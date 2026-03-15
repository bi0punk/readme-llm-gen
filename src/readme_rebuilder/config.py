from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    temperature: float = 0.1


class DiscoverySettings(BaseModel):
    max_depth: int = 3
    include_hidden: bool = False
    exclude_dirs: list[str] = Field(default_factory=list)
    project_markers: list[str] = Field(default_factory=list)


class ScannerSettings(BaseModel):
    max_files: int = 18
    max_file_chars: int = 10000
    max_total_chars: int = 85000
    max_tree_entries: int = 250
    max_tree_depth: int = 4
    tree_mode: str = "system_auto"
    tree_timeout_seconds: int = 8
    exclude_dirs: list[str] = Field(default_factory=list)
    important_file_patterns: list[str] = Field(default_factory=list)


class OutputSettings(BaseModel):
    readme_name: str = "README.generated.md"
    report_dir: str = ".readme_rebuilder"
    save_analysis_json: bool = True


class AppSettings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(config_path: str | Path = "config.yaml") -> AppSettings:
    load_dotenv()
    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    env_override: dict[str, Any] = {
        "llm": {
            "base_url": os.getenv("OLLAMA_BASE_URL") or raw.get("llm", {}).get("base_url", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL") or raw.get("llm", {}).get("model", "qwen2.5:7b"),
            "temperature": float(os.getenv("OLLAMA_TEMPERATURE") or raw.get("llm", {}).get("temperature", 0.1)),
        },
        "scanner": {
            "max_files": int(os.getenv("MAX_FILES") or raw.get("scanner", {}).get("max_files", 18)),
            "max_file_chars": int(os.getenv("MAX_FILE_CHARS") or raw.get("scanner", {}).get("max_file_chars", 10000)),
            "max_total_chars": int(os.getenv("MAX_TOTAL_CHARS") or raw.get("scanner", {}).get("max_total_chars", 85000)),
            "max_tree_entries": int(raw.get("scanner", {}).get("max_tree_entries", 250)),
            "max_tree_depth": int(raw.get("scanner", {}).get("max_tree_depth", 4)),
            "tree_mode": os.getenv("TREE_MODE") or raw.get("scanner", {}).get("tree_mode", "system_auto"),
            "tree_timeout_seconds": int(os.getenv("TREE_TIMEOUT_SECONDS") or raw.get("scanner", {}).get("tree_timeout_seconds", 8)),
            "exclude_dirs": raw.get("scanner", {}).get("exclude_dirs", []),
            "important_file_patterns": raw.get("scanner", {}).get("important_file_patterns", []),
        },
        "discovery": {
            "max_depth": int(raw.get("discovery", {}).get("max_depth", 3)),
            "include_hidden": bool(raw.get("discovery", {}).get("include_hidden", False)),
            "exclude_dirs": raw.get("discovery", {}).get("exclude_dirs", []),
            "project_markers": raw.get("discovery", {}).get("project_markers", []),
        },
        "output": {
            "readme_name": os.getenv("OUTPUT_README") or raw.get("output", {}).get("readme_name", "README.generated.md"),
            "report_dir": raw.get("output", {}).get("report_dir", ".readme_rebuilder"),
            "save_analysis_json": bool(raw.get("output", {}).get("save_analysis_json", True)),
        },
    }

    merged = _deep_merge(raw, env_override)
    return AppSettings.model_validate(merged)
