from __future__ import annotations

from pathlib import Path

DEFAULT_EXCLUDED_DIRS = {
    '.git', '.venv', 'venv', 'env', 'ENV',
    '.tox', '.nox', '.direnv',
    'node_modules', '__pycache__',
    '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'dist', 'build', '.idea', '.vscode',
}


def build_excluded_dir_set(configured: list[str] | None = None) -> set[str]:
    return DEFAULT_EXCLUDED_DIRS | set(configured or [])


def is_excluded_path(path: Path | str, excluded_dirs: set[str] | list[str] | tuple[str, ...]) -> bool:
    parts = Path(path).parts if not isinstance(path, Path) else path.parts
    excluded = set(excluded_dirs)
    return any(part in excluded for part in parts)
