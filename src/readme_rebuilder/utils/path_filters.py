from __future__ import annotations

from pathlib import Path

DEFAULT_EXCLUDED_DIRS = {
    # VCS
    '.git',
    # Entornos virtuales Python — todos los nombres comunes
    '.venv', 'venv', 'env', 'ENV', '.env',
    'virtualenv', '.virtualenv',
    # Tox / nox / direnv
    '.tox', '.nox', '.direnv',
    # JS
    'node_modules',
    # Build artifacts
    '__pycache__', 'dist', 'build',
    '.mypy_cache', '.pytest_cache', '.ruff_cache',
    # IDEs
    '.idea', '.vscode',
    # Output propio de esta herramienta
    '.readme_rebuilder',
}

# Patrones de nombre que indican entorno virtual aunque no estén en la lista exacta
_VENV_PREFIXES = ('venv', '.venv', 'env', '.env', 'virtualenv', '.virtualenv')


def build_excluded_dir_set(configured: list[str] | None = None) -> set[str]:
    return DEFAULT_EXCLUDED_DIRS | set(configured or [])


def is_excluded_path(path: Path | str, excluded_dirs: set[str] | list[str] | tuple[str, ...]) -> bool:
    parts = Path(path).parts if not isinstance(path, Path) else path.parts
    excluded = set(excluded_dirs)
    for part in parts:
        if part in excluded:
            return True
        # Excluir entornos virtuales con nombres custom (ej: .venv-dev, venv3.11)
        low = part.lower()
        if any(low.startswith(prefix) for prefix in _VENV_PREFIXES):
            return True
    return False
