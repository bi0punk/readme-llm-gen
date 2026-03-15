from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from readme_rebuilder.config import ScannerSettings
from readme_rebuilder.utils.path_filters import build_excluded_dir_set, is_excluded_path


class TreeService:
    def __init__(self, settings: ScannerSettings) -> None:
        self.settings = settings
        self.excluded_dirs = build_excluded_dir_set(settings.exclude_dirs)

    def _exclude_names(self) -> list[str]:
        return sorted(name for name in self.excluded_dirs if name)

    def _is_excluded(self, path: Path) -> bool:
        return is_excluded_path(path, self.excluded_dirs)

    def _system_tree_available(self) -> bool:
        return shutil.which('tree') is not None

    def _build_tree_command(self, project_path: Path) -> list[str]:
        exclude_pattern = '|'.join(self._exclude_names())
        command = ['tree', '-a', '-L', str(self.settings.max_tree_depth)]
        if exclude_pattern:
            command.extend(['-I', exclude_pattern])
        command.append(str(project_path))
        return command

    def _parse_tree_report(self, lines: list[str]) -> tuple[int, int]:
        if not lines:
            return 0, 0
        match = re.search(r'(\d+) directories?,\s+(\d+) files?', lines[-1])
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, 0

    def _build_tree_with_system_command(self, project_path: Path) -> dict | None:
        if not self._system_tree_available():
            return None
        command = self._build_tree_command(project_path)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self.settings.tree_timeout_seconds, check=False)
        except (subprocess.SubprocessError, OSError):
            return None
        if result.returncode != 0:
            return None
        all_lines = [line.rstrip() for line in result.stdout.splitlines() if line.strip()]
        dir_count, file_count = self._parse_tree_report(all_lines)
        body_lines = all_lines[:-1] if dir_count or file_count else all_lines
        root_label = project_path.name
        if body_lines and (body_lines[0] == str(project_path) or body_lines[0] == root_label):
            body_lines = body_lines[1:]
        truncated = False
        if len(body_lines) > self.settings.max_tree_entries:
            body_lines = body_lines[: self.settings.max_tree_entries]
            body_lines.append('... [tree output truncated]')
            truncated = True
        return {
            'root': root_label,
            'directories': dir_count,
            'files': file_count,
            'entries': body_lines,
            'tree_text': '\n'.join([root_label, *body_lines]),
            'tree_command': ' '.join(command),
            'tree_source': 'system',
            'tree_truncated': truncated,
            'excluded_dirs': self._exclude_names(),
        }

    def _build_tree_with_python_fallback(self, project_path: Path) -> dict:
        entries: list[str] = []
        file_count = 0
        dir_count = 0
        truncated = False
        for current in sorted(project_path.rglob('*')):
            try:
                rel = current.relative_to(project_path)
            except ValueError:
                continue
            if self._is_excluded(rel):
                continue
            if len(rel.parts) > self.settings.max_tree_depth:
                continue
            if len(entries) >= self.settings.max_tree_entries:
                entries.append('... [tree output truncated]')
                truncated = True
                break
            prefix = '  ' * max(len(rel.parts) - 1, 0)
            entries.append(f"{prefix}{rel.name}{'/' if current.is_dir() else ''}")
            if current.is_dir():
                dir_count += 1
            else:
                file_count += 1
        return {
            'root': project_path.name,
            'directories': dir_count,
            'files': file_count,
            'entries': entries,
            'tree_text': '\n'.join([project_path.name, *entries]),
            'tree_command': '',
            'tree_source': 'python-fallback',
            'tree_truncated': truncated,
            'excluded_dirs': self._exclude_names(),
        }

    def build_tree_summary(self, project_path: Path) -> dict:
        mode = self.settings.tree_mode
        if mode in {'system', 'system_auto'}:
            system_tree = self._build_tree_with_system_command(project_path)
            if system_tree is not None:
                return system_tree
            if mode == 'system':
                raise RuntimeError("No se pudo ejecutar el comando 'tree' en modo system")
        return self._build_tree_with_python_fallback(project_path)
