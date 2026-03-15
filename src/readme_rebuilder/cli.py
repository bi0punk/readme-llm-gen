from __future__ import annotations

import csv
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _build_workflow(settings: AppSettings, fast: bool = False):
    llm_service = LLMService(settings.llm)
    builder = ReadmeGraphBuilder(
        tree_service=TreeService(settings.scanner),
        file_selector_service=FileSelectorService(settings.scanner),
        heuristics_service=HeuristicsService(settings.scanner.exclude_dirs),
        llm_service=llm_service,
        writer_service=WriterService(settings.output),
        git_context_service=GitContextService(),
        settings=settings,
        fast=fast,
    )
    workflow = builder.compile()
    return workflow, llm_service


def _render_result_table(results: list[dict]) -> Table:
    table = Table(title='README Rebuilder · Resultado de lote')
    table.add_column('Proyecto', style='cyan')
    table.add_column('README previo', style='white')
    table.add_column('Salida', style='green')
    table.add_column('Diff', style='magenta')
    table.add_column('Estado')
    for item in results:
        status = item.get('status', 'ok')
        status_style = 'green' if status == 'ok' else 'red'
        table.add_row(
            item.get('project_name', '-'),
            'sí' if item.get('had_existing_readme') else 'no',
            item.get('output_path', '-'),
            'sí' if item.get('diff_changed') else 'no',
            f'[{status_style}]{status}[/]',
        )
    return table


def _show_llm_preflight(preflight: dict) -> None:
    installed = preflight.get('installed_models', [])
    preview = ', '.join(installed[:5])
    if len(installed) > 5:
        preview += ', ...'
    body = (
        f"[bold]Backend:[/] {preflight.get('backend', '-')}\n"
        f"[bold]Endpoint:[/] {preflight['base_url']}\n"
        f"[bold]Modelo solicitado:[/] {preflight['requested_model']}\n"
        f"[bold]Modelo en uso:[/] {preflight['resolved_model']}\n"
        f"[bold]Fallback automático:[/] {'sí' if preflight['used_fallback'] else 'no'}\n"
        f"[bold]Origen:[/] {preflight.get('source', '-')}\n"
        f"[bold]Modelos detectados:[/] {preview or '-'}"
    )
    console.print(Panel.fit(body, title='Preflight LLM', border_style='magenta'))


def _run_single_project(
    workflow,
    project_path: Path,
    overwrite: bool,
    show_thinking: bool,
    verbose: bool,
    debug_llm: bool = False,
    dry_run: bool = False,
    save_analysis_json: bool = True,
) -> dict:
    observer = ConsoleRunObserver(console=console, show_thinking=show_thinking, verbose=verbose, debug_llm=debug_llm)
    observer.project_start(project_path)
    try:
        result = workflow.invoke({
            'project_path': str(project_path),
            'overwrite_readme': overwrite,
            'observer': observer,
            'dry_run': dry_run,
            'save_analysis_json': save_analysis_json,
        })
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


def _run_batch_worker(settings: AppSettings, project_path: Path, *, fast: bool, overwrite: bool, show_thinking: bool, verbose: bool, debug_llm: bool, dry_run: bool, save_analysis_json: bool) -> dict:
    workflow, _ = _build_workflow(settings, fast=fast)
    result = _run_single_project(
        workflow,
        project_path,
        overwrite=overwrite,
        show_thinking=show_thinking,
        verbose=verbose,
        debug_llm=debug_llm,
        dry_run=dry_run,
        save_analysis_json=save_analysis_json,
    )
    return {
        'project_name': result['project_profile'].get('project_name') or project_path.name,
        'project_path': str(project_path),
        'had_existing_readme': bool(result.get('had_existing_readme')),
        'output_path': result.get('output_path', ''),
        'analysis_path': result.get('analysis_path', ''),
        'diff_path': result.get('diff_path', ''),
        'diff_changed': bool(result.get('diff_changed')),
        'status': 'ok',
    }


@app.command()
def project(
    project_path: str = typer.Argument(..., help='Path to a local project or repository'),
    config: str = typer.Option('config.yaml', '--config', help='Path to YAML config'),
    model: str | None = typer.Option(None, '--model', help='Override configured model for this run'),
    overwrite: bool = typer.Option(False, '--overwrite', help='Replace README.md instead of writing README.generated.md'),
    fast: bool = typer.Option(False, '--fast', help='Reduced prompt (~3x faster on 7B models, slightly less detail)'),
    dry_run: bool = typer.Option(False, '--dry-run', help='Run analysis without writing output files'),
    no_analysis_json: bool = typer.Option(False, '--no-analysis-json', help='Do not write analysis.json for this run'),
    verbose: bool = typer.Option(False, '--verbose', help='Enable debug logs'),
    show_thinking: bool = typer.Option(False, '--show-thinking', help='Show LLM diagnostic summaries and evidence traces'),
    debug_llm: bool = typer.Option(False, '--debug-llm', help='Print full prompt sent to LLM and raw response'),
) -> None:
    setup_logging(verbose)
    path = Path(project_path).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise typer.BadParameter(f'Ruta inválida: {path}')
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    workflow, llm_service = _build_workflow(settings, fast=fast)
    _show_llm_preflight(llm_service.preflight())
    if fast:
        console.print(Panel.fit('[bold yellow]Modo fast activo[/] — prompt reducido y más económico.', border_style='yellow'))
    result = _run_single_project(
        workflow,
        path,
        overwrite=overwrite,
        show_thinking=show_thinking,
        verbose=verbose,
        debug_llm=debug_llm,
        dry_run=dry_run,
        save_analysis_json=not no_analysis_json,
    )
    body = f"README generado en: {result['output_path']}"
    if result.get('diff_path'):
        body += f"\nDiff: {result['diff_path']}"
    console.print(Panel.fit(body, title='Salida', border_style='green'))
    console.print(Panel.fit(json.dumps(result['project_profile'], ensure_ascii=False, indent=2), title='Perfil detectado', border_style='blue'))


@app.command()
def batch(
    base_dir: str = typer.Argument(..., help='Base directory containing local projects'),
    config: str = typer.Option('config.yaml', '--config', help='Path to YAML config'),
    model: str | None = typer.Option(None, '--model', help='Override configured model for this run'),
    overwrite: bool = typer.Option(False, '--overwrite', help='Replace README.md instead of writing README.generated.md'),
    fast: bool = typer.Option(False, '--fast', help='Reduced prompt (~3x faster on 7B models, slightly less detail)'),
    dry_run: bool = typer.Option(False, '--dry-run', help='Run analysis without writing output files'),
    no_analysis_json: bool = typer.Option(False, '--no-analysis-json', help='Do not write analysis.json for this run'),
    max_projects: int | None = typer.Option(None, '--max-projects', help='Optional cap for discovered projects'),
    concurrency: int | None = typer.Option(None, '--concurrency', min=1, help='Parallel workers for batch processing'),
    verbose: bool = typer.Option(False, '--verbose', help='Enable debug logs'),
    show_thinking: bool = typer.Option(False, '--show-thinking', help='Show LLM diagnostic summaries and evidence traces'),
    debug_llm: bool = typer.Option(False, '--debug-llm', help='Print full prompt sent to LLM and raw response'),
) -> None:
    setup_logging(verbose)
    settings = load_settings(config)
    if model:
        settings.llm.model = model
    base_path = Path(base_dir).expanduser().resolve()
    if not base_path.exists() or not base_path.is_dir():
        raise typer.BadParameter(f'Ruta inválida: {base_path}')
    discovery = DiscoveryService(settings.discovery)
    workflow, llm_service = _build_workflow(settings, fast=fast)
    _show_llm_preflight(llm_service.preflight())
    projects = discovery.discover_projects(base_path)
    if max_projects is not None:
        projects = projects[:max_projects]
    if not projects:
        console.print(Panel.fit(f'No se detectaron proyectos en {base_path}', title='Sin resultados', border_style='yellow'))
        raise typer.Exit(code=0)
    workers = concurrency or settings.batch.concurrency
    console.print(Panel.fit(
        f"[bold]Base:[/] {base_path}\n"
        f"[bold]Proyectos detectados:[/] {len(projects)}\n"
        f"[bold]Overwrite:[/] {'sí' if overwrite else 'no'}\n"
        f"[bold]Modo fast:[/] {'sí' if fast else 'no'}\n"
        f"[bold]Dry run:[/] {'sí' if dry_run else 'no'}\n"
        f"[bold]Concurrencia:[/] {workers}",
        title='Ejecución batch', border_style='cyan',
    ))
    results: list[dict] = []
    with Progress(SpinnerColumn(), TextColumn('[progress.description]{task.description}'), BarColumn(), TextColumn('{task.completed}/{task.total}'), TimeElapsedColumn(), console=console) as progress:
        task_id = progress.add_task('Procesando proyectos', total=len(projects))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _run_batch_worker,
                    settings,
                    p,
                    fast=fast,
                    overwrite=overwrite,
                    show_thinking=show_thinking,
                    verbose=verbose,
                    debug_llm=debug_llm,
                    dry_run=dry_run,
                    save_analysis_json=not no_analysis_json,
                ): p
                for p in projects
            }
            for future in as_completed(futures):
                p = futures[future]
                progress.update(task_id, description=f'Finalizando {p.name}')
                try:
                    results.append(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.exception('Fallo procesando %s', p)
                    results.append({
                        'project_name': p.name,
                        'project_path': str(p),
                        'had_existing_readme': False,
                        'output_path': '',
                        'analysis_path': '',
                        'diff_path': '',
                        'diff_changed': False,
                        'status': f'error: {exc}',
                    })
                finally:
                    progress.advance(task_id)

    results.sort(key=lambda item: item.get('project_name', '').lower())
    report_dir = base_path / settings.output.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / 'batch_report.json'
    csv_path = report_dir / 'batch_report.csv'
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    with csv_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['project_name', 'project_path', 'had_existing_readme', 'output_path', 'analysis_path', 'diff_path', 'diff_changed', 'status'])
        writer.writeheader()
        writer.writerows(results)

    console.print(_render_result_table(results))
    console.print(Panel.fit(f'JSON: {json_path}\nCSV: {csv_path}', title='Reportes batch', border_style='green'))


@app.command('export-graph')
def export_graph(
    output_dir: str = typer.Argument('.', help='Directory where the graph files will be written'),
    config: str = typer.Option('config.yaml', '--config', help='Path to YAML config'),
    fast: bool = typer.Option(False, '--fast', help='Export the fast workflow variant'),
) -> None:
    settings = load_settings(config)
    workflow, _ = _build_workflow(settings, fast=fast)
    mmd_path, png_path = _export_graph_files(workflow, Path(output_dir).expanduser().resolve())
    body = f'[bold]Mermaid:[/] {mmd_path}'
    if png_path:
        body += f'\n[bold]PNG:[/] {png_path}'
    console.print(Panel.fit(body, title='Grafo exportado', border_style='cyan'))


if __name__ == '__main__':
    app()
