# Local README Rebuilder

Proyecto en Python para recorrer directorios locales, detectar proyectos o repositorios, analizar sus archivos clave y generar o reconstruir un `README.md` profesional usando LangGraph y un LLM local vía Ollama o llama.cpp.

## Qué cambió en esta v2.1

- Adapters LLM formales para Ollama, llama.cpp server y llama.cpp local.
- Soporte para `.readme-rebuilderignore`.
- Diff unificado contra README existente en `.readme_rebuilder/readme.diff`.
- Batch concurrente real con `--concurrency` o `batch.concurrency`.
- Tree y selección de archivos respetan exclusiones del proyecto.
- Suite ampliada para cubrir ignore rules, diff y adapters.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
cp .env.example .env
cp config.yaml config.local.yaml
```

## Backends soportados

### Ollama

```bash
ollama pull qwen2.5:7b
readme-rebuilder project /ruta/al/proyecto --verbose
```

### llama.cpp server

```bash
llama-server -m /ruta/modelo.gguf --host 0.0.0.0 --port 8080
readme-rebuilder project /ruta/al/proyecto --config config.yaml --verbose
```

### llama.cpp local

Configura `llm.backend=llamacpp` y `llm.llamacpp_model_path=/ruta/modelo.gguf`.

## Ignore file del proyecto

Puedes crear un archivo `.readme-rebuilderignore` en la raíz del proyecto analizado.

Ejemplos:

```text
# ignorar directorios
samples/
docs/

# ignorar patrones
artifacts/*.json
src/generated_*.py
```

## Uso

Proyecto individual:

```bash
readme-rebuilder project /ruta/al/proyecto --verbose
```

Sin escribir archivos:

```bash
readme-rebuilder project /ruta/al/proyecto --dry-run
```

Lote con concurrencia:

```bash
readme-rebuilder batch /ruta/base --concurrency 4 --verbose
```

## Salidas

Por cada proyecto se genera:

- `README.generated.md` o `README.md`
- `.readme_rebuilder/analysis.json`
- `.readme_rebuilder/readme.diff`

En modo lote además se genera:

- `.readme_rebuilder/batch_report.json`
- `.readme_rebuilder/batch_report.csv`

## Seguridad y privacidad

- Por defecto `analysis.json` guarda metadatos de archivos seleccionados, no snippets.
- El selector aplica redacción básica de secretos comunes antes de enviar snippets al LLM.
- El diff permite revisar cambios antes de sobrescribir README si prefieres un flujo más controlado.

## Flujo

```text
Directorio base
   -> descubrimiento de proyectos
   -> resumen del árbol
   -> selección primaria de archivos
   -> heurísticas locales
   -> digest de contexto primario
   -> detección de gaps
   -> selección secundaria de archivos
   -> digest de contexto secundario
   -> blueprint README
   -> validación mínima
   -> escritura segura de salida + diff
```

## Desarrollo

```bash
pip install -e .[dev]
pytest -q
```
