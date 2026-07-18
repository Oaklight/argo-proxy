"""Upstream model list fetching and availability checks."""

import fnmatch
import json
from typing import Any

from llm_rosetta._vendor.httpclient import AsyncClient
from pydantic import BaseModel
from tqdm.asyncio import tqdm_asyncio

from ..config import _get_yes_no_input_with_timeout
from ..utils.logging import log_debug, log_error, log_warning
from ..utils.misc import build_user_agent

from .constants import (
    GPT_O_PATTERN,
    _DEFAULT_CHAT_MODELS,
    is_anthropic_model,
)

DEFAULT_TIMEOUT = 30


class Model(BaseModel):
    """Model representation supporting both old and new API formats.

    This class provides backward compatibility for API format changes:
    - Old format: {"id": "gpt35", "model_name": "GPT-3.5 Turbo"}
    - New format: {"id": "GPT-3.5 Turbo", "internal_id": "gpt35", ...}
    """

    id: str
    internal_id: str | None = None
    object: str | None = "model"
    created: int | None = None
    owned_by: str | None = None
    model_name: str | None = None

    @property
    def display_name(self) -> str:
        """Gets the display name, compatible with both old and new formats."""
        if self.model_name:
            return self.model_name
        else:
            return self.id

    @property
    def internal_identifier(self) -> str:
        """Gets the internal identifier, compatible with both old and new formats."""
        if self.internal_id:
            return self.internal_id
        else:
            return self.id


def produce_argo_model_list(upstream_models: list[Model]) -> dict[str, str]:
    """Generates a dictionary mapping standardized Argo model identifiers to their corresponding internal IDs.

    Args:
        upstream_models: A list of Model objects (supports both old and new API formats).

    Returns:
        A dictionary where keys are formatted Argo model identifiers
        (e.g., "argo:gpt-4o", "argo:claude-4-opus") and values are internal IDs.
    """
    argo_models = {}
    for model in upstream_models:
        display_name = model.display_name
        internal_id = model.internal_identifier

        model_name = display_name.replace(" ", "-").lower()

        if fnmatch.fnmatch(internal_id, GPT_O_PATTERN):
            argo_models[f"argo:gpt-{model_name}"] = internal_id

        elif is_anthropic_model(internal_id):
            parts = model_name.split("-")
            if parts[0] == "claude" and len(parts) >= 3:
                # "claude-opus-4.7" → argo:claude-4.7-opus
                _, codename, gen_num, *version = parts
                if version:
                    argo_models[f"argo:claude-{gen_num}-{codename}-{version[0]}"] = (
                        internal_id
                    )
                else:
                    argo_models[f"argo:claude-{gen_num}-{codename}"] = internal_id
            elif len(parts) >= 2:
                # "sonnet-5" → argo:sonnet-5 (handled by regular mapping below)
                # also add swapped alias: argo:5-sonnet
                codename, gen_num, *version = parts
                if version:
                    argo_models[f"argo:{gen_num}-{codename}-{version[0]}"] = internal_id
                else:
                    argo_models[f"argo:{gen_num}-{codename}"] = internal_id

        argo_models[f"argo:{model_name}"] = internal_id

    return argo_models


async def get_upstream_model_list_async(
    url: str,
    resolver_overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """Fetches the list of available models from the upstream server asynchronously.

    Args:
        url: The URL of the upstream server.
        resolver_overrides: Currently unused (kept for API compat).

    Returns:
        A dictionary containing the list of available models mapping
        argo model names to internal IDs.
    """
    log_debug(f"Starting model list fetch from: {url}", context="models")
    raw_data = ""

    try:
        client = AsyncClient(timeout=DEFAULT_TIMEOUT)
        try:
            response = await client.get(url, headers={"User-Agent": build_user_agent()})
        finally:
            await client.aclose()

        status_code = response.status_code
        log_debug(
            f"Received response with status code: {status_code}",
            context="models",
        )

        if status_code != 200:
            log_error(
                f"HTTP error fetching model list from {url}",
                context="models",
            )
            log_error(f"HTTP status code: {status_code}", context="models")
            log_warning("Using built-in model list.", context="models")
            return _DEFAULT_CHAT_MODELS

        raw_data = response.text  # type: ignore[union-attr]
        log_debug(
            f"Response data length: {len(raw_data)} characters",
            context="models",
        )

        data = json.loads(raw_data)
        model_count = len(data.get("data", []))
        log_debug(f"Parsed {model_count} models from API", context="models")

        if data.get("data") and len(data["data"]) > 0:
            sample_model = data["data"][0]
            if "model_name" in sample_model:
                log_debug(
                    "Detected old format API (contains model_name field)",
                    context="models",
                )
            elif "internal_id" in sample_model:
                log_debug(
                    "Detected new format API (contains internal_id field)",
                    context="models",
                )
            else:
                log_warning("Detected unknown format API", context="models")
            log_debug(f"Sample model data: {sample_model}", context="models")

        models = (
            [Model(**model) for model in data.get("data", [])]
            if data.get("data")
            else []
        )

        argo_models = produce_argo_model_list(models)

        if argo_models:
            sample_mappings = list(argo_models.items())[:3]
            log_debug(f"Sample model mappings: {sample_mappings}", context="models")

        return argo_models

    except json.JSONDecodeError as e:
        log_error(
            f"JSON parsing error fetching model list from {url}", context="models"
        )
        log_error(f"JSON error: {e}", context="models")
        log_error(
            f"Response content first 200 chars: {raw_data[:200] if raw_data else 'unknown'}",
            context="models",
        )
        log_warning("Using built-in model list.", context="models")
        return _DEFAULT_CHAT_MODELS

    except Exception as e:
        log_error(f"Error fetching model list from {url}", context="models")
        log_error(f"Error: {type(e).__name__}: {e}", context="models")
        log_warning("Using built-in model list.", context="models")
        return _DEFAULT_CHAT_MODELS


async def _check_model_streamability(
    model_id: str,
    stream_url: str,
    non_stream_url: str,
    user: str,
    payload: dict[str, Any],
) -> tuple[str, bool | None]:
    """Check if a model is streamable using model_id."""
    payload_copy = payload.copy()
    payload_copy["model"] = model_id
    headers = {"Authorization": f"Bearer {user}", "User-Agent": build_user_agent()}

    client = AsyncClient(timeout=DEFAULT_TIMEOUT)
    try:
        resp = await client.post(stream_url, json=payload_copy, headers=headers)
        if resp.status_code < 400:
            return (model_id, True)
    except Exception:
        pass

    try:
        resp = await client.post(non_stream_url, json=payload_copy, headers=headers)
        if resp.status_code < 400:
            return (model_id, False)
    except Exception:
        pass
    finally:
        await client.aclose()

    log_error(f"All attempts failed for model ID: {model_id}", context="models")
    return (model_id, None)


def _categorize_results(
    results: list[tuple[str, bool | None]], model_mapping: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Categorize model check results into streamable/non-streamable/unavailable.
    Maps results back to all aliases using the model_mapping."""
    streamable = set()
    non_streamable = set()
    unavailable = set()

    reverse_mapping = {}
    for alias, model_id in model_mapping.items():
        reverse_mapping.setdefault(model_id, []).append(alias)

    for model_id, status in results:
        aliases = reverse_mapping.get(model_id, [model_id])
        if status is True:
            streamable.update(aliases)
            non_streamable.update(aliases)
        elif status is False:
            non_streamable.update(aliases)
        elif status is None:
            unavailable.update(aliases)

    if unavailable:
        log_warning(f"Unavailable models: {unavailable}", context="models")
        if _get_yes_no_input_with_timeout(
            "Do you want to keep using them? It might be a temporary issue. [Y/n]",
            timeout=5,
        ):
            non_streamable.update(unavailable)
            unavailable.clear()
        else:
            log_error(
                "Proceeding without unavailable models. Subsequent calls to these models will use the configured default fallback",
                context="models",
            )

    return (
        sorted(list(streamable)),
        sorted(list(non_streamable)),
        sorted(list(unavailable)),
    )


async def determine_models_availability(
    stream_url: str, non_stream_url: str, user: str, model_list: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Asynchronously checks which models are streamable.

    Args:
        stream_url: URL for streaming API endpoint.
        non_stream_url: URL for non-streaming API endpoint.
        user: User identifier.
        model_list: Dictionary mapping model aliases to their IDs.

    Returns:
        Tuple of (streamable_models, non_streamable_models, unavailable_models)
        where each list contains all aliases for the models.
    """
    payload = {
        "model": None,
        "messages": [{"role": "user", "content": "What are you?"}],
    }

    unique_model_ids = set(model_list.values())
    tasks = [
        _check_model_streamability(model_id, stream_url, non_stream_url, user, payload)
        for model_id in unique_model_ids
    ]

    results = []
    for coro in tqdm_asyncio.as_completed(
        tasks, total=len(tasks), desc="Checking models"
    ):
        result = await coro
        results.append(result)

    return _categorize_results(results, model_list)
