from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

IGNORE_FILE_NAME = '.readme-rebuilderignore'


@dataclass(frozen=True)
class IgnoreRule:
    pattern: str
    directory_only: bool = False
    anchored: bool = False

    def matches(self, rel_path: Path, is_dir: bool) -> bool:
        rel = rel_path.as_posix().lstrip('./')
        name = rel_path.name
        if self.directory_only and not is_dir:
            return False
        pattern = self.pattern
        if self.anchored:
            return fnmatch.fnmatch(rel, pattern)
        if '/' in pattern or '*' in pattern or '?' in pattern or '[' in pattern:
            return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern)
        if self.directory_only:
            return pattern in rel_path.parts
        return name == pattern or pattern in rel_path.parts


class ProjectIgnoreMatcher:
    def __init__(self, rules: list[IgnoreRule]) -> None:
        self.rules = rules

    def matches(self, rel_path: Path | str, is_dir: bool = False) -> bool:
        path = rel_path if isinstance(rel_path, Path) else Path(rel_path)
        return any(rule.matches(path, is_dir=is_dir) for rule in self.rules)

    @property
    def active(self) -> bool:
        return bool(self.rules)


def load_project_ignore(project_path: Path, filename: str = IGNORE_FILE_NAME) -> ProjectIgnoreMatcher:
    ignore_path = project_path / filename
    rules: list[IgnoreRule] = []
    if not ignore_path.exists():
        return ProjectIgnoreMatcher(rules)
    for raw_line in ignore_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        anchored = line.startswith('/')
        if anchored:
            line = line[1:]
        directory_only = line.endswith('/')
        if directory_only:
            line = line[:-1]
        if line:
            rules.append(IgnoreRule(pattern=line, directory_only=directory_only, anchored=anchored))
    return ProjectIgnoreMatcher(rules)
