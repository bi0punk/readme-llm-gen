from __future__ import annotations

from typing import Any, TypedDict


class GraphState(TypedDict, total=False):
    project_path: str
    overwrite_readme: bool
    dry_run: bool
    save_analysis_json: bool
    observer: Any
    tree_summary: dict
    primary_files: list[dict[str, str]]
    primary_file_paths: list[str]
    secondary_files: list[dict[str, str]]
    secondary_file_paths: list[str]
    selected_files: list[dict[str, str]]
    selected_file_paths: list[str]
    existing_readme: str
    heuristic_facts: dict
    git_context: dict
    primary_context: dict
    secondary_context: dict
    info_gaps: list[str]
    blueprint: dict
    project_profile: dict
    output_path: str
    analysis_path: str
    trace_events: list[dict]
