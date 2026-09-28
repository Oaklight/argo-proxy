"""Bridge between ArgoConfig and llm-rosetta GatewayConfig.

Converts the ARGO YAML-based configuration into the raw dict format
that :class:`GatewayConfig` expects, allowing argo-proxy to use the
gateway's proxy pipeline while keeping its own config system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from llm_rosetta.gateway.config import GatewayConfig

from .models.constants import classify_model_family, supports_native_responses

if TYPE_CHECKING:
    from .config.model import ArgoConfig
    from .models.registry import ModelRegistry


_SHIM_NAME_MAP: dict[str, str] = {
    "anthropic": "argo--anthropic",
    "openai_chat": "argo--openai_chat",
}


def build_gateway_config(
    argo_config: ArgoConfig,
    model_registry: ModelRegistry,
) -> GatewayConfig:
    """Build a :class:`GatewayConfig` from ARGO's config and model registry.

    The resulting config has two providers ("argo-anthropic" and
    "argo-openai") backed by the ARGO upstream URLs, and a model table
    built from the live :class:`ModelRegistry`.

    With ``native_responses`` on, a third provider speaking the Responses
    API is added and ``prefer_same_format`` enabled, so ``/v1/responses``
    reaches ARGO's own Responses endpoint unconverted.
    """
    native = argo_config.native_responses
    providers = _build_providers(argo_config, native_responses=native)
    models = _build_models(model_registry, native_responses=native)

    raw: dict = {
        "providers": providers,
        "models": models,
        "server": {
            "host": argo_config.host,
            "port": argo_config.port,
            # Prefer the provider already speaking the client's wire format.
            "prefer_same_format": native,
        },
        "debug": {
            "verbose": argo_config.verbose,
            "log_bodies": False,
            "error_dumps": argo_config.dump_requests,
        },
    }
    if argo_config.socket:
        raw["server"]["socket"] = argo_config.socket
    if argo_config.data_dir:
        raw["server"]["data_dir"] = argo_config.data_dir

    return GatewayConfig(raw)


def _build_providers(config: ArgoConfig, *, native_responses: bool = True) -> dict:
    providers: dict = {
        "argo-openai": {
            "shim": "argo--openai_chat",
            "api_key": config.user,
            "base_url": config.native_openai_base_url,
            "readonly": True,
            "embedding_format": "openai",
        },
        "argo-anthropic": {
            "shim": "argo--anthropic",
            "api_key": config.user,
            "base_url": config.native_anthropic_base_url,
            "readonly": True,
        },
    }
    if native_responses:
        # Same host as argo-openai -- only the wire format differs.
        providers["argo-openai-responses"] = {
            "shim": "argo--openai_responses",
            "api_key": config.user,
            "base_url": config.native_openai_base_url,
            "readonly": True,
        }
    return providers


def _build_models(registry: ModelRegistry, *, native_responses: bool = True) -> dict:
    """Map every model alias to a provider based on family classification."""
    embed_models = set(registry.available_embed_models)
    models: dict = {}
    for alias, model_id in registry.available_models.items():
        family = classify_model_family(model_id)
        if family == "anthropic":
            provider_name = "argo-anthropic"
        else:
            provider_name = "argo-openai"
        if alias in embed_models:
            capabilities = ["embedding"]
        else:
            capabilities = ["text", "vision", "tools", "reasoning"]
        entry: dict
        if (
            native_responses
            and alias not in embed_models
            and supports_native_responses(model_id)
        ):
            # Gemini is non-anthropic too but 500s on ARGO's Responses
            # endpoint, hence the probe-verified gate rather than the
            # anthropic/else split. A source matching neither dialect
            # round-robins across the pair -- see tests.
            entry = {
                "providers": [provider_name, "argo-openai-responses"],
                "capabilities": capabilities,
            }
        else:
            entry = {
                "provider": provider_name,
                "capabilities": capabilities,
            }
        if alias in embed_models:
            entry["type"] = "embedding"
        if model_id != alias:
            entry["upstream_model"] = model_id
        models[alias] = entry
    return models


def rebuild_gateway_models(
    gateway_config: GatewayConfig,
    model_registry: ModelRegistry,
) -> None:
    """Rebuild the model routing table in-place after a model refresh.

    Called by the ``/refresh`` endpoint when the upstream model list
    changes at runtime. The native-responses flag is read back off
    *gateway_config* so a refresh cannot disagree with the running
    routing.
    """
    new_models = _build_models(
        model_registry,
        native_responses=getattr(gateway_config, "prefer_same_format", False),
    )
    # Re-parse through GatewayConfig's model parser
    models, capabilities, upstream_names = GatewayConfig._parse_models(
        new_models, gateway_config._raw_providers
    )
    gateway_config.models = models
    gateway_config.model_capabilities = capabilities
    gateway_config.model_upstream_names = upstream_names
