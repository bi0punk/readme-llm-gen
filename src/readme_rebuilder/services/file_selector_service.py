from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from readme_rebuilder.config import ScannerSettings
from readme_rebuilder.utils.path_filters import build_excluded_dir_set, is_excluded_path

TEXT_EXTENSIONS = {
    '.py', '.md', '.txt', '.toml', '.yml', '.yaml', '.json', '.ini', '.cfg', '.env',
    '.js', '.ts', '.tsx', '.jsx', '.sh', '.bash', '.zsh', '.html', '.css', '.sql',
    '.java', '.go', '.rs', '.php', '.rb', '.xml'
}

HIGH_SIGNAL_NAMES = {
    'app.py', 'main.py', 'run.py', 'manage.py', 'wsgi.py', 'asgi.py', 'server.py', 'api.py',
    'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'requirements.txt', 'pyproject.toml',
    'package.json', 'Makefile', '.env.example', 'config.yaml', 'settings.py', 'routes.py',
    'README.md', 'README.rst', 'README.txt', '.gitignore'
}

SECONDARY_HINT_PATTERNS = [
    'config.py', 'settings.py', '.env.example', 'routes.py', 'urls.py', 'models.py',
    'tests/*', 'tests/**/*.py', '.github/workflows/*', 'docker-compose*.yml', 'docker-compose*.yaml'
]


class FileSelectorService:
    def __init__(self, settings: ScannerSettings) -> None:
        self.settings = settings
        self.excluded_dirs = build_excluded_dir_set(settings.exclude_dirs)

    def _is_excluded(self, path: Path) -> bool:
        return is_excluded_path(path, self.excluded_dirs)

    def _is_text_candidate(self, path: Path) -> bool:
        return path.name in HIGH_SIGNAL_NAMES or path.suffix.lower() in TEXT_EXTENSIONS or path.name.lower() == 'dockerfile'

    def _priority_score(self, rel_path: str) -> int:
        score = 0
        name = Path(rel_path).name
        if name in HIGH_SIGNAL_NAMES:
            score += 100
        if any(fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern) for pattern in self.settings.important_file_patterns):
            score += 60
        if rel_path.count('/') == 0:
            score += 20
        if re.search(r'(app|main|api|server|manage|route|setting|config|docker|readme|requirement|pyproject|package|makefile)', rel_path, re.I):
            score += 30
        if re.search(r'(test|spec|fixture|mock|min\.js|min\.css|coverage)', rel_path, re.I):
            score -= 20
        return score

    def _iter_candidate_files(self, project_path: Path):
        for path in project_path.rglob('*'):
            if not path.is_file():
                continue
            rel = path.relative_to(project_path)
            if self._is_excluded(rel):
                continue
            if not self._is_text_candidate(path):
                continue
            yield rel, path

    def select_files(self, project_path: Path, max_files: int | None = None) -> list[Path]:
        candidates: list[tuple[int, Path]] = []
        for rel, path in self._iter_candidate_files(project_path):
            candidates.append((self._priority_score(rel.as_posix()), path))
        cap = max_files or self.settings.max_files
        return [p for _, p in sorted(candidates, key=lambda x: x[0], reverse=True)[:cap]]

    def _extract_snippet(self, rel: str, content: str) -> str:
        name = Path(rel).name.lower()
        if name == 'package.json':
            try:
                pkg = json.loads(content)
                scripts = json.dumps(pkg.get('scripts', {}), ensure_ascii=False, indent=2)
                deps = json.dumps(pkg.get('dependencies', {}), ensure_ascii=False, indent=2)
                return f"scripts:\n{scripts}\n\ndependencies:\n{deps}"[: self.settings.max_file_chars]
            except Exception:
                return content[: self.settings.max_file_chars]

        important_lines: list[str] = []
        patterns = [
            r'^(from\s+\S+\s+import\s+.+)$',
            r'^(import\s+.+)$',
            r'^(app\s*=.+)$',
            r'^(router\s*=.+)$',
            r'^(urlpatterns\s*=.+)$',
            r'^(if __name__ == ["\']__main__["\']:\s*)$',
            r'^(uvicorn\..+)$',
            r'^(CMD\s+.+)$',
            r'^(ENTRYPOINT\s+.+)$',
            r'^(EXPOSE\s+.+)$',
        ]
        for line in content.splitlines():
            if any(re.search(pattern, line, re.I) for pattern in patterns):
                important_lines.append(line)
            if len('\n'.join(important_lines)) >= self.settings.max_file_chars // 2:
                break
        if important_lines:
            head = '\n'.join(content.splitlines()[:40])
            tail = '\n'.join(important_lines)
            return f"{head}\n\n# extracted_signals\n{tail}"[: self.settings.max_file_chars]
        return content[: self.settings.max_file_chars]

    def read_files(self, project_path: Path, files: list[Path]) -> list[dict[str, str]]:
        total_chars = 0
        payload: list[dict[str, str]] = []
        for path in files:
            rel = path.relative_to(project_path).as_posix()
            if self._is_excluded(Path(rel)):
                continue
            try:
                content = path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            snippet = self._extract_snippet(rel, content)
            if total_chars + len(snippet) > self.settings.max_total_chars:
                break
            payload.append({'path': rel, 'content': snippet})
            total_chars += len(snippet)
        return payload

    def split_existing_readme(self, payload: list[dict[str, str]]) -> tuple[str, list[dict[str, str]]]:
        readme_candidates = [item for item in payload if Path(item['path']).name.lower().startswith('readme')]
        existing_readme = readme_candidates[0]['content'] if readme_candidates else ''
        filtered = [item for item in payload if item not in readme_candidates]
        return existing_readme, filtered

    def choose_secondary_files(self, project_path: Path, primary_paths: list[str], gaps: list[str], max_files: int = 6) -> list[Path]:
        primary_set = set(primary_paths)
        scored: list[tuple[int, Path]] = []
        for rel, path in self._iter_candidate_files(project_path):
            rel_posix = rel.as_posix()
            if rel_posix in primary_set:
                continue
            score = self._priority_score(rel_posix) // 2
            if any(fnmatch.fnmatch(rel_posix, pattern) for pattern in SECONDARY_HINT_PATTERNS):
                score += 35
            lower = rel_posix.lower()
            if any(token in lower for token in ['config', 'setting', '.env']) and 'configuration' in gaps:
                score += 50
            if any(token in lower for token in ['test', 'pytest', 'spec']) and 'testing' in gaps:
                score += 50
            if any(token in lower for token in ['docker', 'compose']) and 'docker' in gaps:
                score += 50
            if any(token in lower for token in ['route', 'url', 'api']) and 'usage' in gaps:
                score += 40
            if score > 0:
                scored.append((score, path))
        return [p for _, p in sorted(scored, key=lambda x: x[0], reverse=True)[:max_files]]
