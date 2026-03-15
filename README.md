# Local README Rebuilder

Proyecto en Python para recorrer directorios locales, detectar proyectos o repositorios, analizar sus archivos clave y generar o reconstruir un `README.md` profesional usando LangGraph y un LLM local vía Ollama.

## Qué hace

- Recorre una carpeta base y detecta proyectos candidatos.
- Revisa si existe un `README` previo y lo usa como contexto secundario.
- Inspecciona árbol de directorios y archivos de alta señal.
- Genera un README nuevo o reconstruido.
- Puede procesar un proyecto individual o una carpeta con múltiples proyectos.
- Guarda además un reporte JSON y CSV del lote.
- Muestra trazas de ejecución en terminal con colores, estado por etapa, rutas analizadas y evidencia de diagnóstico del LLM.

## Stack

- Python 3.11+
- LangGraph
- LangChain
- Ollama
- Typer
- Rich

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
```

## Modelo local

Instala y levanta Ollama, luego descarga un modelo compatible:

```bash
ollama pull qwen2.5-coder:7b
```

## Uso

Procesar un proyecto puntual:

```bash
readme-rebuilder project /ruta/al/proyecto --verbose
```

Procesar un proyecto puntual mostrando trazas de diagnóstico del LLM:

```bash
readme-rebuilder project /ruta/al/proyecto --verbose --show-thinking
```

Procesar un directorio base completo:

```bash
readme-rebuilder batch /ruta/base --verbose
```

Procesar un directorio base completo con salida detallada por proyecto:

```bash
readme-rebuilder batch /ruta/base --verbose --show-thinking
```

Sobrescribir `README.md` en vez de generar `README.generated.md`:

```bash
readme-rebuilder project /ruta/al/proyecto --overwrite
```

## Observabilidad de terminal

La herramienta ahora muestra:

- inicio de análisis por proyecto
- ruta exacta del proyecto
- etapas del flujo LangGraph
- archivos seleccionados para contexto
- heurísticas detectadas
- diagnósticos resumidos del LLM
- ruta de salida del README y del análisis JSON

La opción `--show-thinking` no expone razonamiento interno crudo del modelo. Muestra diagnósticos resumidos, evidencia y salidas intermedias útiles para depuración.

## Salidas

Por cada proyecto se genera:

- `README.generated.md` o `README.md`
- `.readme_rebuilder/analysis.json`

En `analysis.json` se guardan también:

- `selected_file_paths`
- `heuristic_facts`
- `file_insights`
- `project_profile`
- `sections`
- `trace_events`

En modo lote además se genera:

- `.readme_rebuilder/batch_report.json`
- `.readme_rebuilder/batch_report.csv`

## Flujo

```text
Directorio base
   -> descubrimiento de proyectos
   -> resumen del árbol
   -> selección de archivos clave
   -> lectura de README existente
   -> heurísticas locales
   -> análisis con LLM
   -> síntesis del proyecto
   -> generación del README
   -> revisión final
   -> escritura de salida
```


## Notas de operación con Ollama

- El proyecto hace un preflight contra `http://localhost:11434/api/tags` antes de procesar repositorios.
- Si el modelo configurado no existe pero detecta uno compatible instalado, aplica fallback automático y lo informa en terminal.
- Puedes forzar el modelo del run con `--model`, por ejemplo:

```bash
readme-rebuilder batch ~/Documentos --model qwen2.5:7b --verbose --show-thinking
```

- El modo `--verbose` ya no muestra el ruido interno de `httpx/httpcore`; deja visible solo la traza útil del proyecto.


## Notas sobre el árbol de directorios

Esta versión intenta usar el comando del sistema `tree` para capturar una estructura más fiel del proyecto y enviarla como contexto adicional al LLM. Si `tree` no está instalado o falla, el proyecto usa un fallback en Python.

Directorios excluidos por defecto en el árbol: `.git`, `.venv`, `venv`, `env`, `ENV`, `.tox`, `.nox`, `.direnv`, `node_modules`, `dist`, `build`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.idea`, `.vscode`.

Puedes ajustar esto en `config.yaml` con `scanner.tree_mode`, `scanner.tree_timeout_seconds` y `scanner.exclude_dirs`.
