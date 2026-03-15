from readme_rebuilder.config import LLMSettings
from readme_rebuilder.services.llm_service import LLMService


def test_preflight_uses_exact_match(monkeypatch):
    service = LLMService(LLMSettings(model='qwen2.5:7b'))
    monkeypatch.setattr(service, '_fetch_installed_models', lambda: ['qwen2.5:7b', 'llama3.1:8b'])
    monkeypatch.setattr(service, '_build_model', lambda model_name: {'model': model_name})
    info = service.preflight()
    assert info['resolved_model'] == 'qwen2.5:7b'
    assert info['used_fallback'] is False


def test_preflight_falls_back_from_coder_to_base(monkeypatch):
    service = LLMService(LLMSettings(model='qwen2.5-coder:7b'))
    monkeypatch.setattr(service, '_fetch_installed_models', lambda: ['qwen2.5:7b'])
    monkeypatch.setattr(service, '_build_model', lambda model_name: {'model': model_name})
    info = service.preflight()
    assert info['resolved_model'] == 'qwen2.5:7b'
    assert info['used_fallback'] is True
