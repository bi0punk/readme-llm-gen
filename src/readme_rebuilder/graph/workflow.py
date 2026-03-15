from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from langgraph.graph import END, StateGraph

from readme_rebuilder.graph.state import GraphState
from readme_rebuilder.models.schemas import ContextDigest, GapAnalysis, ReadmeBlueprint
from readme_rebuilder.prompts.templates import (
    BLUEPRINT_PROMPT,
    BLUEPRINT_PROMPT_FAST,
    GAP_ANALYSIS_PROMPT,
    PRIMARY_CONTEXT_PROMPT,
    README_BASE_TEMPLATE,
    SECONDARY_CONTEXT_PROMPT,
)

_PROMPT_WARN_CHARS = 6_000


class ReadmeGraphBuilder:
    def __init__(self, tree_service, file_selector_service, heuristics_service,
                 llm_service, writer_service, git_context_service, settings,
                 fast: bool = False) -> None:
        self.tree_service = tree_service
        self.file_selector_service = file_selector_service
        self.heuristics_service = heuristics_service
        self.llm_service = llm_service
        self.writer_service = writer_service
        self.git_context_service = git_context_service
        self.settings = settings
        self.fast = fast

    def _observer(self, state: GraphState):
        return state.get('observer')

    def _start(self, state: GraphState, step_name: str) -> None:
        observer = self._observer(state)
        if observer:
            observer.step_start(step_name)
            self.llm_service.set_observer(observer)

    def _done(self, state: GraphState, step_name: str, summary: str) -> None:
        observer = self._observer(state)
        if observer:
            observer.step_done(step_name, summary)

    def _collect_tree(self, project_path: Path) -> dict:
        return self.tree_service.build_tree_summary(project_path)

    def _collect_git(self, project_path: Path) -> dict:
        return self.git_context_service.collect(project_path)

    def _collect_files(self, project_path: Path) -> tuple[list, list, str]:
        selected_paths = self.file_selector_service.select_files(project_path)
        payload = self.file_selector_service.read_files(project_path, selected_paths)
        existing_readme, filtered = self.file_selector_service.split_existing_readme(payload)
        file_paths = [item['path'] for item in filtered]
        return filtered, file_paths, existing_readme

    def gather_context(self, state: GraphState) -> GraphState:
        self._start(state, 'gather_context')
        project_path = Path(state['project_path'])
        tasks = {
            'tree': lambda: self._collect_tree(project_path),
            'git': lambda: self._collect_git(project_path),
            'files': lambda: self._collect_files(project_path),
        }
        results: dict = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                results[futures[future]] = future.result()

        tree_summary = results['tree']
        git_context = results['git']
        selected_files, selected_file_paths, existing_readme = results['files']
        observer = self._observer(state)
        if observer:
            observer.selected_files(selected_file_paths)

        summary = (
            f"{tree_summary['directories']} dirs · {tree_summary['files']} archivos"
            f" · {len(selected_file_paths)} seleccionados"
            f" · fuente={tree_summary.get('tree_source', '?')}"
            f" · git={'sí' if git_context.get('has_git_repo') else 'no'}"
        )
        if existing_readme.strip():
            summary += ' · README previo detectado'
        self._done(state, 'gather_context', summary)

        return {
            'tree_summary': tree_summary,
            'git_context': git_context,
            'selected_files': selected_files,
            'selected_file_paths': selected_file_paths,
            'primary_files': selected_files,
            'primary_file_paths': selected_file_paths,
            'existing_readme': existing_readme,
        }

    def run_heuristics(self, state: GraphState) -> GraphState:
        self._start(state, 'run_heuristics')
        project_path = Path(state['project_path'])
        facts = self.heuristics_service.derive_project_facts(
            files=state['selected_files'],
            tree_summary=state['tree_summary'],
            project_path=project_path,
            git_context=state.get('git_context', {}),
        )
        git_context = state['git_context']
        observer = self._observer(state)
        if observer:
            observer.heuristics(facts | {
                'git_branch': git_context.get('current_branch', ''),
                'git_remotes': git_context.get('remotes', [])[:2],
            })
        summary = (
            f"langs={','.join(facts['languages']) or '-'}"
            f" · frameworks={len(facts['framework_hints'])}"
            f" · entrypoints={len(facts['entrypoints'])}"
            f" · git={'sí' if git_context['has_git_repo'] else 'no'}"
        )
        self._done(state, 'run_heuristics', summary)
        return {'heuristic_facts': facts}

    def build_primary_context(self, state: GraphState) -> GraphState:
        self._start(state, 'build_primary_context')
        snippets = json.dumps(state['selected_files'], ensure_ascii=False, indent=2)
        prompt = PRIMARY_CONTEXT_PROMPT.format(
            tree_text=state['tree_summary'].get('tree_text', ''),
            heuristic_facts=json.dumps(state['heuristic_facts'], ensure_ascii=False, indent=2),
            git_context=json.dumps(state.get('git_context', {}), ensure_ascii=False, indent=2),
            existing_readme=state.get('existing_readme', ''),
            primary_file_snippets=snippets,
        )
        if self._observer(state) and len(prompt) > _PROMPT_WARN_CHARS:
            self._observer(state).info(
                'Prompt grande detectado',
                f'{len(prompt)} chars → el LLM puede tardar varios minutos. Usa --fast si necesitas respuesta rápida.',
                style='yellow',
            )
        primary_context = self.llm_service.structured(prompt, ContextDigest, label='primary_context_digest')
        self._done(state, 'build_primary_context', f"objetivo={primary_context.inferred_goal[:60]} · open_questions={len(primary_context.open_questions)}")
        return {'primary_context': primary_context.model_dump()}

    def detect_information_gaps(self, state: GraphState) -> GraphState:
        self._start(state, 'detect_information_gaps')
        prompt = GAP_ANALYSIS_PROMPT.format(
            primary_context=json.dumps(state['primary_context'], ensure_ascii=False, indent=2),
        )
        gap_result = self.llm_service.structured(prompt, GapAnalysis, label='information_gaps')
        gaps = gap_result.gaps[:6]
        self._done(state, 'detect_information_gaps', ', '.join(gaps) if gaps else 'sin gaps críticos')
        return {'info_gaps': gaps}

    def enrich_context(self, state: GraphState) -> GraphState:
        self._start(state, 'enrich_context')
        gaps = state.get('info_gaps', [])
        if not gaps:
            self._done(state, 'enrich_context', 'sin enriquecimiento adicional')
            return {
                'secondary_context': {
                    'project_name': state['primary_context']['project_name'],
                    'inferred_goal': state['primary_context']['inferred_goal'],
                    'architecture_notes': [],
                    'setup_notes': [],
                    'usage_notes': [],
                    'testing_notes': [],
                    'docker_notes': [],
                    'open_questions': [],
                },
                'secondary_files': [],
                'secondary_file_paths': [],
            }

        project_path = Path(state['project_path'])
        secondary_paths = self.file_selector_service.choose_secondary_files(
            project_path=project_path,
            primary_paths=state.get('primary_file_paths', []),
            gaps=gaps,
            max_files=6,
        )
        secondary_files = self.file_selector_service.read_files(project_path, secondary_paths)
        secondary_file_paths = [item['path'] for item in secondary_files]
        prompt = SECONDARY_CONTEXT_PROMPT.format(
            primary_context=json.dumps(state['primary_context'], ensure_ascii=False, indent=2),
            requested_gaps=json.dumps(gaps, ensure_ascii=False, indent=2),
            secondary_file_snippets=json.dumps(secondary_files, ensure_ascii=False, indent=2),
        )
        secondary_context = self.llm_service.structured(prompt, ContextDigest, label='secondary_context_digest')
        self._done(state, 'enrich_context', f"{len(secondary_file_paths)} archivos secundarios · gaps={len(gaps)}")
        return {
            'secondary_context': secondary_context.model_dump(),
            'secondary_files': secondary_files,
            'secondary_file_paths': secondary_file_paths,
        }

    def build_blueprint(self, state: GraphState) -> GraphState:
        self._start(state, 'build_blueprint')
        if self.fast:
            snippets = json.dumps(
                [{**f, 'content': f['content'][:1500]} for f in state['selected_files']],
                ensure_ascii=False,
            )
            prompt = BLUEPRINT_PROMPT_FAST.format(
                tree_text=state['tree_summary'].get('tree_text', ''),
                heuristic_facts=json.dumps(state['heuristic_facts'], ensure_ascii=False),
                selected_file_snippets=snippets,
            )
        else:
            prompt = BLUEPRINT_PROMPT.format(
                base_template=README_BASE_TEMPLATE,
                tree_text=state['tree_summary'].get('tree_text', ''),
                heuristic_facts=json.dumps(state['heuristic_facts'], ensure_ascii=False, indent=2),
                git_context=json.dumps(state.get('git_context', {}), ensure_ascii=False, indent=2),
                existing_readme=state.get('existing_readme', ''),
                primary_context=json.dumps(state.get('primary_context', {}), ensure_ascii=False, indent=2),
                secondary_context=json.dumps(state.get('secondary_context', {}), ensure_ascii=False, indent=2),
            )
        blueprint = self.llm_service.structured(prompt, ReadmeBlueprint, label='readme_blueprint')
        self._done(state, 'build_blueprint', f"{blueprint.project_type} · {blueprint.primary_language} · {len(blueprint.features)} features")
        return {
            'blueprint': blueprint.model_dump(),
            'project_profile': {
                'project_name': blueprint.project_name,
                'project_type': blueprint.project_type,
                'primary_language': blueprint.primary_language,
                'one_liner': blueprint.one_liner,
            },
        }

    def validate_blueprint(self, state: GraphState) -> GraphState:
        self._start(state, 'validate_blueprint')
        blueprint = dict(state['blueprint'])
        if not blueprint.get('title'):
            blueprint['title'] = blueprint.get('project_name', 'Proyecto')
        if not blueprint.get('tagline'):
            blueprint['tagline'] = blueprint.get('one_liner', 'README generado automáticamente.')
        if not blueprint.get('overview'):
            blueprint['overview'] = blueprint.get('one_liner', 'Sin descripción suficiente.')
        self._done(state, 'validate_blueprint', 'campos mínimos validados')
        return {'blueprint': blueprint}

    def write_outputs(self, state: GraphState) -> GraphState:
        self._start(state, 'write_outputs')
        project_path = Path(state['project_path'])
        readme_content = self.writer_service.render_readme_from_blueprint(state['blueprint'])
        write_result = self.writer_service.write_project_outputs(
            project_path=project_path,
            readme_content=readme_content,
            overwrite=bool(state.get('overwrite_readme', False)),
            analysis={
                'tree_summary': state['tree_summary'],
                'selected_files': state.get('selected_files', []),
                'selected_file_paths': state.get('selected_file_paths', []),
                'secondary_files': state.get('secondary_files', []),
                'secondary_file_paths': state.get('secondary_file_paths', []),
                'heuristic_facts': state['heuristic_facts'],
                'git_context': state.get('git_context', {}),
                'existing_readme': state.get('existing_readme', ''),
                'primary_context': state.get('primary_context', {}),
                'secondary_context': state.get('secondary_context', {}),
                'info_gaps': state.get('info_gaps', []),
                'project_profile': state['project_profile'],
                'blueprint': state['blueprint'],
                'trace_events': self._observer(state).events if self._observer(state) else [],
            },
            save_analysis_json=bool(state.get('save_analysis_json', self.settings.output.save_analysis_json)),
            dry_run=bool(state.get('dry_run', False)),
        )
        self._done(state, 'write_outputs', Path(write_result['output_path']).name)
        return write_result

    def compile(self):
        graph = StateGraph(GraphState)
        graph.add_node('gather_context', self.gather_context)
        graph.add_node('run_heuristics', self.run_heuristics)
        graph.add_node('build_primary_context', self.build_primary_context)
        graph.add_node('detect_information_gaps', self.detect_information_gaps)
        graph.add_node('enrich_context', self.enrich_context)
        graph.add_node('build_blueprint', self.build_blueprint)
        graph.add_node('validate_blueprint', self.validate_blueprint)
        graph.add_node('write_outputs', self.write_outputs)

        graph.set_entry_point('gather_context')
        graph.add_edge('gather_context', 'run_heuristics')
        graph.add_edge('run_heuristics', 'build_primary_context')
        graph.add_edge('build_primary_context', 'detect_information_gaps')
        graph.add_edge('detect_information_gaps', 'enrich_context')
        graph.add_edge('enrich_context', 'build_blueprint')
        graph.add_edge('build_blueprint', 'validate_blueprint')
        graph.add_edge('validate_blueprint', 'write_outputs')
        graph.add_edge('write_outputs', END)
        return graph.compile()
