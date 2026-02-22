from argoproxy.config import ArgoConfig
from argoproxy.models import ModelRegistry


def _registry() -> ModelRegistry:
    return ModelRegistry(ArgoConfig(user="tester"))


# --- Candidate transformation: original input (baseline) ---


def test_resolve_by_exact_key() -> None:
    """Original input matches an alias key directly (e.g. 'argo:gpt-4o')."""
    registry = _registry()
    assert registry.resolve_model_name("argo:gpt-4o", "chat") == "gpt4o"


def test_resolve_embed_by_exact_key() -> None:
    """Original input matches an embed alias key directly."""
    registry = _registry()
    assert (
        registry.resolve_model_name("argo:text-embedding-3-small", "embed") == "v3small"
    )


# --- Candidate transformation: internal_id direct match (values) ---


def test_resolve_by_internal_id() -> None:
    """Compact internal_id (e.g. 'gpt4o') matches a value directly."""
    registry = _registry()
    assert registry.resolve_model_name("gpt4o", "chat") == "gpt4o"


def test_resolve_embed_by_internal_id() -> None:
    """Compact internal_id (e.g. 'v3small') matches an embed value directly."""
    registry = _registry()
    assert registry.resolve_model_name("v3small", "embed") == "v3small"


# --- Candidate transformation: slash → colon ---


def test_resolve_chat_model_with_slash_separator() -> None:
    """'argo/gpt-4o' → 'argo:gpt-4o' matches a key."""
    registry = _registry()
    assert registry.resolve_model_name("argo/gpt-4o", "chat") == "gpt4o"


def test_resolve_embed_model_with_slash_separator() -> None:
    """'argo/text-embedding-3-small' → 'argo:text-embedding-3-small' matches a key."""
    registry = _registry()
    assert (
        registry.resolve_model_name("argo/text-embedding-3-small", "embed") == "v3small"
    )


# --- Candidate transformation: case-insensitive ---


def test_resolve_model_name_case_insensitive() -> None:
    """'ARGO/GPT-4O' → lowercased + slash→colon → 'argo:gpt-4o' matches a key."""
    registry = _registry()
    assert registry.resolve_model_name("ARGO/GPT-4O", "chat") == "gpt4o"


def test_resolve_model_name_mixed_case() -> None:
    """'Argo:GPT-4o' → lowercased → 'argo:gpt-4o' matches a key."""
    registry = _registry()
    assert registry.resolve_model_name("Argo:GPT-4o", "chat") == "gpt4o"


# --- Candidate transformation: auto-add 'argo:' prefix ---


def test_resolve_chat_model_with_bare_argo_name() -> None:
    """'gpt-4o' → 'argo:gpt-4o' via auto-prefix matches a key."""
    registry = _registry()
    assert registry.resolve_model_name("gpt-4o", "chat") == "gpt4o"


def test_resolve_embed_model_with_bare_argo_name() -> None:
    """'text-embedding-3-small' → 'argo:text-embedding-3-small' via auto-prefix."""
    registry = _registry()
    assert registry.resolve_model_name("text-embedding-3-small", "embed") == "v3small"


# --- Fallback to default ---


def test_resolve_unknown_model_falls_back_to_default() -> None:
    """Unrecognized model names fall back to the default for each type."""
    registry = _registry()
    assert registry.resolve_model_name("nonexistent-chat-model", "chat") == "gpt4o"
    assert registry.resolve_model_name("nonexistent-embed-model", "embed") == "v3small"
