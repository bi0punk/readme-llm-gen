from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from readme_rebuilder.utils.path_filters import is_excluded_name, is_excluded_path


def iter_files(base_dir: Path, excluded_dirs: set[str], include_hidden: bool = False, ignore_matcher=None) -> Iterator[tuple[Path, Path]]:
    for root, dirs, files in os.walk(base_dir, topdown=True):
        root_path = Path(root)
        rel_root = root_path.relative_to(base_dir) if root_path != base_dir else Path('.')
        dirs[:] = [
            name for name in sorted(dirs)
            if not is_excluded_name(name, excluded_dirs)
            and (include_hidden or not name.startswith('.'))
            and not (ignore_matcher and ignore_matcher.matches((rel_root / name) if rel_root != Path('.') else Path(name), is_dir=True))
        ]
        for file_name in sorted(files):
            if not include_hidden and file_name.startswith('.') and file_name.lower() not in {'.env.example', '.gitignore'}:
                continue
            full_path = root_path / file_name
            rel_path = full_path.relative_to(base_dir)
            if is_excluded_path(rel_path, excluded_dirs):
                continue
            if ignore_matcher and ignore_matcher.matches(rel_path, is_dir=False):
                continue
            if rel_root != Path('.') and not include_hidden and any(part.startswith('.') for part in rel_root.parts):
                continue
            yield rel_path, full_path


def iter_dirs(base_dir: Path, excluded_dirs: set[str], include_hidden: bool = False, ignore_matcher=None) -> Iterator[tuple[Path, Path]]:
    for root, dirs, _ in os.walk(base_dir, topdown=True):
        root_path = Path(root)
        rel_root = root_path.relative_to(base_dir) if root_path != base_dir else Path('.')
        dirs[:] = [
            name for name in sorted(dirs)
            if not is_excluded_name(name, excluded_dirs)
            and (include_hidden or not name.startswith('.'))
            and not (ignore_matcher and ignore_matcher.matches((rel_root / name) if rel_root != Path('.') else Path(name), is_dir=True))
        ]
        for dir_name in list(dirs):
            full_path = root_path / dir_name
            rel_path = full_path.relative_to(base_dir)
            if is_excluded_path(rel_path, excluded_dirs):
                continue
            if ignore_matcher and ignore_matcher.matches(rel_path, is_dir=True):
                continue
            yield rel_path, full_path
