from __future__ import annotations

import difflib
import json
from pathlib import Path

from readme_rebuilder.config import OutputSettings
from readme_rebuilder.prompts.templates import README_BASE_TEMPLATE


def _as_bullets(items: list[str], empty: str = '- No identificado con suficiente evidencia.') -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return empty
    return '\n'.join(f'- {item}' for item in cleaned)


class WriterService:
    def __init__(self, settings: OutputSettings) -> None:
        self.settings = settings
        self.template_text = README_BASE_TEMPLATE

    def render_readme_from_blueprint(self, blueprint: dict) -> str:
        return self.template_text.format(
            title=blueprint.get('title') or blueprint.get('project_name') or 'Proyecto',
            tagline=blueprint.get('tagline') or blueprint.get('one_liner') or 'README generado automáticamente.',
            overview=blueprint.get('overview') or 'Sin descripción suficiente.',
            features=_as_bullets(blueprint.get('features', [])),
            architecture=_as_bullets(blueprint.get('architecture', [])),
            prerequisites=_as_bullets(blueprint.get('prerequisites', [])),
            installation=_as_bullets(blueprint.get('installation', [])),
            configuration=_as_bullets(blueprint.get('configuration', [])),
            usage=_as_bullets(blueprint.get('usage', [])),
            testing=_as_bullets(blueprint.get('testing', [])),
            docker=_as_bullets(blueprint.get('docker', [])),
            repository_notes=_as_bullets(blueprint.get('repository_notes', [])),
            limitations=_as_bullets(blueprint.get('limitations', [])),
            next_steps=_as_bullets(blueprint.get('next_steps', [])),
        ).strip() + '\n'

    def _safe_analysis_payload(self, analysis: dict) -> dict:
        if self.settings.persist_source_snippets:
            return analysis
        clone = dict(analysis)
        clone['selected_files'] = [
            {key: value for key, value in item.items() if key != 'content'}
            for item in analysis.get('selected_files', [])
        ]
        clone['secondary_files'] = [
            {key: value for key, value in item.items() if key != 'content'}
            for item in analysis.get('secondary_files', [])
        ]
        return clone

    def _write_text_atomic(self, path: Path, content: str) -> None:
        if not self.settings.write_atomically:
            path.write_text(content, encoding='utf-8')
            return
        tmp_path = path.with_suffix(path.suffix + '.tmp')
        tmp_path.write_text(content, encoding='utf-8')
        tmp_path.replace(path)

    def _build_unified_diff(self, existing_text: str, new_text: str, path_label: str) -> str:
        lines = difflib.unified_diff(
            existing_text.splitlines(),
            new_text.splitlines(),
            fromfile=f'{path_label} (existing)',
            tofile=f'{path_label} (generated)',
            lineterm='',
            n=self.settings.diff_context_lines,
        )
        return '\n'.join(lines) + '\n'

    def write_project_outputs(
        self,
        project_path: Path,
        readme_content: str,
        overwrite: bool,
        analysis: dict,
        save_analysis_json: bool | None = None,
        dry_run: bool = False,
    ) -> dict:
        output_name = 'README.md' if overwrite else self.settings.readme_name
        output_path = project_path / output_name
        report_dir = project_path / self.settings.report_dir
        analysis_path = report_dir / 'analysis.json'
        diff_path = report_dir / 'readme.diff'

        existing_text = ''
        existing_readme_path = project_path / 'README.md'
        if existing_readme_path.exists():
            existing_text = existing_readme_path.read_text(encoding='utf-8', errors='ignore')
        diff_text = self._build_unified_diff(existing_text, readme_content, output_name)

        if not dry_run:
            report_dir.mkdir(parents=True, exist_ok=True)
            self._write_text_atomic(output_path, readme_content)
            if self.settings.save_readme_diff:
                self._write_text_atomic(diff_path, diff_text)
            should_save = self.settings.save_analysis_json if save_analysis_json is None else save_analysis_json
            if should_save:
                safe_analysis = self._safe_analysis_payload(analysis)
                self._write_text_atomic(analysis_path, json.dumps(safe_analysis, ensure_ascii=False, indent=2))
        return {
            'output_path': str(output_path),
            'analysis_path': str(analysis_path),
            'diff_path': str(diff_path),
            'diff_changed': bool(diff_text.strip()),
            'had_existing_readme': bool(existing_text.strip() or analysis.get('existing_readme', '').strip()),
        }
