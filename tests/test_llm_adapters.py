from readme_rebuilder.config import LLMSettings
from readme_rebuilder.services.llm_adapters import LlamaCppLocalAdapter, LlamaCppServerAdapter, OllamaAdapter, build_adapter


def test_build_adapter_for_ollama():
    adapter = build_adapter(LLMSettings(backend='ollama'))
    assert isinstance(adapter, OllamaAdapter)


def test_build_adapter_for_llamacpp_server():
    adapter = build_adapter(LLMSettings(backend='llamacpp', llamacpp_model_path=''))
    assert isinstance(adapter, LlamaCppServerAdapter)


def test_build_adapter_for_llamacpp_local():
    adapter = build_adapter(LLMSettings(backend='llamacpp', llamacpp_model_path='/tmp/model.gguf'))
    assert isinstance(adapter, LlamaCppLocalAdapter)
