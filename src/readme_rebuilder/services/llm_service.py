from __future__ import annotations

import json
from typing import Type, TypeVar
from urllib import error, request

from pydantic import BaseModel

from readme_rebuilder.config import LLMSettings

T = TypeVar('T', bound=BaseModel)


class LLMService:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self.observer = None
        self.requested_model = settings.model
        self.resolved_model = settings.model
        self.model = None

    def _build_model(self, model_name: str):
        try:
            from langchain_ollama import ChatOllama
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                'Falta la dependencia langchain-ollama. Instálala con: pip install -e .'
            ) from exc

        return ChatOllama(
            model=model_name,
            base_url=self.settings.base_url,
            temperature=self.settings.temperature,
        )

    def _ensure_model(self) -> None:
        if self.model is None:
            self.model = self._build_model(self.resolved_model)

    def set_observer(self, observer) -> None:
        self.observer = observer

    def clear_observer(self) -> None:
        self.observer = None

    def _normalize_model_name(self, value: str) -> str:
        return value.removesuffix(':latest')

    def _fallback_candidates(self, requested: str) -> list[str]:
        requested_norm = self._normalize_model_name(requested)
        candidates: list[str] = []
        if '-coder:' in requested:
            candidates.append(requested.replace('-coder:', ':'))
        if requested.endswith('-coder'):
            candidates.append(requested[:-6])
        candidates.extend([
            'qwen2.5:7b',
            'qwen2.5-coder:7b',
            'qwen2.5:3b',
            'llama3.1:8b',
            'mistral:7b',
            'phi4:14b',
        ])
        dedup: list[str] = []
        seen: set[str] = {requested, requested_norm}
        for candidate in candidates:
            norm = self._normalize_model_name(candidate)
            if candidate in seen or norm in seen:
                continue
            dedup.append(candidate)
            seen.add(candidate)
            seen.add(norm)
        return dedup

    def _fetch_installed_models(self) -> list[str]:
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

        models = payload.get('models', [])
        names = [item.get('name', '').strip() for item in models if item.get('name')]
        return sorted(set(names))

    def preflight(self) -> dict:
        installed = self._fetch_installed_models()
        installed_norm = {self._normalize_model_name(name): name for name in installed}
        requested = self.requested_model
        requested_norm = self._normalize_model_name(requested)

        if requested in installed:
            resolved = requested
            used_fallback = False
        elif requested_norm in installed_norm:
            resolved = installed_norm[requested_norm]
            used_fallback = resolved != requested
        else:
            resolved = ''
            used_fallback = False
            for candidate in self._fallback_candidates(requested):
                candidate_norm = self._normalize_model_name(candidate)
                if candidate in installed:
                    resolved = candidate
                    used_fallback = True
                    break
                if candidate_norm in installed_norm:
                    resolved = installed_norm[candidate_norm]
                    used_fallback = True
                    break

        if not resolved:
            available = ', '.join(installed[:8]) if installed else 'sin modelos instalados'
            raise RuntimeError(
                f"El modelo configurado '{requested}' no está instalado en Ollama. "
                f"Modelos detectados: {available}. "
                'Puedes corregirlo con --model, OLLAMA_MODEL o editando config.yaml.'
            )

        if resolved != self.resolved_model or self.model is None:
            self.resolved_model = resolved
            self.model = self._build_model(resolved)

        return {
            'base_url': self.settings.base_url,
            'requested_model': requested,
            'resolved_model': self.resolved_model,
            'used_fallback': used_fallback,
            'installed_models': installed,
        }

    def _summarize_model_output(self, value: BaseModel | str) -> tuple[str, str | None]:
        if isinstance(value, BaseModel):
            data = value.model_dump()
            compact = json.dumps(data, ensure_ascii=False, indent=2)
            if 'path' in data and 'purpose' in data:
                return f"{data['path']} · {data['purpose'][:120]}", compact[:1400]
            if 'project_name' in data and 'one_liner' in data:
                return f"{data['project_name']} · {data['one_liner'][:120]}", compact[:1600]
            if 'summary' in data and 'missing_sections' in data:
                missing = ', '.join(data.get('missing_sections', [])[:3]) or 'sin vacíos críticos'
                return f'README previo evaluado · faltantes: {missing}', compact[:1400]
            if 'title' in data and 'tagline' in data:
                return f"Secciones listas · {data['title'][:80]}", compact[:1600]
            return 'Salida estructurada generada', compact[:1600]

        text = str(value).strip()
        first_line = text.splitlines()[0][:140] if text else 'sin contenido'
        return first_line, text[:1400] if text else None

    def structured(self, prompt: str, schema: Type[T], label: str = 'structured_call') -> T:
        self._ensure_model()
        if self.observer:
            self.observer.llm_start(label=label, prompt_chars=len(prompt), schema_name=schema.__name__)
        chain = self.model.with_structured_output(schema)
        result = chain.invoke(prompt)
        if self.observer:
            summary, excerpt = self._summarize_model_output(result)
            self.observer.llm_result(label=label, summary=summary, raw_excerpt=excerpt)
        return result

    def text(self, prompt: str, label: str = 'text_call') -> str:
        self._ensure_model()
        if self.observer:
            self.observer.llm_start(label=label, prompt_chars=len(prompt), schema_name=None)
        response = self.model.invoke(prompt)
        content = getattr(response, 'content', response)
        if isinstance(content, list):
            rendered = json.dumps(content, ensure_ascii=False, indent=2)
        else:
            rendered = str(content)
        if self.observer:
            summary, excerpt = self._summarize_model_output(rendered)
            self.observer.llm_result(label=label, summary=summary, raw_excerpt=excerpt)
        return rendered
