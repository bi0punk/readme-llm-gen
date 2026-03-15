from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator


class LLMSettings(BaseModel):
    backend: Literal["ollama", "llamacpp"] = "ollama"

    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"

    llamacpp_base_url: str = "http://localhost:8080"
    llamacpp_model_path: str = ""
    llamacpp_n_ctx: int = 4096
    llamacpp_n_threads: int = 0
    llamacpp_n_gpu_layers: int = 0

    temperature: float = 0.1
    timeout_seconds: int = 90
    retry_count: int = 2

    @field_validator("base_url", "llamacpp_base_url")
    @classmethod
    def _strip_trailing_slashes(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, value: float) -> float:
        if not 0 <= value <= 2:
            raise ValueError("temperature must be between 0 and 2")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("timeout_seconds must be > 0")
        return value

    @field_validator("retry_count")
    @classmethod
    def _validate_retry(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retry_count must be >= 0")
        return value

    @model_validator(mode="after")
    def _validate_llamacpp_settings(self) -> "LLMSettings":
        if self.backend == "llamacpp" and self.llamacpp_model_path:
            expanded = Path(self.llamacpp_model_path).expanduser()
            self.llamacpp_model_path = str(expanded)
        return self


class DiscoverySettings(BaseModel):
    max_depth: int = 3
    include_hidden: bool = False
    exclude_dirs: list[str] = Field(default_factory=list)
    project_markers: list[str] = Field(default_factory=list)


class ScannerSettings(BaseModel):
    max_files: int = 12
    max_file_chars: int = 3500
    max_total_chars: int = 28000
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
    persist_source_snippets: bool = False
    redact_secrets: bool = True
    write_atomically: bool = True
    save_readme_diff: bool = True
    diff_context_lines: int = 3


class BatchSettings(BaseModel):
    concurrency: int = 2

    @field_validator('concurrency')
    @classmethod
    def _validate_concurrency(cls, value: int) -> int:
        if value <= 0:
            raise ValueError('concurrency must be > 0')
        return value


class AppSettings(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    discovery: DiscoverySettings = Field(default_factory=DiscoverySettings)
    scanner: ScannerSettings = Field(default_factory=ScannerSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    batch: BatchSettings = Field(default_factory=BatchSettings)


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
            "backend": os.getenv("LLM_BACKEND") or raw.get("llm", {}).get("backend", "ollama"),
            "base_url": os.getenv("OLLAMA_BASE_URL") or raw.get("llm", {}).get("base_url", "http://localhost:11434"),
            "model": os.getenv("OLLAMA_MODEL") or raw.get("llm", {}).get("model", "qwen2.5:7b"),
            "llamacpp_base_url": os.getenv("LLAMACPP_BASE_URL") or raw.get("llm", {}).get("llamacpp_base_url", "http://localhost:8080"),
            "llamacpp_model_path": os.getenv("LLAMACPP_MODEL_PATH") or raw.get("llm", {}).get("llamacpp_model_path", ""),
            "llamacpp_n_ctx": int(os.getenv("LLAMACPP_N_CTX") or raw.get("llm", {}).get("llamacpp_n_ctx", 4096)),
            "llamacpp_n_threads": int(os.getenv("LLAMACPP_N_THREADS") or raw.get("llm", {}).get("llamacpp_n_threads", 0)),
            "llamacpp_n_gpu_layers": int(os.getenv("LLAMACPP_N_GPU_LAYERS") or raw.get("llm", {}).get("llamacpp_n_gpu_layers", 0)),
            "temperature": float(os.getenv("LLM_TEMPERATURE") or raw.get("llm", {}).get("temperature", 0.1)),
            "timeout_seconds": int(os.getenv("LLM_TIMEOUT_SECONDS") or raw.get("llm", {}).get("timeout_seconds", 90)),
            "retry_count": int(os.getenv("LLM_RETRY_COUNT") or raw.get("llm", {}).get("retry_count", 2)),
        },
        "scanner": {
            "max_files": int(os.getenv("MAX_FILES") or raw.get("scanner", {}).get("max_files", 12)),
            "max_file_chars": int(os.getenv("MAX_FILE_CHARS") or raw.get("scanner", {}).get("max_file_chars", 3500)),
            "max_total_chars": int(os.getenv("MAX_TOTAL_CHARS") or raw.get("scanner", {}).get("max_total_chars", 28000)),
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
            "persist_source_snippets": bool(raw.get("output", {}).get("persist_source_snippets", False)),
            "redact_secrets": bool(raw.get("output", {}).get("redact_secrets", True)),
            "write_atomically": bool(raw.get("output", {}).get("write_atomically", True)),
            "save_readme_diff": bool(raw.get("output", {}).get("save_readme_diff", True)),
            "diff_context_lines": int(raw.get("output", {}).get("diff_context_lines", 3)),
        },
        "batch": {
            "concurrency": int(os.getenv("BATCH_CONCURRENCY") or raw.get("batch", {}).get("concurrency", 2)),
        },
    }

    merged = _deep_merge(raw, env_override)
    return AppSettings.model_validate(merged)
