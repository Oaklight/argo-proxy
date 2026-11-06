"""Tests for the ArgoConfig -> GatewayConfig bridge."""

from __future__ import annotations

from types import SimpleNamespace

from argoproxy.bridge import (
    _build_models,
    _build_providers,
    build_gateway_config,
    rebuild_gateway_models,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MODELS = {
    "gpt-5": "gpt5",
    "gpt-5.6-sol": "gpt5.6-sol",
    "claude-opus-4-6": "claudeopus4.6",
    "gemini-2.5-pro": "gemini25pro",
    "text-embedding-3-small": "v3small",
}
EMBED_MODELS = {"text-embedding-3-small"}


class FakeConfig:
    host = "127.0.0.1"
    port = 44497
    socket = ""
    user = "test-user"
    verbose = False
    dump_requests = False
    data_dir = ""
    native_openai_base_url = "https://example.com/v1"
    native_anthropic_base_url = "https://example.com"


def fake_registry() -> SimpleNamespace:
    return SimpleNamespace(
        available_models=dict(MODELS),
        available_embed_models=set(EMBED_MODELS),
    )


# ---------------------------------------------------------------------------
# Provider table
# ---------------------------------------------------------------------------


class TestBuildProviders:
    def test_has_all_three_providers(self):
        providers = _build_providers(FakeConfig())
        assert set(providers) == {
            "argo-openai",
            "argo-anthropic",
            "argo-openai-responses",
        }
        responses = providers["argo-openai-responses"]
        assert responses["shim"] == "argo--openai_responses"
        assert responses["base_url"] == providers["argo-openai"]["base_url"]


# ---------------------------------------------------------------------------
# Model table
# ---------------------------------------------------------------------------


class TestBuildModels:
    def test_gpt_models_get_both_providers(self):
        models = _build_models(fake_registry())
        for alias in ("gpt-5", "gpt-5.6-sol"):
            assert models[alias]["providers"] == [
                "argo-openai",
                "argo-openai-responses",
            ]
            assert "provider" not in models[alias]

    def test_claude_and_gemini_keep_single_provider(self):
        models = _build_models(fake_registry())
        assert models["claude-opus-4-6"]["provider"] == "argo-anthropic"
        assert models["gemini-2.5-pro"]["provider"] == "argo-openai"
        assert "providers" not in models["claude-opus-4-6"]
        assert "providers" not in models["gemini-2.5-pro"]

    def test_embedding_model_keeps_single_provider(self):
        models = _build_models(fake_registry())
        entry = models["text-embedding-3-small"]
        assert entry["provider"] == "argo-openai"
        assert entry["type"] == "embedding"
        assert "providers" not in entry

    def test_upstream_model_preserved(self):
        models = _build_models(fake_registry())
        assert models["gpt-5"]["upstream_model"] == "gpt5"
        assert models["claude-opus-4-6"]["upstream_model"] == "claudeopus4.6"


# ---------------------------------------------------------------------------
# Server flag
# ---------------------------------------------------------------------------


class TestPreferSameFormat:
    def test_enabled(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        assert gc.prefer_same_format is True


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


class TestResolution:
    def test_responses_source_reaches_responses_provider(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        route, _info = gc.resolve("openai_responses", "gpt-5")
        assert route.provider_name == "argo-openai-responses"
        assert route.target_provider == "openai_responses"

    def test_chat_source_reaches_chat_provider(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        route, _info = gc.resolve("openai_chat", "gpt-5")
        assert route.provider_name == "argo-openai"
        assert route.target_provider == "openai_chat"

    def test_claude_unaffected_by_the_extra_provider(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        for source in ("openai_responses", "openai_chat", "anthropic"):
            route, _info = gc.resolve(source, "claude-opus-4-6")
            assert route.provider_name == "argo-anthropic"

    def test_gemini_never_reaches_the_responses_provider(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        for source in ("openai_responses", "openai_chat"):
            route, _info = gc.resolve(source, "gemini-2.5-pro")
            assert route.provider_name == "argo-openai"

    def test_embeddings_route_outside_the_chat_table(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        assert "text-embedding-3-small" not in gc.models
        assert gc.embedding_models["text-embedding-3-small"] == "argo-openai"

    def test_unmatched_source_round_robins_documented_limitation(self):
        """Reachable only via /v1/messages with a gpt* model.

        Both conversions work, so this picks between two working paths.
        Pinned so an upstream change surfaces here.
        """
        gc = build_gateway_config(FakeConfig(), fake_registry())
        seen = {gc.resolve("anthropic", "gpt-5")[0].provider_name for _ in range(20)}
        assert seen == {"argo-openai", "argo-openai-responses"}

    def test_rebuild_preserves_dual_provider_entries(self):
        gc = build_gateway_config(FakeConfig(), fake_registry())
        registry = fake_registry()
        registry.available_models["gpt-6"] = "gpt6"

        rebuild_gateway_models(gc, registry)

        assert "gpt-6" in gc.models
        route, _info = gc.resolve("openai_responses", "gpt-6")
        assert route.provider_name == "argo-openai-responses"
        route, _info = gc.resolve("openai_chat", "gpt-5")
        assert route.provider_name == "argo-openai"
