from argoproxy.config import ArgoConfig
from argoproxy.models import ModelRegistry


def _registry() -> ModelRegistry:
    return ModelRegistry(ArgoConfig(user="tester"))


def test_resolve_chat_model_with_slash_separator() -> None:
    registry = _registry()
    assert registry.resolve_model_name("argo/gpt-4o", "chat") == "gpt4o"


def test_resolve_chat_model_with_bare_argo_name() -> None:
    registry = _registry()
    assert registry.resolve_model_name("gpt-4o", "chat") == "gpt4o"


def test_resolve_embed_model_with_slash_separator() -> None:
    registry = _registry()
    assert (
        registry.resolve_model_name("argo/text-embedding-3-small", "embed") == "v3small"
    )


def test_resolve_embed_model_with_bare_argo_name() -> None:
    registry = _registry()
    assert registry.resolve_model_name("text-embedding-3-small", "embed") == "v3small"


def test_resolve_model_name_case_insensitive() -> None:
    registry = _registry()
    assert registry.resolve_model_name("ARGO/GPT-4O", "chat") == "gpt4o"


def test_resolve_unknown_model_falls_back_to_default() -> None:
    registry = _registry()
    assert registry.resolve_model_name("nonexistent-chat-model", "chat") == "gpt4o"
    assert registry.resolve_model_name("nonexistent-embed-model", "embed") == "v3small"
