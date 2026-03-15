import json
from pathlib import Path

from readme_rebuilder.config import OutputSettings
from readme_rebuilder.services.writer_service import WriterService


def test_writer_generates_diff_and_safe_analysis(tmp_path: Path):
    (tmp_path / 'README.md').write_text('# Old\n\nlegacy\n', encoding='utf-8')
    service = WriterService(OutputSettings(report_dir='.readme_rebuilder', save_readme_diff=True, persist_source_snippets=False))

    result = service.write_project_outputs(
        project_path=tmp_path,
        readme_content='# New\n\nupdated\n',
        overwrite=False,
        analysis={
            'existing_readme': '# Old',
            'selected_files': [{'path': 'app.py', 'content': 'SECRET=1', 'score': '10'}],
            'secondary_files': [],
        },
    )

    diff_text = Path(result['diff_path']).read_text(encoding='utf-8')
    analysis = json.loads(Path(result['analysis_path']).read_text(encoding='utf-8'))

    assert 'Old' in diff_text or '-legacy' in diff_text
    assert result['diff_changed'] is True
    assert 'content' not in analysis['selected_files'][0]
    assert (tmp_path / 'README.generated.md').exists()
