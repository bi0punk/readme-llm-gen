from __future__ import annotations

import json
from typing import Type, TypeVar

from pydantic import BaseModel

from readme_rebuilder.config import LLMSettings
from readme_rebuilder.services.llm_adapters import build_adapter

T = TypeVar('T', bound=BaseModel)


class LLMService:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self.observer = None
        self.requested_model = settings.model
        self.resolved_model = settings.model
        self.model = None
        self.adapter = build_adapter(settings)

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
            'qwen2.5:7b', 'qwen2.5-coder:7b', 'qwen2.5:3b',
            'llama3.1:8b', 'mistral:7b', 'phi4:14b',
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

    def _build_model(self, model_name: str):
        return self.adapter.build_model(model_name)

    def _fetch_installed_models(self) -> list[str]:
        return self.adapter.fetch_installed_models()

    def _ensure_model(self) -> None:
        if self.model is None:
            self.model = self._build_model(self.resolved_model)

    def _summarize_model_output(self, value: BaseModel | str) -> tuple[str, str | None]:
        if isinstance(value, BaseModel):
            data = value.model_dump()
            compact = json.dumps(data, ensure_ascii=False, indent=2)
            if 'project_name' in data and 'inferred_goal' in data:
                return f"{data['project_name']} · contexto sintetizado", compact[:1600]
            if 'gaps' in data:
                return f"Gaps detectados: {', '.join(data['gaps'][:4]) or 'ninguno'}", compact[:1400]
            if 'title' in data and 'tagline' in data:
                return f"Secciones listas · {data['title'][:80]}", compact[:1600]
            return 'Salida estructurada generada', compact[:1600]
        text = str(value).strip()
        first_line = text.splitlines()[0][:140] if text else 'sin contenido'
        return first_line, text[:1400] if text else None

    def preflight(self) -> dict:
        installed = self._fetch_installed_models()

        if self.settings.backend == 'llamacpp':
            requested = self.settings.llamacpp_model_path or self.requested_model or 'server'
            resolved = installed[0] if installed else 'local-model'
            self.resolved_model = resolved
            self.model = self._build_model(resolved)
            return {
                'base_url': self.settings.llamacpp_base_url,
                'requested_model': requested,
                'resolved_model': resolved,
                'used_fallback': requested != resolved and not self.settings.llamacpp_model_path,
                'installed_models': installed,
                'backend': 'llamacpp',
                'source': self.adapter.source_description(),
            }

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
            'backend': 'ollama',
            'source': self.adapter.source_description(),
        }

    def structured(self, prompt: str, schema: Type[T], label: str = 'structured_call') -> T:
        self._ensure_model()
        if self.observer:
            self.observer.llm_prompt(label=label, prompt=prompt)
            self.observer.llm_start(label=label, prompt_chars=len(prompt), schema_name=schema.__name__)

        last_error: Exception | None = None
        for attempt in range(self.settings.retry_count + 1):
            try:
                result = self.adapter.structured_invoke(self.model, prompt, schema)
                if self.observer:
                    summary, excerpt = self._summarize_model_output(result)
                    self.observer.llm_result(label=label, summary=summary, raw_excerpt=excerpt)
                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.settings.retry_count:
                    break
        raise RuntimeError(f'Fallo la llamada estructurada al LLM ({label}): {last_error}') from last_error

    def text(self, prompt: str, label: str = 'text_call') -> str:
        self._ensure_model()
        if self.observer:
            self.observer.llm_prompt(label=label, prompt=prompt)
            self.observer.llm_start(label=label, prompt_chars=len(prompt), schema_name=None)
        rendered = self.adapter.text_invoke(self.model, prompt)
        if self.observer:
            summary, excerpt = self._summarize_model_output(rendered)
            self.observer.llm_result(label=label, summary=summary, raw_excerpt=excerpt)
        return rendered
