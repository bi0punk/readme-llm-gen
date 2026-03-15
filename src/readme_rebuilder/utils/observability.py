from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


STEP_TITLES = {
    # nombres actuales del grafo
    "gather_context":   "Contexto paralelo (tree + git + archivos)",
    "run_heuristics":   "Heurísticas locales",
    "build_primary_context": "Síntesis primaria con LLM",
    "detect_information_gaps": "Detección de huecos",
    "enrich_context": "Enriquecimiento de contexto",
    "build_blueprint":  "Construcción del blueprint README",
    "validate_blueprint": "Validación del blueprint",
    "write_outputs":    "Escritura de artefactos",
    # nombres legacy (por si se usan en tests o análisis JSON previos)
    "scan_tree":                  "Escaneo del árbol",
    "select_primary_files":       "Selección primaria de archivos",
    "select_key_files":           "Selección de archivos clave",
    "summarize_primary_context":  "Síntesis primaria con LLM",
    "detect_information_gaps":    "Detección de huecos",
    "select_secondary_files":     "Selección secundaria de archivos",
    "summarize_secondary_context":"Síntesis secundaria con LLM",
}


@dataclass
class ConsoleRunObserver:
    console: Console
    show_thinking: bool = False
    verbose: bool = False
    debug_llm: bool = False          # --debug-llm: muestra prompt completo + respuesta raw
    events: list[dict[str, Any]] = field(default_factory=list)
    _timers: dict[str, float] = field(default_factory=dict)
    _pending_prompts: dict[str, str] = field(default_factory=dict)  # label → prompt
    current_project: str | None = None
    current_project_path: str | None = None

    def _emit_event(self, kind: str, **payload: Any) -> None:
        self.events.append({"ts": time.time(), "kind": kind, **payload})

    def project_start(self, project_path: Path) -> None:
        self.current_project = project_path.name
        self.current_project_path = str(project_path)
        body = (
            f"[bold]Proyecto:[/] {project_path.name}\n"
            f"[bold]Ruta:[/] {project_path}\n"
            f"[bold]Modo diagnóstico LLM:[/] {'activo' if self.show_thinking else 'resumido'}\n"
            f"[bold]Debug LLM completo:[/] {'activo' if self.debug_llm else 'no'}"
        )
        self.console.print(Panel.fit(body, title="Inicio de análisis", border_style="cyan"))
        self._emit_event("project_start", project_name=project_path.name, project_path=str(project_path))

    def project_done(self, output_path: str, analysis_path: str) -> None:
        body = (
            f"[bold green]README generado:[/] {output_path}\n"
            f"[bold]Análisis:[/] {analysis_path}"
        )
        self.console.print(Panel.fit(body, title="Proyecto completado", border_style="green"))
        self._emit_event("project_done", output_path=output_path, analysis_path=analysis_path)

    def project_error(self, exc: Exception) -> None:
        self.console.print(Panel.fit(str(exc), title="Error procesando proyecto", border_style="red"))
        self._emit_event("project_error", error=str(exc))

    def step_start(self, step_name: str) -> None:
        label = STEP_TITLES.get(step_name, step_name)
        self._timers[step_name] = time.perf_counter()
        self.console.print(f"[bold cyan]→[/] {label} [dim]({step_name})[/]")
        self._emit_event("step_start", step=step_name, label=label)

    def step_done(self, step_name: str, summary: str | None = None) -> None:
        label = STEP_TITLES.get(step_name, step_name)
        started = self._timers.get(step_name, time.perf_counter())
        elapsed = time.perf_counter() - started
        line = Text()
        line.append("✓ ", style="bold green")
        line.append(label, style="green")
        line.append(f" · {elapsed:.2f}s", style="dim")
        if summary:
            line.append(f" · {summary}", style="white")
        self.console.print(line)
        self._emit_event("step_done", step=step_name, label=label, elapsed_seconds=round(elapsed, 3), summary=summary or "")

    def selected_files(self, files: Iterable[str]) -> None:
        paths = list(files)
        table = Table(title="Archivos seleccionados", show_lines=False)
        table.add_column("#", style="cyan", width=4)
        table.add_column("Ruta", style="white")
        for idx, path in enumerate(paths, start=1):
            table.add_row(str(idx), path)
        self.console.print(table)
        self._emit_event("selected_files", files=paths)

    def heuristics(self, facts: dict[str, Any]) -> None:
        table = Table(title="Señales detectadas")
        table.add_column("Hecho", style="cyan")
        table.add_column("Valor", style="white")
        for key in [
            "languages",
            "framework_hints",
            "project_type_hints",
            "dependency_managers",
            "entrypoints",
            "has_docker",
            "has_tests",
            "has_ci",
            "has_git_repo",
            "git_branch",
            "git_remotes",
        ]:
            value = facts.get(key, [])
            if isinstance(value, list):
                rendered = ", ".join(str(v) for v in value) if value else "-"
            else:
                rendered = str(value)
            table.add_row(key, rendered)
        self.console.print(table)
        self._emit_event("heuristics", facts=facts)

    # ── Métodos LLM — aquí está el nuevo debug_llm ───────────────────────────

    def llm_prompt(self, label: str, prompt: str) -> None:
        """Llamado por llm_service justo antes de invocar el modelo.
        Solo imprime si debug_llm=True."""
        self._pending_prompts[label] = prompt
        if not self.debug_llm:
            return
        self.console.print(Rule(f"[bold magenta]PROMPT → {label}[/] ({len(prompt)} chars)", style="magenta"))
        # Syntax highlight básico: el prompt es texto plano pero Syntax lo hace
        # scrollable y con número de líneas, más fácil de leer en terminal.
        self.console.print(Syntax(prompt, "text", theme="monokai", word_wrap=True, line_numbers=True))
        self.console.print(Rule(style="magenta dim"))
        self._emit_event("llm_prompt", label=label, prompt=prompt)

    def llm_start(self, label: str, prompt_chars: int, schema_name: str | None = None) -> None:
        meta = f"{prompt_chars} chars"
        if schema_name:
            meta += f" · schema={schema_name}"
        self.console.print(f"[magenta]⋯[/] LLM: {label} [dim]({meta})[/]")
        self._emit_event("llm_start", label=label, prompt_chars=prompt_chars, schema=schema_name)

    def llm_result(self, label: str, summary: str, raw_excerpt: str | None = None) -> None:
        self.console.print(f"[bold magenta]↳[/] {label}: {summary}")
        if self.debug_llm and raw_excerpt:
            self.console.print(Rule(f"[bold magenta]RESPUESTA ← {label}[/]", style="magenta"))
            self.console.print(Syntax(raw_excerpt, "json", theme="monokai", word_wrap=True, line_numbers=True))
            self.console.print(Rule(style="magenta dim"))
        elif self.show_thinking and raw_excerpt:
            self.console.print(Panel.fit(raw_excerpt, title=f"Diagnóstico LLM · {label}", border_style="magenta"))
        self._emit_event("llm_result", label=label, summary=summary, raw_excerpt=raw_excerpt or "")

    def info(self, title: str, body: str, style: str = "blue") -> None:
        self.console.print(Panel.fit(body, title=title, border_style=style))
        self._emit_event("info", title=title, body=body)
