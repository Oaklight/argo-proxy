"""Tests for the ArgoConfig -> GatewayConfig bridge.

Routing tests need llm-rosetta features that are in no release yet, so
they skip rather than fail on an older install.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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
    native_responses = True
    native_openai_base_url = "https://example.com/v1"
    native_anthropic_base_url = "https://example.com"

    def __init__(self, *, native_responses: bool = True) -> None:
        self.native_responses = native_responses


def fake_registry() -> SimpleNamespace:
    return SimpleNamespace(
        available_models=dict(MODELS),
        available_embed_models=set(EMBED_MODELS),
    )


def _responses_shim_available() -> bool:
    """True when the installed llm-rosetta can build the bridge routing."""
    try:
        gc = build_gateway_config(FakeConfig(), fake_registry())
    except Exception:  # noqa: BLE001 - older releases reject the provider
        return False
    return (
        getattr(gc, "prefer_same_format", False)
        and gc.provider_types.get("argo-openai-responses") == "openai_responses"
    )


requires_native_routing = pytest.mark.skipif(
    not _responses_shim_available(),
    reason="needs llm-rosetta with the argo--openai_responses shim "
    "and server.prefer_same_format",
)


# ---------------------------------------------------------------------------
# Provider table
# ---------------------------------------------------------------------------


class TestBuildProviders:
    def test_adds_responses_provider_when_enabled(self):
        providers = _build_providers(FakeConfig(), native_responses=True)
        assert set(providers) == {
            "argo-openai",
            "argo-anthropic",
            "argo-openai-responses",
        }
        responses = providers["argo-openai-responses"]
        assert responses["shim"] == "argo--openai_responses"
        assert responses["base_url"] == providers["argo-openai"]["base_url"]

    def test_omits_responses_provider_when_disabled(self):
        providers = _build_providers(FakeConfig(), native_responses=False)
        assert set(providers) == {"argo-openai", "argo-anthropic"}


# ---------------------------------------------------------------------------
# Model table
# ---------------------------------------------------------------------------


class TestBuildModels:
    def test_gpt_models_get_both_providers(self):
        models = _build_models(fake_registry(), native_responses=True)
        for alias in ("gpt-5", "gpt-5.6-sol"):
            assert models[alias]["providers"] == [
                "argo-openai",
                "argo-openai-responses",
            ]
            assert "provider" not in models[alias]

    def test_claude_and_gemini_keep_single_provider(self):
        """Gemini 500s on ARGO's Responses endpoint; the probe guards this."""
        models = _build_models(fake_registry(), native_responses=True)
        assert models["claude-opus-4-6"]["provider"] == "argo-anthropic"
        assert models["gemini-2.5-pro"]["provider"] == "argo-openai"
        assert "providers" not in models["claude-opus-4-6"]
        assert "providers" not in models["gemini-2.5-pro"]

    def test_embedding_model_keeps_single_provider(self):
        models = _build_models(fake_registry(), native_responses=True)
        entry = models["text-embedding-3-small"]
        assert entry["provider"] == "argo-openai"
        assert entry["type"] == "embedding"
        assert "providers" not in entry

    def test_disabled_matches_pre_bridge_shape(self):
        models = _build_models(fake_registry(), native_responses=False)
        assert all("providers" not in e for e in models.values())
        assert models["gpt-5"]["provider"] == "argo-openai"
        assert models["claude-opus-4-6"]["provider"] == "argo-anthropic"

    def test_upstream_model_preserved(self):
        models = _build_models(fake_registry(), native_responses=True)
        assert models["gpt-5"]["upstream_model"] == "gpt5"
        assert models["claude-opus-4-6"]["upstream_model"] == "claudeopus4.6"


# ---------------------------------------------------------------------------
# Server flag
# ---------------------------------------------------------------------------


class TestPreferSameFormat:
    @requires_native_routing
    def test_enabled_follows_toggle(self):
        gc = build_gateway_config(FakeConfig(native_responses=True), fake_registry())
        assert gc.prefer_same_format is True

    def test_disabled_follows_toggle(self):
        gc = build_gateway_config(FakeConfig(native_responses=False), fake_registry())
        assert getattr(gc, "prefer_same_format", False) is False


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@requires_native_routing
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
