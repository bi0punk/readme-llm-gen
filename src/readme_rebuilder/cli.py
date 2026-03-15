from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from readme_rebuilder.config import AppSettings, load_settings
from readme_rebuilder.graph.workflow import ReadmeGraphBuilder
from readme_rebuilder.services.discovery_service import DiscoveryService
from readme_rebuilder.services.file_selector_service import FileSelectorService
from readme_rebuilder.services.git_context_service import GitContextService
from readme_rebuilder.services.heuristic_service import HeuristicsService
from readme_rebuilder.services.llm_service import LLMService
from readme_rebuilder.services.tree_service import TreeService
from readme_rebuilder.services.writer_service import WriterService
from readme_rebuilder.utils.logging import setup_logging
from readme_rebuilder.utils.observability import ConsoleRunObserver

app = typer.Typer(help='Generate or rebuild README files for local projects using LangGraph and a local LLM')
console = Console()
logger = logging.getLogger(__name__)


def _build_workflow(settings: AppSettings):
    llm_service = LLMService(settings.llm)
    builder = ReadmeGraphBuilder(
        tree_service=TreeService(settings.scanner),
        file_selector_service=FileSelectorService(settings.scanner),
        heuristics_service=HeuristicsService(settings.scanner.exclude_dirs),
        llm_service=llm_service,
        writer_service=WriterService(settings.output),
        git_context_service=GitContextService(),
        settings=settings,
    )
    workflow = builder.compile()
    return workflow, llm_service


def _render_result_table(results: list[dict]) -> Table:
    table = Table(title='README Rebuilder · Resultado de lote')
    table.add_column('Proyecto', style='cyan')
    table.add_column('README previo', style='white')
    table.add_column('Salida', style='green')
    table.add_column('Estado')
    for item in results:
        status = item.get('status', 'ok')
        status_style = 'green' if status == 'ok' else 'red'
        table.add_row(item.get('project_name', '-'), 'sí' if item.get('had_existing_readme') else 'no', item.get('output_path', '-'), f'[{status_style}]{status}[/]')
    return table


def _show_llm_preflight(preflight: dict) -> None:
    installed = preflight.get('installed_models', [])
    preview = ', '.join(installed[:5])
    if len(installed) > 5:
        preview += ', ...'
    body = (
        f"[bold]Endpoint:[/] {preflight['base_url']}\n"
        f"[bold]Modelo solicitado:[/] {preflight['requested_model']}\n"
        f"[bold]Modelo en uso:[/] {preflight['resolved_model']}\n"
        f"[bold]Fallback automático:[/] {'sí' if preflight['used_fallback'] else 'no'}\n"
        f"[bold]Modelos detectados:[/] {preview or '-'}"
    )
    console.print(Panel.fit(body, title='Preflight LLM', border_style='magenta'))


def _run_single_project(workflow, project_path: Path, overwrite: bool, show_thinking: bool, verbose: bool) -> dict:
    observer = ConsoleRunObserver(console=console, show_thinking=show_thinking, verbose=verbose)
    observer.project_start(project_path)
    try:
        result = workflow.invoke({'project_path': str(project_path), 'overwrite_readme': overwrite, 'observer': observer})
    except Exception as exc:  # noqa: BLE001
        observer.project_error(exc)
        raise
    observer.project_done(result['output_path'], result['analysis_path'])
    return result


def _export_graph_files(workflow, output_dir: Path, stem: str = 'langgraph_workflow') -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = workflow.get_graph()
    mermaid = graph.draw_mermaid()
    mmd_path = output_dir / f'{stem}.mmd'
    png_path = output_dir / f'{stem}.png'
    mmd_path.write_text(mermaid, encoding='utf-8')
    written_png: Path | None = None
    try:
        png_bytes = graph.draw_mermaid_png()
        png_path.write_bytes(png_bytes)
        written_png = png_path
    except Exception:  # noqa: BLE001
        written_png = None
    return mmd_path, written_png


@app.command()
def project(
    project_path: str = typer.Argument(..., help='Path to a local project or repository'),
    config: str = typer.Option('config.yaml', '--config', help='Path to YAML config'),
    model: str | None = typer.Option(None, '--model', help='Override Ollama model for this run'),
    overwrite: bool = typer.Option(False, '--overwrite', help='Replace README.md instead of writing README.generated.md'),
    verbose: bool = typer.Option(False, '--verbose', help='Enable debug logs'),
    show_thinking: bool = typer.Option(False, '--show-thinking', help='Show LLM diagnostic summaries and evidence traces'),
) -> None:
    setup_logging(verbose)
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    workflow, llm_service = _build_workflow(settings)
    _show_llm_preflight(llm_service.preflight())
    path = Path(project_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise typer.BadParameter(f'Ruta inválida: {path}')
    result = _run_single_project(workflow, path, overwrite=overwrite, show_thinking=show_thinking, verbose=verbose)
    console.print(Panel.fit(f"README generado en: {result['output_path']}", title='Salida', border_style='green'))
    console.print(Panel.fit(json.dumps(result['project_profile'], ensure_ascii=False, indent=2), title='Perfil detectado', border_style='blue'))
    console.print(Panel.fit(json.dumps(result['heuristic_facts'], ensure_ascii=False, indent=2), title='Heurísticas', border_style='cyan'))
    console.print(Panel.fit(json.dumps(result['blueprint'], ensure_ascii=False, indent=2), title='Blueprint README', border_style='magenta'))


@app.command()
def batch(
    base_dir: str = typer.Argument(..., help='Base directory containing local projects'),
    config: str = typer.Option('config.yaml', '--config', help='Path to YAML config'),
    model: str | None = typer.Option(None, '--model', help='Override Ollama model for this run'),
    overwrite: bool = typer.Option(False, '--overwrite', help='Replace README.md instead of writing README.generated.md'),
    max_projects: int | None = typer.Option(None, '--max-projects', help='Optional cap for discovered projects'),
    verbose: bool = typer.Option(False, '--verbose', help='Enable debug logs'),
    show_thinking: bool = typer.Option(False, '--show-thinking', help='Show LLM diagnostic summaries and evidence traces'),
) -> None:
    setup_logging(verbose)
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    base_path = Path(base_dir).expanduser().resolve()
    if not base_path.exists() or not base_path.is_dir():
        raise typer.BadParameter(f'Ruta inválida: {base_path}')
    discovery = DiscoveryService(settings.discovery)
    workflow, llm_service = _build_workflow(settings)
    _show_llm_preflight(llm_service.preflight())
    projects = discovery.discover_projects(base_path)
    if max_projects is not None:
        projects = projects[:max_projects]
    if not projects:
        console.print(Panel.fit(f'No se detectaron proyectos en {base_path}', title='Sin resultados', border_style='yellow'))
        raise typer.Exit(code=0)
    console.print(Panel.fit(f"[bold]Base:[/] {base_path}\n[bold]Proyectos detectados:[/] {len(projects)}\n[bold]Overwrite:[/] {'sí' if overwrite else 'no'}", title='Ejecución batch', border_style='cyan'))
    results: list[dict] = []
    with Progress(SpinnerColumn(), TextColumn('[progress.description]{task.description}'), BarColumn(), TextColumn('{task.completed}/{task.total}'), TimeElapsedColumn(), console=console) as progress:
        task_id = progress.add_task('Procesando proyectos', total=len(projects))
        for project_path in projects:
            logger.info('Procesando proyecto: %s', project_path)
            progress.update(task_id, description=f'Procesando {project_path.name}')
            try:
                result = _run_single_project(workflow, project_path, overwrite=overwrite, show_thinking=show_thinking, verbose=verbose)
                results.append({'project_name': result['project_profile'].get('project_name') or project_path.name, 'project_path': str(project_path), 'had_existing_readme': bool(result.get('existing_readme', '').strip()), 'output_path': result.get('output_path', ''), 'status': 'ok'})
            except Exception as exc:  # noqa: BLE001
                logger.exception('Fallo procesando %s', project_path)
                results.append({'project_name': project_path.name, 'project_path': str(project_path), 'had_existing_readme': False, 'output_path': '', 'status': f'error: {exc}'})
            finally:
                progress.advance(task_id)
    report_dir = base_path / settings.output.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    report_json = report_dir / 'batch_report.json'
    report_csv = report_dir / 'batch_report.csv'
    report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    with report_csv.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['project_name', 'project_path', 'had_existing_readme', 'output_path', 'status'])
        writer.writeheader()
        writer.writerows(results)
    console.print(_render_result_table(results))
    console.print(Panel.fit(f'Reportes guardados en: {report_dir}', title='Lote completado', border_style='green'))


@app.command('export-graph')
def export_graph(
    output_dir: str = typer.Option('.', '--output-dir', help='Directory where Mermaid and PNG files will be written'),
    config: str = typer.Option('config.yaml', '--config', help='Path to YAML config'),
    model: str | None = typer.Option(None, '--model', help='Override Ollama model for this run'),
) -> None:
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    workflow, _ = _build_workflow(settings)
    out_dir = Path(output_dir).expanduser().resolve()
    mmd_path, png_path = _export_graph_files(workflow, out_dir)
    body = f'[bold]Mermaid:[/] {mmd_path}'
    if png_path:
        body += f'\n[bold]PNG:[/] {png_path}'
    else:
        body += '\n[bold yellow]PNG:[/] no generado en este entorno; usa el .mmd como fallback.'
    console.print(Panel.fit(body, title='Grafo exportado', border_style='green'))


if __name__ == '__main__':
    app()
