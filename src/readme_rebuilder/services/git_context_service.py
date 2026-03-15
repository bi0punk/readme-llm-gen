from __future__ import annotations

import subprocess
from pathlib import Path


class GitContextService:
    def _run(self, project_path: Path, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ['git', *args],
                cwd=str(project_path),
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ''
        if result.returncode != 0:
            return ''
        return result.stdout.strip()

    def collect(self, project_path: Path) -> dict:
        git_dir = project_path / '.git'
        has_git_repo = git_dir.exists() or bool(self._run(project_path, ['rev-parse', '--is-inside-work-tree']))
        if not has_git_repo:
            return {
                'has_git_repo': False,
                'git_dir_type': 'absent',
                'current_branch': '',
                'remotes': [],
                'last_commit': '',
                'tracked_files_count': 0,
            }

        remotes_raw = self._run(project_path, ['remote', '-v'])
        remotes = []
        for line in remotes_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                remotes.append(f'{parts[0]} {parts[1]}')

        tracked = self._run(project_path, ['ls-files'])
        branch = self._run(project_path, ['rev-parse', '--abbrev-ref', 'HEAD'])
        last_commit = self._run(project_path, ['log', '-1', '--pretty=format:%h %s'])

        git_dir_type = 'directory' if git_dir.is_dir() else 'file' if git_dir.is_file() else 'worktree-or-indirect'
        return {
            'has_git_repo': True,
            'git_dir_type': git_dir_type,
            'current_branch': branch,
            'remotes': remotes,
            'last_commit': last_commit,
            'tracked_files_count': len([line for line in tracked.splitlines() if line.strip()]),
        }
