from pathlib import Path

from readme_rebuilder.config import ScannerSettings
from readme_rebuilder.services.file_selector_service import FileSelectorService
from readme_rebuilder.services.tree_service import TreeService


def test_project_ignore_excludes_selected_files(tmp_path: Path):
    (tmp_path / '.readme-rebuilderignore').write_text('docs/\nsecret.py\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text('from flask import Flask\napp = Flask(__name__)', encoding='utf-8')
    (tmp_path / 'secret.py').write_text('TOKEN="abc"', encoding='utf-8')
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs' / 'guide.md').write_text('# doc', encoding='utf-8')

    service = FileSelectorService(ScannerSettings(max_files=10, important_file_patterns=['*.py', '*.md']))
    selected = [p.relative_to(tmp_path).as_posix() for p in service.select_files(tmp_path)]

    assert 'app.py' in selected
    assert 'secret.py' not in selected
    assert 'docs/guide.md' not in selected


def test_tree_service_uses_python_fallback_when_ignore_file_exists(tmp_path: Path):
    (tmp_path / '.readme-rebuilderignore').write_text('generated/\n', encoding='utf-8')
    (tmp_path / 'generated').mkdir()
    (tmp_path / 'generated' / 'skip.py').write_text('print(1)', encoding='utf-8')
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'app.py').write_text('print(2)', encoding='utf-8')

    service = TreeService(ScannerSettings(max_tree_depth=4, max_tree_entries=50))
    result = service.build_tree_summary(tmp_path)

    rendered = '\n'.join(result['entries'])
    assert result['tree_source'] == 'python-fallback'
    assert 'generated' not in rendered
    assert 'skip.py' not in rendered
    assert 'app.py' in rendered
