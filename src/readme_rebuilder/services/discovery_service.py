from __future__ import annotations

from pathlib import Path

from readme_rebuilder.config import DiscoverySettings
from readme_rebuilder.utils.fs_walk import iter_dirs
from readme_rebuilder.utils.path_filters import build_excluded_dir_set
from readme_rebuilder.utils.project_ignore import load_project_ignore


class DiscoveryService:
    def __init__(self, settings: DiscoverySettings) -> None:
        self.settings = settings
        self.excluded_dirs = build_excluded_dir_set(settings.exclude_dirs)

    def _project_score(self, path: Path) -> int:
        score = 0
        for marker in self.settings.project_markers:
            if (path / marker).exists():
                if marker == '.git':
                    score += 100
                elif marker in {'pyproject.toml', 'package.json'}:
                    score += 80
                elif marker in {'requirements.txt', 'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml'}:
                    score += 60
                else:
                    score += 35
        if (path / 'src').exists():
            score += 25
        if (path / 'README.md').exists():
            score += 15
        return score

    def _looks_like_project(self, path: Path) -> bool:
        return self._project_score(path) >= 80

    def discover_projects(self, base_dir: Path) -> list[Path]:
        base_dir = base_dir.resolve()
        ignore_matcher = load_project_ignore(base_dir)
        discovered: list[Path] = []
        seen: set[Path] = set()

        if self._looks_like_project(base_dir):
            discovered.append(base_dir)
            seen.add(base_dir)

        for rel_path, current in iter_dirs(base_dir, self.excluded_dirs, include_hidden=self.settings.include_hidden, ignore_matcher=ignore_matcher):
            if len(rel_path.parts) > self.settings.max_depth:
                continue
            if self._looks_like_project(current) and current not in seen:
                discovered.append(current)
                seen.add(current)

        return sorted(discovered)
