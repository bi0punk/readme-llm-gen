from pathlib import Path

from readme_rebuilder.config import ScannerSettings
from readme_rebuilder.services.tree_service import TreeService


class DummyCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def test_system_tree_command_excludes_virtualenvs(monkeypatch, tmp_path: Path):
    service = TreeService(ScannerSettings(max_tree_depth=3, max_tree_entries=50, exclude_dirs=['.git']))
    monkeypatch.setattr(service, '_system_tree_available', lambda: True)

    captured = {}

    def fake_run(command, capture_output, text, timeout, check):
        captured['command'] = command
        return DummyCompletedProcess(stdout=f"{tmp_path.name}\n├── app.py\n└── src\n\n1 directories, 1 files\n")

    monkeypatch.setattr('subprocess.run', fake_run)
    result = service.build_tree_summary(tmp_path)

    assert result['tree_source'] == 'system'
    assert result['directories'] == 1
    assert result['files'] == 1
    assert '-I' in captured['command']
    pattern = captured['command'][captured['command'].index('-I') + 1]
    assert 'venv' in pattern
    assert '.venv' in pattern
    assert 'env' in pattern
    assert 'ENV' in pattern


def test_python_fallback_excludes_virtualenv_directory(tmp_path: Path):
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src' / 'app.py').write_text('print(1)', encoding='utf-8')
    (tmp_path / 'venv').mkdir()
    (tmp_path / 'venv' / 'ignored.py').write_text('print(2)', encoding='utf-8')

    service = TreeService(ScannerSettings(max_tree_depth=4, max_tree_entries=50, exclude_dirs=['venv']))
    result = service.build_tree_summary(tmp_path)

    rendered = '\n'.join(result['entries'])
    assert 'ignored.py' not in rendered
    assert 'venv' not in rendered
    assert 'app.py' in rendered
