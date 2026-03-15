from __future__ import annotations

import json
import re
from pathlib import Path

from readme_rebuilder.config import ScannerSettings

# ── Regex compiladas al importar — no se recompilan por archivo ───────────────
_RE_TESTS_TREE  = re.compile(r"(^|\s)tests?/", re.M)
_RE_CI_TREE     = re.compile(r"gitlab-ci", re.I)

_RE_TESTS       = re.compile(r"pytest|unittest|TestCase|describe\(|vitest|jest")
_RE_FLASK       = re.compile(r"from\s+flask|import\s+flask|Flask\(")
_RE_FASTAPI     = re.compile(r"from\s+fastapi|import\s+fastapi|FastAPI\(")
_RE_DJANGO      = re.compile(r"from\s+django|DJANGO_SETTINGS_MODULE|manage\.py")
_RE_STREAMLIT   = re.compile(r"streamlit", re.I)
_RE_CLI         = re.compile(r"typer|argparse|click", re.I)
_RE_WORKER      = re.compile(r"celery|rq\b|worker", re.I)
_RE_LANGGRAPH   = re.compile(r"langgraph|StateGraph|add_node", re.I)
_RE_LANGCHAIN   = re.compile(r"from\s+langchain|import\s+langchain", re.I)
_RE_ENV_VARS    = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
_RE_CMD_PY      = re.compile(r"(python\s+[\w./-]+\.py[^\n]*)")
_RE_CMD_UV      = re.compile(r"(uvicorn\s+[^\n]+)")

# ── Mapas de lookup O(1) ──────────────────────────────────────────────────────
_EXT_LANG: dict[str, str] = {
    '.py': 'Python', '.js': 'JavaScript', '.jsx': 'JavaScript',
    '.ts': 'TypeScript', '.tsx': 'TypeScript', '.go': 'Go',
    '.rs': 'Rust', '.rb': 'Ruby', '.java': 'Java',
    '.kt': 'Kotlin', '.cs': 'C#', '.cpp': 'C++', '.c': 'C',
}

_DOCKER_NAMES = frozenset({'dockerfile', 'docker-compose.yml', 'docker-compose.yaml'})

_ENTRYPOINT_NAMES = frozenset({
    'app.py', 'main.py', 'run.py', 'manage.py', 'server.py', 'api.py',
    'index.js', 'index.ts', 'main.go', 'main.rs',
})

_DEP_MANAGERS: dict[str, str] = {
    'requirements.txt': 'pip',
    'pyproject.toml': 'pip/uv',
    'package.json': 'npm/yarn',
    'go.mod': 'go modules',
    'cargo.toml': 'cargo',
    'gemfile': 'bundler',
    'pom.xml': 'maven',
    'build.gradle': 'gradle',
}


class HeuristicsService:
    def __init__(self, exclude_dirs: list[str] | None = None) -> None:
        # Acepta exclude_dirs por compatibilidad con cli.py aunque no lo use aún
        self._exclude_dirs = set(exclude_dirs or [])

    def derive_project_facts(self, files: list[dict[str, str]], tree_summary: dict, project_path: Path) -> dict:
        languages:          set[str] = set()
        framework_hints:    set[str] = set()
        commands:           set[str] = set()
        env_vars:           set[str] = set()
        entrypoints:        list[str] = []
        project_type_hints: set[str] = set()
        dependency_managers:set[str] = set()

        has_docker   = False
        has_tests    = False
        has_ci       = False
        has_git_repo = (project_path / ".git").exists()

        # ── Detección rápida desde el árbol (sin abrir archivos) ──────────────
        entries_text = "\n".join(tree_summary.get("entries", []))
        if _RE_TESTS_TREE.search(entries_text):
            has_tests = True
        if ".github/" in entries_text or _RE_CI_TREE.search(entries_text):
            has_ci = True
        if "dockerfile" in entries_text.lower() or "docker-compose" in entries_text.lower():
            has_docker = True

        # ── Análisis por archivo ───────────────────────────────────────────────
        for item in files:
            path    = item["path"]
            content = item["content"]
            name    = Path(path).name.lower()
            suffix  = Path(path).suffix.lower()

            # Lenguaje O(1)
            if lang := _EXT_LANG.get(suffix):
                languages.add(lang)

            # Gestor de dependencias O(1)
            if dm := _DEP_MANAGERS.get(name):
                dependency_managers.add(dm)

            # Docker
            if name in _DOCKER_NAMES:
                has_docker = True

            # Tests (early-exit: si ya lo sabemos no re-evaluamos)
            if not has_tests and _RE_TESTS.search(content):
                has_tests = True

            # Frameworks
            if _RE_FLASK.search(content):
                framework_hints.add("Flask")
                project_type_hints.add("web application or API")
            if _RE_FASTAPI.search(content):
                framework_hints.add("FastAPI")
                project_type_hints.add("API service")
            if _RE_DJANGO.search(content) or name == "manage.py":
                framework_hints.add("Django")
                project_type_hints.add("web application")
            if _RE_STREAMLIT.search(content):
                framework_hints.add("Streamlit")
                project_type_hints.add("interactive app")
            if _RE_LANGGRAPH.search(content):
                framework_hints.add("LangGraph")
                project_type_hints.add("AI / LLM pipeline")
            if _RE_LANGCHAIN.search(content):
                framework_hints.add("LangChain")
                project_type_hints.add("AI / LLM pipeline")
            if _RE_CLI.search(content):
                project_type_hints.add("CLI tool")
            if _RE_WORKER.search(content):
                project_type_hints.add("worker or background job")

            # Entrypoints
            if name in _ENTRYPOINT_NAMES:
                entrypoints.append(path)

            # Env vars y comandos
            env_vars.update(_RE_ENV_VARS.findall(content))
            commands.update(cmd.strip() for cmd in _RE_CMD_PY.findall(content))
            commands.update(cmd.strip() for cmd in _RE_CMD_UV.findall(content))

            # package.json: scripts npm
            if name == "package.json":
                try:
                    pkg = json.loads(content)
                    for script_name, script_cmd in pkg.get("scripts", {}).items():
                        commands.add(f"npm run {script_name}  # {script_cmd}")
                except Exception:
                    pass

        if not project_type_hints and entrypoints:
            project_type_hints.add("application")

        return {
            "languages":           sorted(languages),
            "framework_hints":     sorted(framework_hints),
            "dependency_managers": sorted(dependency_managers),
            "commands":            sorted(commands),
            "env_vars":            sorted(env_vars),
            "entrypoints":         entrypoints,
            "has_docker":          has_docker,
            "has_tests":           has_tests,
            "has_ci":              has_ci,
            "has_git_repo":        has_git_repo,
            "project_type_hints":  sorted(project_type_hints),
        }
