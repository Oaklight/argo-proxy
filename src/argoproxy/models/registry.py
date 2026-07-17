"""ModelRegistry — central model tracking and resolution."""

import asyncio
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from ..config import ArgoConfig
from ..utils.logging import log_debug, log_error, log_info, log_warning

from .constants import (
    NATIVE_TOOL_CALL_MODELS,
    NATIVE_TOOL_CALL_PATTERNS,
    NO_SYS_MSG_MODELS,
    NO_SYS_MSG_PATTERNS,
    OPTION_2_INPUT_MODELS,
    OPTION_2_INPUT_PATTERNS,
    _DEFAULT_CHAT_MODELS,
    _EMBED_MODELS,
    classify_model_family,
    filter_model_by_patterns,
)
from .upstream import (
    determine_models_availability,
    get_upstream_model_list_async,
)


class OpenAIModel(BaseModel):
    """OpenAI-compatible model representation for /v1/models responses."""

    id: str
    internal_name: str
    object: Literal["model"] = "model"
    created: int = int(datetime.now().timestamp())
    owned_by: str = "argo"

    def __init__(self, **data):
        super().__init__(**data)
        if self.owned_by == "argo":
            family = classify_model_family(self.internal_name)
            if family != "unknown":
                self.owned_by = family


class ModelRegistry:
    def __init__(self, config: ArgoConfig):
        self._chat_models: dict[str, str] = {}
        self._no_sys_msg_models = NO_SYS_MSG_MODELS
        self._option_2_input_models = OPTION_2_INPUT_MODELS
        self._native_tool_call_models = NATIVE_TOOL_CALL_MODELS

        self._streamable_models: dict[str, int] = defaultdict(lambda: 0)
        self._non_streamable_models: dict[str, int] = defaultdict(lambda: 0)
        self._unavailable_models: dict[str, int] = defaultdict(lambda: 0)

        self._last_updated: datetime | None = None
        self._refresh_task = None
        self._config = config

    async def initialize(self):
        """Initialize model registry with upstream data."""
        try:
            await self.refresh_availability()
        except Exception as e:
            log_error(
                f"Initial availability check failed: {str(e)}", context="ModelRegistry"
            )

        interval = self._config.model_refresh_interval_hours
        if interval > 0:
            self._refresh_task = asyncio.create_task(
                self._periodic_refresh(interval_hours=interval)
            )
            log_info(
                f"Periodic model refresh enabled: every {interval}h",
                context="ModelRegistry",
            )

    async def refresh_availability(self, real_test: bool = False):
        """Refresh model availability status."""
        if not self._config:
            raise ValueError("Failed to load valid configuration")

        model_url = f"{self._config.native_openai_base_url}/models"

        log_debug(
            f"Fetching models from: {model_url}",
            context="ModelRegistry",
        )
        self._chat_models = await get_upstream_model_list_async(
            model_url,
            resolver_overrides=getattr(self._config, "resolve_overrides", None),
        )

        source = "upstream API" if len(self._chat_models) > 32 else "built-in list"
        log_info(
            f"Model registry initialized: {len(self._chat_models)} models from {source}",
            context="ModelRegistry",
        )

        try:
            if real_test:
                (
                    streamable,
                    non_streamable,
                    unavailable,
                ) = await determine_models_availability(
                    self._config.argo_stream_url,
                    self._config.argo_url,
                    self._config.user,
                    self.available_chat_models,
                )
            else:
                streamable = self.available_chat_models.keys()
                non_streamable = self.available_chat_models.keys()
                unavailable = []

            for name in streamable:
                self._streamable_models[name]
            for name in non_streamable:
                self._non_streamable_models[name]
            for name in unavailable:
                self._unavailable_models[name]
            self._last_updated = datetime.now()

            self._no_sys_msg_models = filter_model_by_patterns(
                self.available_chat_models, NO_SYS_MSG_PATTERNS
            )

            self._option_2_input_models = filter_model_by_patterns(
                self.available_chat_models, OPTION_2_INPUT_PATTERNS
            )

            self._native_tool_call_models = filter_model_by_patterns(
                self.available_chat_models, NATIVE_TOOL_CALL_PATTERNS
            )

            log_debug(
                "Model availability refreshed successfully", context="ModelRegistry"
            )
        except Exception as e:
            log_error(
                f"Failed to refresh model availability: {str(e)}",
                context="ModelRegistry",
            )
            if not self._last_updated:
                self._chat_models = _DEFAULT_CHAT_MODELS
                log_warning(
                    "Falling back to default model list", context="ModelRegistry"
                )

    async def _periodic_refresh(self, interval_hours: float):
        """Background task that refreshes the model list on a fixed interval."""
        try:
            while True:
                await asyncio.sleep(interval_hours * 3600)
                log_info(
                    f"Periodic model refresh triggered (every {interval_hours}h)",
                    context="ModelRegistry",
                )
                try:
                    await self.refresh_availability()
                except Exception as e:
                    log_error(
                        f"Periodic refresh failed: {e!s}",
                        context="ModelRegistry",
                    )
        except asyncio.CancelledError:
            log_debug(
                "Periodic model refresh task cancelled",
                context="ModelRegistry",
            )

    async def manual_refresh(self):
        """Trigger manual refresh of model data."""
        try:
            await self.refresh_availability(real_test=True)
        except Exception as e:
            log_error(f"Manual refresh failed: {str(e)}", context="ModelRegistry")

    def _model_lookup_candidates(self, model_name: str) -> list[str]:
        """Build equivalent model-name candidates for flexible lookup.

        The ``available_models`` dict uses ``argo:xxx`` keys (e.g.
        ``argo:gpt-4o``) mapped to compact ``internal_id`` values (e.g.
        ``gpt4o``).  ``resolve_model_name`` already checks both keys and
        values, so passing an ``internal_id`` directly (like ``gpt4o``)
        will match without any extra transformation here.

        Candidate transformations kept:
        - Original input: baseline behaviour.
        - ``/`` → ``:`` : URL path segments use ``/``; Argo keys use ``:``.
        - Lowercasing: defensive against case mismatches.
        - ``argo:`` prefix addition: lets users omit the prefix
          (e.g. ``gpt-4o`` → ``argo:gpt-4o`` matches a key).
        """
        raw = model_name.strip()
        if not raw:
            return []

        candidates: list[str] = []

        def _add(candidate: str) -> None:
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        _add(raw)

        if "/" in raw:
            _add(raw.replace("/", ":"))

        _add(raw.lower())
        if "/" in raw:
            _add(raw.replace("/", ":").lower())

        for c in list(candidates):
            if not c.startswith("argo:"):
                _add(f"argo:{c}")

        stripped = re.sub(r"[^a-z0-9]", "", raw.lower())
        _add(stripped)

        date_stripped = re.sub(r"-\d{8}$", "", raw)
        if date_stripped != raw:
            _add(date_stripped)
            _add(date_stripped.lower())
            if not date_stripped.startswith("argo:"):
                _add(f"argo:{date_stripped.lower()}")
            _add(re.sub(r"[^a-z0-9]", "", date_stripped.lower()))

        return candidates

    def resolve_model_name(
        self,
        model_name: str,
        model_type: Literal["chat", "embed"],
        as_is: bool = False,
    ) -> str:
        """Resolves a model name to its primary model name using the flattened model mapping.

        Args:
            model_name: The input model name to resolve.
            model_type: The type of model to resolve (chat or embed).
            as_is: If True, return the original model name unchanged when no
                match is found instead of falling back to a default model.

        Returns:
            The resolved primary model name, the original model name (when
            *as_is* is True and no match is found), or a default model.
        """
        for candidate in self._model_lookup_candidates(model_name):
            if candidate in self.available_models.values():
                return candidate
            if candidate in self.available_models:
                return self.available_models[candidate]

        if as_is:
            log_warning(
                f"Model '{model_name}' not found in registry, passing through as-is",
                context="ModelRegistry",
            )
            return model_name

        if model_type == "chat":
            default_model = self._config.default_chat_model
        elif model_type == "embed":
            default_model = self._config.default_embed_model
        else:
            default_model = self._config.default_chat_model
            log_warning(
                f"Unknown model_type '{model_type}', using chat fallback",
                context="ModelRegistry",
            )
        log_warning(
            f"Model '{model_name}' not found in registry, falling back to {default_model}",
            context="ModelRegistry",
        )
        if default_model in self.available_models:
            return self.available_models[default_model]
        log_warning(
            f"Default fallback model '{default_model}' not in registry either",
            context="ModelRegistry",
        )
        return default_model

    def as_openai_list(self) -> dict[str, Any]:
        model_data: dict[str, Any] = {"object": "list", "data": []}

        for model_name, model_id in self.available_models.items():
            model_data["data"].append(
                OpenAIModel(id=model_name, internal_name=model_id).model_dump()
            )

        return model_data

    def flag_as_non_streamable(self, model_name: str):
        self._streamable_models.pop(model_name, 0)
        self._non_streamable_models[model_name]

    def flag_as_streamable(self, model_name: str):
        self._non_streamable_models.pop(model_name, 0)
        self._streamable_models[model_name]

    def flag_as_unavailable(self, model_name: str):
        self._unavailable_models[model_name]
        self._streamable_models.pop(model_name, 0)
        self._non_streamable_models.pop(model_name, 0)

    @property
    def available_chat_models(self):
        return self._chat_models or _DEFAULT_CHAT_MODELS

    @property
    def available_embed_models(self):
        return _EMBED_MODELS

    @property
    def available_models(self):
        return {**self.available_chat_models, **self.available_embed_models}

    @property
    def unavailable_models(self):
        return list(self._unavailable_models.keys())

    @property
    def streamable_models(self):
        return list(self._streamable_models.keys())

    @property
    def non_streamable_models(self):
        return list(self._non_streamable_models.keys()) or list(
            _DEFAULT_CHAT_MODELS.keys()
        )

    @property
    def no_sys_msg_models(self):
        return self._no_sys_msg_models or NO_SYS_MSG_MODELS

    @property
    def option_2_input_models(self):
        return self._option_2_input_models or OPTION_2_INPUT_MODELS

    @property
    def native_tool_call_models(self):
        return self._native_tool_call_models or NATIVE_TOOL_CALL_MODELS

    @property
    def unique_model_count(self) -> int:
        """Get the count of unique models (not aliases)."""
        return len(set(self.available_models.values()))

    @property
    def alias_count(self) -> int:
        """Get the count of all aliases (including model names)."""
        return len(self.available_models)

    def resolve_model_target(
        self,
        resolved_model: str,
        config: ArgoConfig,
    ) -> tuple[Literal["openai_chat", "anthropic"], str]:
        """Map a resolved model name to its upstream provider and URL.

        Args:
            resolved_model: The internal model ID (e.g. "gpt4o", "claudesonnet4").
            config: The ArgoConfig instance for URL resolution.

        Returns:
            Tuple of (provider_type, upstream_url).
        """
        family = classify_model_family(resolved_model)
        if family == "anthropic":
            return ("anthropic", f"{config.native_anthropic_base_url}/v1/messages")
        return ("openai_chat", f"{config.native_openai_base_url}/chat/completions")

    def get_model_stats(self) -> dict:
        """Get detailed model statistics including model family breakdown."""
        unique_models = set(self.available_models.values())
        chat_models = set(self.available_chat_models.values())
        embed_models = set(self.available_embed_models.values())

        family_counts = {"openai": 0, "anthropic": 0, "google": 0, "unknown": 0}
        chat_family_counts = {"openai": 0, "anthropic": 0, "google": 0, "unknown": 0}
        embed_family_counts = {"openai": 0, "anthropic": 0, "google": 0, "unknown": 0}

        chat_family_alias_counts = {
            "openai": 0,
            "anthropic": 0,
            "google": 0,
            "unknown": 0,
        }
        embed_family_alias_counts = {
            "openai": 0,
            "anthropic": 0,
            "google": 0,
            "unknown": 0,
        }

        for model_id in unique_models:
            family = classify_model_family(model_id)
            family_counts[family] += 1

            if model_id in chat_models:
                chat_family_counts[family] += 1
            elif model_id in embed_models:
                embed_family_counts[family] += 1

        for alias, model_id in self.available_chat_models.items():
            family = classify_model_family(model_id)
            chat_family_alias_counts[family] += 1

        for alias, model_id in self.available_embed_models.items():
            family = classify_model_family(model_id)
            embed_family_alias_counts[family] += 1

        return {
            "total_aliases": len(self.available_models),
            "unique_models": len(unique_models),
            "unique_chat_models": len(chat_models),
            "unique_embed_models": len(embed_models),
            "chat_aliases": len(self.available_chat_models),
            "embed_aliases": len(self.available_embed_models),
            "family_counts": family_counts,
            "chat_family_counts": chat_family_counts,
            "embed_family_counts": embed_family_counts,
            "chat_family_alias_counts": chat_family_alias_counts,
            "embed_family_alias_counts": embed_family_alias_counts,
        }
