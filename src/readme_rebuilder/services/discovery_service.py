from __future__ import annotations

from pathlib import Path

from readme_rebuilder.config import DiscoverySettings
from readme_rebuilder.utils.path_filters import build_excluded_dir_set, is_excluded_path


class DiscoveryService:
    def __init__(self, settings: DiscoverySettings) -> None:
        self.settings = settings
        self.excluded_dirs = build_excluded_dir_set(settings.exclude_dirs)

    def _is_excluded(self, path: Path, base_dir: Path) -> bool:
        try:
            rel = path.relative_to(base_dir)
        except ValueError:
            rel = path
        return is_excluded_path(rel, self.excluded_dirs)

    def _is_hidden(self, path: Path, base_dir: Path) -> bool:
        try:
            rel = path.relative_to(base_dir)
        except ValueError:
            rel = path
        return any(part.startswith('.') for part in rel.parts if part not in {'.', ''} and part not in self.excluded_dirs)

    def _looks_like_project(self, path: Path) -> bool:
        return any((path / marker).exists() for marker in self.settings.project_markers)

    def discover_projects(self, base_dir: Path) -> list[Path]:
        base_dir = base_dir.resolve()
        discovered: list[Path] = []
        seen: set[Path] = set()

        if self._looks_like_project(base_dir):
            discovered.append(base_dir)
            seen.add(base_dir)

        for current in sorted(base_dir.rglob('*')):
            if not current.is_dir():
                continue
            if self._is_excluded(current, base_dir):
                continue
            if not self.settings.include_hidden and self._is_hidden(current, base_dir):
                continue
            if len(current.relative_to(base_dir).parts) > self.settings.max_depth:
                continue
            if self._looks_like_project(current) and current not in seen:
                discovered.append(current)
                seen.add(current)

        return sorted(discovered)
