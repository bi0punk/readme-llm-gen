from __future__ import annotations

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

    def write_project_outputs(self, project_path: Path, readme_content: str, overwrite: bool, analysis: dict) -> dict:
        output_name = 'README.md' if overwrite else self.settings.readme_name
        output_path = project_path / output_name
        report_dir = project_path / self.settings.report_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = report_dir / 'analysis.json'

        output_path.write_text(readme_content, encoding='utf-8')
        if self.settings.save_analysis_json:
            analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding='utf-8')

        return {
            'output_path': str(output_path),
            'analysis_path': str(analysis_path),
            'had_existing_readme': bool(analysis.get('existing_readme', '').strip()),
        }
