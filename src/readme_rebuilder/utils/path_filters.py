from __future__ import annotations

from pathlib import Path

DEFAULT_EXCLUDED_DIRS = {
    '.git',
    '.venv', 'venv', 'env', 'ENV',
    'virtualenv', '.virtualenv',
    '.tox', '.nox', '.direnv',
    'node_modules',
    '__pycache__', 'dist', 'build',
    '.mypy_cache', '.pytest_cache', '.ruff_cache',
    '.idea', '.vscode',
    '.readme_rebuilder',
}

_VENV_PREFIXES = ('venv', '.venv', 'env', '.env', 'virtualenv', '.virtualenv')


def build_excluded_dir_set(configured: list[str] | None = None) -> set[str]:
    return DEFAULT_EXCLUDED_DIRS | set(configured or [])


def is_excluded_name(name: str, excluded_dirs: set[str] | list[str] | tuple[str, ...]) -> bool:
    excluded = set(excluded_dirs)
    if name in excluded:
        return True
    low = name.lower()
    return any(low.startswith(prefix) for prefix in _VENV_PREFIXES)


def is_excluded_path(path: Path | str, excluded_dirs: set[str] | list[str] | tuple[str, ...]) -> bool:
    parts = Path(path).parts if not isinstance(path, Path) else path.parts
    return any(is_excluded_name(part, excluded_dirs) for part in parts)
