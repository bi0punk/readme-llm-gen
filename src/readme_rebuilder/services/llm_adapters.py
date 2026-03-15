from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Type, TypeVar
from urllib import error, request

from pydantic import BaseModel

from readme_rebuilder.config import LLMSettings

T = TypeVar("T", bound=BaseModel)


class BaseLLMAdapter(ABC):
    backend_name = "unknown"

    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    @abstractmethod
    def fetch_installed_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def build_model(self, model_name: str):
        raise NotImplementedError

    @abstractmethod
    def structured_invoke(self, model, prompt: str, schema: Type[T]) -> T:
        raise NotImplementedError

    def text_invoke(self, model, prompt: str) -> str:
        response = model.invoke(prompt)
        content = getattr(response, 'content', response)
        if isinstance(content, list):
            return json.dumps(content, ensure_ascii=False, indent=2)
        return str(content)

    def source_description(self) -> str:
        return self.backend_name


class OllamaAdapter(BaseLLMAdapter):
    backend_name = 'ollama'

    def build_model(self, model_name: str):
        try:
            from langchain_ollama import ChatOllama
        except ModuleNotFoundError as exc:
            raise RuntimeError('Falta langchain-ollama. Instálala con: pip install langchain-ollama') from exc
        return ChatOllama(
            model=model_name,
            base_url=self.settings.base_url,
            temperature=self.settings.temperature,
            timeout=self.settings.timeout_seconds,
        )

    def fetch_installed_models(self) -> list[str]:
        base = self.settings.base_url.rstrip('/')
        req = request.Request(f'{base}/api/tags', method='GET')
        try:
            with request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except error.URLError as exc:
            raise RuntimeError(
                f'No fue posible contactar Ollama en {self.settings.base_url}. '
                'Verifica que el servicio esté arriba y escuchando en ese puerto.'
            ) from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError('Ollama respondió con un JSON inválido al consultar /api/tags.') from exc
        names = [item.get('name', '').strip() for item in payload.get('models', []) if item.get('name')]
        return sorted(set(names))

    def structured_invoke(self, model, prompt: str, schema: Type[T]) -> T:
        chain = model.with_structured_output(schema)
        return chain.invoke(prompt)

    def source_description(self) -> str:
        return f'ollama · {self.settings.base_url}'


class _JsonStructuredMixin:
    def _extract_first_json_object(self, text: str) -> dict:
        stripped = text.strip()
        if stripped.startswith('```'):
            stripped = '\n'.join(line for line in stripped.splitlines() if not line.strip().startswith('```')).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', stripped, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise RuntimeError(f'El backend no devolvió JSON válido. Respuesta recibida:\n{stripped[:500]}')

    def _structured_prompt(self, prompt: str, schema: Type[T]) -> str:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False, indent=2)
        return (
            f'{prompt}\n\n'
            'Respond ONLY with a valid JSON object matching this schema exactly. '
            'No explanation, no markdown, no code fences.\n\n'
            f'Schema:\n{schema_json}'
        )


class LlamaCppServerAdapter(_JsonStructuredMixin, BaseLLMAdapter):
    backend_name = 'llamacpp'

    def build_model(self, model_name: str):
        try:
            from langchain_openai import ChatOpenAI
        except ModuleNotFoundError as exc:
            raise RuntimeError('Falta langchain-openai. Instálala con: pip install langchain-openai') from exc
        base = self.settings.llamacpp_base_url.rstrip('/')
        return ChatOpenAI(
            base_url=f'{base}/v1',
            api_key='no-key',
            model=model_name,
            temperature=self.settings.temperature,
            max_retries=self.settings.retry_count,
            timeout=self.settings.timeout_seconds,
        )

    def fetch_installed_models(self) -> list[str]:
        base = self.settings.llamacpp_base_url.rstrip('/')
        req = request.Request(f'{base}/v1/models', method='GET')
        try:
            with request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except error.URLError as exc:
            raise RuntimeError(
                f'No fue posible contactar llama.cpp en {self.settings.llamacpp_base_url}. '
                'Asegúrate de que el servidor está corriendo.'
            ) from exc
        except json.JSONDecodeError:
            return ['local-model']
        names = [item.get('id', 'local-model') for item in payload.get('data', [])]
        return sorted(set(names)) or ['local-model']

    def structured_invoke(self, model, prompt: str, schema: Type[T]) -> T:
        response = model.invoke(self._structured_prompt(prompt, schema))
        content = getattr(response, 'content', response)
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        return schema.model_validate(self._extract_first_json_object(str(content)))

    def source_description(self) -> str:
        return f'llama.cpp server · {self.settings.llamacpp_base_url}'


class LlamaCppLocalAdapter(_JsonStructuredMixin, BaseLLMAdapter):
    backend_name = 'llamacpp'

    def build_model(self, model_name: str):
        del model_name
        try:
            from langchain_community.llms import LlamaCpp
        except ModuleNotFoundError as exc:
            raise RuntimeError('Falta llama-cpp-python. Instálala con: pip install llama-cpp-python') from exc
        n_threads = self.settings.llamacpp_n_threads or None
        return LlamaCpp(
            model_path=self.settings.llamacpp_model_path,
            temperature=self.settings.temperature,
            n_ctx=self.settings.llamacpp_n_ctx,
            n_threads=n_threads,
            n_gpu_layers=self.settings.llamacpp_n_gpu_layers,
            verbose=False,
        )

    def fetch_installed_models(self) -> list[str]:
        model_path = Path(self.settings.llamacpp_model_path)
        if not model_path.exists():
            raise RuntimeError(f'Modelo GGUF no encontrado: {self.settings.llamacpp_model_path}')
        return [model_path.stem or model_path.name]

    def structured_invoke(self, model, prompt: str, schema: Type[T]) -> T:
        response = model.invoke(self._structured_prompt(prompt, schema))
        content = getattr(response, 'content', response)
        if isinstance(content, list):
            content = json.dumps(content, ensure_ascii=False)
        return schema.model_validate(self._extract_first_json_object(str(content)))

    def source_description(self) -> str:
        return f'llama.cpp local · {self.settings.llamacpp_model_path}'


def build_adapter(settings: LLMSettings) -> BaseLLMAdapter:
    if settings.backend == 'ollama':
        return OllamaAdapter(settings)
    if settings.backend == 'llamacpp' and settings.llamacpp_model_path:
        return LlamaCppLocalAdapter(settings)
    if settings.backend == 'llamacpp':
        return LlamaCppServerAdapter(settings)
    raise ValueError(f"Backend desconocido: {settings.backend}")
