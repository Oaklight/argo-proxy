"""Universal dispatch module — core of argo-proxy v3.0.0.

Routes any client API format (OpenAI Chat, OpenAI Responses, Anthropic Messages,
Google GenAI) to the optimal upstream (native Anthropic for Claude, OpenAI Chat
for everything else), using llm-rosetta for cross-format conversion.

When source and target formats match, requests pass through without conversion.
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
from collections.abc import Callable
from typing import Any, Union

import aiohttp
from aiohttp import web

from llm_rosetta import get_converter_for_provider
from llm_rosetta.auto_detect import ProviderType
from llm_rosetta.converters.base.context import ConversionContext, StreamContext
from llm_rosetta.shims.provider_shim import ProviderShim, get_shim
from llm_rosetta.shims.providers import load_providers
from llm_rosetta.shims.transforms import apply_transforms

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..utils.image_processing import process_anthropic_images, process_openai_images
from ..utils.logging import (
    clear_request_user,
    log_converted_request,
    log_debug,
    log_error,
    log_info,
    log_original_request,
    log_upstream_error,
    log_warning,
    set_request_user,
)
from ..utils.misc import (
    ARGO_AUTH_ERROR_MESSAGE,
    apply_username_passthrough,
    check_response_for_argo_warning,
    contains_argo_auth_warning,
    should_use_username_passthrough,
)
from ..utils.tool_calls import reorder_parallel_tool_calls

# ---------------------------------------------------------------------------
# SSE formatting (IR events → source-format SSE text)
# ---------------------------------------------------------------------------


def _format_sse_data_only(chunk: dict[str, Any]) -> str:
    """SSE with data field only (OpenAI Chat, Google)."""
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _format_sse_event_data(chunk: dict[str, Any]) -> str:
    """SSE with event + data fields (Anthropic, OpenAI Responses)."""
    event_type = chunk.get("type", "unknown")
    return f"event: {event_type}\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"


_SSE_FORMATTERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "openai_chat": _format_sse_data_only,
    "openai_responses": _format_sse_event_data,
    "anthropic": _format_sse_event_data,
    "google": _format_sse_data_only,
}


# ---------------------------------------------------------------------------
# SSE parsing (upstream → chunks)
# ---------------------------------------------------------------------------


def _parse_sse_line(line: str) -> tuple[str, str] | None:
    """Parse a single SSE line into (field, value), or None."""
    if not line:
        return None
    if line.startswith("data: "):
        return ("data", line[6:])
    if line.startswith("event: "):
        return ("event", line[7:])
    return None


def _is_openai_done(data: str) -> bool:
    return data.strip() == "[DONE]"


# ---------------------------------------------------------------------------
# Shim integration
# ---------------------------------------------------------------------------

# Load llm-rosetta provider shims on module import
load_providers()

# Map argo-proxy target_provider to llm-rosetta shim name
_SHIM_NAME_MAP: dict[str, str] = {
    "anthropic": "argo--anthropic",
    "openai_chat": "argo--openai_chat",
}


def _resolve_shim(target_provider: ProviderType) -> ProviderShim | None:
    """Look up the llm-rosetta shim for the given target provider."""
    name = _SHIM_NAME_MAP.get(target_provider)
    return get_shim(name) if name else None


def _inject_shim_reasoning(
    ctx: ConversionContext,
    shim: ProviderShim | None,
    model: str,
) -> None:
    """Inject the shim's reasoning capability config into the conversion context."""
    if shim is None or shim.reasoning is None:
        return
    cap = shim.reasoning
    if shim.model_reasoning and model in shim.model_reasoning:
        cap = shim.model_reasoning[model]
    ctx.options["reasoning_cap"] = cap


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------


def _error_response(
    source_provider: ProviderType, status_code: int, message: str
) -> web.Response:
    """Return an error response formatted for the source provider's envelope."""
    if source_provider in ("openai_chat", "openai_responses"):
        body = {
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": None,
            }
        }
    elif source_provider == "anthropic":
        body = {
            "type": "error",
            "error": {"type": "invalid_request_error", "message": message},
        }
    elif source_provider == "google":
        body = {
            "error": {
                "code": status_code,
                "message": message,
                "status": "INVALID_ARGUMENT",
            }
        }
    else:
        body = {"error": {"message": message}}

    return web.json_response(body, status=status_code)


def _is_anthropic_stream_required_error(status_code: int, error_text: str) -> bool:
    """Detect Anthropic's 'streaming is required' bounce-back error.

    This error (HTTP 500) is returned immediately when Anthropic determines
    the operation may exceed 10 minutes.
    """
    if status_code != 500:
        return False
    return "streaming is required" in error_text.lower()


def _dump_error_request(
    request_body: dict[str, Any],
    error_status: int,
    error_text: str,
    upstream_url: str,
    source_provider: ProviderType | None = None,
    target_provider: ProviderType | None = None,
) -> None:
    """Dump request and error details to disk for diagnostics.

    Saves a JSON file to ``<config_dir>/error_dumps/`` containing the
    request body, upstream response status/text, URL, and provider context.
    When the dump directory exceeds 50 MB, existing ``.json`` files are
    automatically gzip-compressed.

    Args:
        request_body: The request payload sent (or intended) to upstream.
        error_status: HTTP status code from the upstream response.
        error_text: Body/text of the upstream error response.
        upstream_url: The upstream URL the request was sent to.
        source_provider: Client-side API format (e.g. ``"openai_chat"``).
        target_provider: Upstream API format (e.g. ``"anthropic"``).
    """
    import gzip
    from datetime import datetime
    from pathlib import Path

    try:
        config_path = os.environ.get("CONFIG_PATH")
        if config_path:
            log_dir = Path(config_path).parent / "error_dumps"
        else:
            log_dir = Path.cwd() / "error_dumps"

        log_dir.mkdir(parents=True, exist_ok=True)

        # Auto-compress when directory exceeds 50MB
        dir_size = sum(f.stat().st_size for f in log_dir.iterdir() if f.is_file())
        if dir_size > 50 * 1024 * 1024:
            log_warning(
                f"Error dump directory ({dir_size / 1024 / 1024:.2f}MB) "
                "exceeds 50MB, compressing logs...",
                context="dispatch",
            )
            for json_file in log_dir.glob("error_*.json"):
                try:
                    gz_path = json_file.with_suffix(".json.gz")
                    with (
                        open(json_file, "rb") as f_in,
                        gzip.open(gz_path, "wb", compresslevel=9) as f_out,
                    ):
                        f_out.write(f_in.read())
                    json_file.unlink()
                except Exception as exc:
                    log_error(
                        f"Failed to compress {json_file}: {exc}", context="dispatch"
                    )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_file = log_dir / f"error_{timestamp}.json"

        entry: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "upstream_url": upstream_url,
            "error_status": error_status,
            "error_text": error_text,
            "source_provider": source_provider,
            "target_provider": target_provider,
            "request_body": request_body,
        }

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        log_info(f"Dumped error request to: {log_file}", context="dispatch")
    except Exception as exc:
        log_error(f"Failed to dump error request: {exc}", context="dispatch")


def _dump_stream_retry_request(
    request_body: dict[str, Any],
    error_status: int,
    error_text: str,
    upstream_url: str,
) -> None:
    """Dump request details when retry mode triggers a forced-streaming retry.

    Thin wrapper around :func:`_dump_error_request` kept for backward
    compatibility with existing call sites.
    """
    _dump_error_request(
        request_body,
        error_status,
        error_text,
        upstream_url,
    )


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def _detect_stream(source_provider: ProviderType, body: dict[str, Any]) -> bool:
    """Detect if the request asks for streaming."""
    if source_provider in ("openai_chat", "openai_responses", "anthropic"):
        return bool(body.get("stream", False))
    # Google streaming is determined by URL, not body
    return False


def _downgrade_developer_role(body: dict[str, Any]) -> None:
    """Replace ``developer`` role with ``system`` for upstream compatibility.

    The ``developer`` role was introduced in the OpenAI 2024-12-17 API
    version for reasoning models (o1/o3/o4).  Upstream gateways that use
    an older API version (e.g. the ANL Argo gateway) reject it with a
    misleading ``Unknown parameter: 'messages[0].tool_calls'`` error.
    Mapping back to ``system`` is safe — all OpenAI models still accept it.

    Args:
        body: The request body (modified in-place).
    """
    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        return
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "developer":
            msg["role"] = "system"


def _normalize_null_content(body: dict[str, Any]) -> None:
    """Replace ``content: null`` with empty string in messages.

    Some upstream gateways (e.g. the ARGO gateway for Gemini models)
    iterate over message ``content`` and crash with
    ``TypeError: 'NoneType' object is not iterable`` when ``content``
    is ``null``.  This is common for assistant messages that carry only
    ``tool_calls`` — the OpenAI SDK serialises their content as ``null``.

    Normalizing ``null`` to ``""`` is semantically equivalent for all
    provider formats and prevents this class of upstream errors.

    Args:
        body: The request body (modified in-place).
    """
    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        return
    for msg in messages:
        if isinstance(msg, dict) and msg.get("content") is None:
            msg["content"] = ""


def _strip_temperature_for_reasoning_models(
    body: dict[str, Any], resolved_model: str
) -> None:
    """Strip ``temperature`` for reasoning models that reject it.

    Reasoning-class models such as Claude Opus 4.7 deprecate the
    ``temperature`` parameter and return ``400 invalid_request_error``
    when it is present.  Silently remove it to avoid upstream rejections.

    Args:
        body: The request body (modified in-place).
        resolved_model: The resolved internal model identifier.
    """
    if "temperature" not in body:
        return
    # Normalise for matching: strip non-alphanumeric, lowercase
    normalised = re.sub(r"[^a-z0-9]", "", resolved_model.lower())
    # Models that reject temperature — extend this set as needed
    _NO_TEMPERATURE_MODELS = {"claudeopus47"}
    if normalised in _NO_TEMPERATURE_MODELS:
        removed = body.pop("temperature")
        log_debug(
            f"Stripped temperature={removed} (unsupported by {resolved_model})",
            context="dispatch",
        )


def _extract_client_credential(
    request: web.Request, target_provider: ProviderType
) -> str | None:
    """Extract auth credential from the client request, prioritised by target.

    When the target is ``anthropic``, ``x-api-key`` is checked first; otherwise
    ``Authorization`` (Bearer) is checked first.  Google-specific headers and
    the ``?key=`` query parameter are checked as fallbacks.

    Args:
        request: The incoming client request.
        target_provider: The upstream provider we are routing to.

    Returns:
        The extracted credential string, or ``None`` if none found.
    """

    def _header_value(hdr: str) -> str | None:
        val = request.headers.get(hdr, "")
        if not val:
            return None
        if val.lower().startswith("bearer "):
            return val[7:].strip() or None
        return val.strip() or None

    if target_provider == "anthropic":
        order = ["x-api-key", "authorization"]
    else:
        order = ["authorization", "x-api-key"]

    for hdr in order:
        key = _header_value(hdr)
        if key:
            return key

    goog = _header_value("x-goog-api-key")
    if goog:
        return goog
    if "key" in request.query:
        return request.query["key"]

    return None


def _build_upstream_headers(
    request: web.Request,
    target_provider: ProviderType,
    *,
    fallback_user: str,
    stream: bool = False,
) -> dict[str, str]:
    """Build HTTP headers for the upstream API request.

    Auth credential logic:
    - Without ``--username-passthrough``: always use *fallback_user*.
    - With ``--username-passthrough``: extract from client request first,
      fall back to *fallback_user*.

    Args:
        request: The incoming client request.
        target_provider: The upstream provider (determines header format).
        fallback_user: Value from ``config.user`` used when no client cred.
        stream: Whether this is a streaming request.

    Returns:
        A dict of HTTP headers ready for the upstream request.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if should_use_username_passthrough():
        api_key = _extract_client_credential(request, target_provider) or fallback_user
    else:
        api_key = fallback_user

    if target_provider == "anthropic":
        headers["x-api-key"] = api_key
        if "anthropic-version" in request.headers:
            headers["anthropic-version"] = request.headers["anthropic-version"]
        else:
            headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    if stream:
        headers["Accept"] = "text/event-stream"
        headers["Accept-Encoding"] = "identity"

    return headers


def _inject_stream_flags(
    body: dict[str, Any], target_provider: ProviderType
) -> dict[str, Any]:
    """Inject stream-related flags into the upstream request body."""
    body = dict(body)
    if target_provider == "openai_chat":
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    elif target_provider in ("openai_responses", "anthropic"):
        body["stream"] = True
    # Google streaming is signaled via URL, not body
    return body


def _apply_anthropic_user_id(data: dict[str, Any], user: str) -> None:
    """Set Anthropic metadata.user_id field."""
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["user_id"] = data.get("user", user)


def _ensure_user_field(body: dict[str, Any], user: str) -> None:
    """Inject ``user`` field if missing (cross-format IR round-trips drop it)."""
    if "user" not in body:
        body["user"] = user


_STREAMING_HEADERS: dict[str, str] = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
}


async def _write_sse_chunks(
    response: web.StreamResponse,
    source_chunks: dict[str, Any] | list[dict[str, Any]] | None,
    format_sse: Callable[[dict[str, Any]], str],
) -> None:
    """Write formatted SSE chunks to the streaming response."""
    if not source_chunks:
        return
    if isinstance(source_chunks, list):
        for sc in source_chunks:
            if sc:
                await response.write(format_sse(sc).encode("utf-8"))
    else:
        await response.write(format_sse(source_chunks).encode("utf-8"))


# ---------------------------------------------------------------------------
# Image preprocessing (runs BEFORE format conversion)
# ---------------------------------------------------------------------------


async def _preprocess_images(
    session: aiohttp.ClientSession,
    data: dict[str, Any],
    source_provider: ProviderType,
    config: ArgoConfig,
) -> dict[str, Any]:
    """Download and convert image URLs to base64 before format conversion."""
    if source_provider in ("openai_chat", "openai_responses"):
        return await process_openai_images(session, data, config)
    elif source_provider == "anthropic":
        return await process_anthropic_images(session, data, config)
    return data


# ---------------------------------------------------------------------------
# Anthropic SSE aggregation (stream → non-streaming response)
# ---------------------------------------------------------------------------


async def _aggregate_anthropic_sse(
    upstream_resp: aiohttp.ClientResponse,
) -> dict[str, Any] | None:
    """Consume an Anthropic SSE stream and reconstruct a non-streaming response.

    Reads all SSE events from the upstream response and aggregates them into
    the equivalent Anthropic Messages API non-streaming JSON response.

    Supports text, tool_use, thinking, and redacted_thinking content blocks.

    Args:
        upstream_resp: The aiohttp response containing SSE content.

    Returns:
        Aggregated response dict, or ``None`` if an ARGO auth warning is
        detected in the first chunk.
    """
    message: dict[str, Any] = {}
    content_blocks: dict[int, dict[str, Any]] = {}
    tool_input_buffers: dict[int, list[str]] = {}
    line_buffer = ""
    _auth_checked = False

    async for raw_chunk in upstream_resp.content.iter_any():
        if not raw_chunk:
            continue

        # Check the very first bytes for ARGO auth warning
        if not _auth_checked:
            raw_text = raw_chunk.decode("utf-8", errors="replace")
            if contains_argo_auth_warning(raw_text):
                return None
            _auth_checked = True

        text = line_buffer + raw_chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        line_buffer = lines.pop()

        for line in lines:
            parsed = _parse_sse_line(line)
            if parsed is None:
                continue
            field, value = parsed
            if field != "data":
                continue

            try:
                data = json.loads(value)
            except json.JSONDecodeError:
                continue

            event_type = data.get("type")

            if event_type == "message_start":
                message = data.get("message", {})
                message.setdefault("content", [])

            elif event_type == "content_block_start":
                index = data.get("index", 0)
                block = data.get("content_block", {})
                content_blocks[index] = dict(block)
                if block.get("type") == "tool_use":
                    tool_input_buffers[index] = []

            elif event_type == "content_block_delta":
                index = data.get("index", 0)
                delta = data.get("delta", {})
                block = content_blocks.get(index)
                if block is None:
                    continue

                delta_type = delta.get("type")
                if delta_type == "text_delta":
                    block["text"] = block.get("text", "") + delta.get("text", "")
                elif delta_type == "input_json_delta":
                    if index in tool_input_buffers:
                        tool_input_buffers[index].append(delta.get("partial_json", ""))
                elif delta_type == "thinking_delta":
                    block["thinking"] = block.get("thinking", "") + delta.get(
                        "thinking", ""
                    )
                elif delta_type == "signature_delta":
                    block["signature"] = block.get("signature", "") + delta.get(
                        "signature", ""
                    )

            elif event_type == "content_block_stop":
                index = data.get("index", 0)
                if index in tool_input_buffers:
                    raw_json = "".join(tool_input_buffers[index])
                    try:
                        content_blocks[index]["input"] = (
                            json.loads(raw_json) if raw_json else {}
                        )
                    except json.JSONDecodeError:
                        content_blocks[index]["input"] = {}

            elif event_type == "message_delta":
                delta = data.get("delta", {})
                for key, val in delta.items():
                    message[key] = val
                usage = data.get("usage", {})
                if usage:
                    message.setdefault("usage", {}).update(usage)

            # message_stop and ping are intentionally ignored

    # Build final content array in index order
    if content_blocks:
        message["content"] = [content_blocks[i] for i in sorted(content_blocks.keys())]

    return message


# ---------------------------------------------------------------------------
# Debug dump helper
# ---------------------------------------------------------------------------


def _debug_dump(stage: str, data: Any, config: ArgoConfig) -> None:
    """Write a JSON dump to ``config.dump_dir``/<timestamp>_<stage>.json.

    The dump is a no-op when ``config.dump_requests`` is False.

    Args:
        stage: Short label describing the processing stage (e.g.
            ``"1_request_received"``).
        data: Payload to serialize as JSON.
        config: The current ArgoConfig instance (controls whether
            dumping is enabled and where files are written).
    """
    if not config.dump_requests:
        return
    dump_dir = config.dump_dir
    os.makedirs(dump_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(dump_dir, f"{ts}_{stage}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    log_debug(f"Debug dump: {path}", context="dispatch")


# ---------------------------------------------------------------------------
# Cross-format conversion handlers
# ---------------------------------------------------------------------------


class _PreparedConvert:
    """Holds the results of the prepare phase so execute can be called
    multiple times (e.g. retry with force_stream) without re-doing the
    IR round-trip."""

    __slots__ = (
        "source_converter",
        "target_converter",
        "shim",
        "ctx",
        "target_body",
        "source_provider",
        "target_provider",
    )

    def __init__(
        self,
        source_converter: Any,
        target_converter: Any,
        shim: ProviderShim | None,
        ctx: ConversionContext,
        target_body: dict[str, Any],
        source_provider: ProviderType,
        target_provider: ProviderType,
    ):
        self.source_converter = source_converter
        self.target_converter = target_converter
        self.shim = shim
        self.ctx = ctx
        self.target_body = target_body
        self.source_provider = source_provider
        self.target_provider = target_provider


def _prepare_convert(
    body: dict[str, Any],
    source_provider: ProviderType,
    target_provider: ProviderType,
    config: ArgoConfig,
) -> Union[_PreparedConvert, web.Response]:
    """Source → IR → target + shim transforms.  Returns prepared state or error.

    The expensive IR round-trip is done once here.  The result can be passed
    to ``_execute_convert`` one or more times with different ``force_stream``
    settings.
    """
    source_converter = get_converter_for_provider(source_provider)
    target_converter = get_converter_for_provider(target_provider)
    shim = _resolve_shim(target_provider)
    ctx = ConversionContext(options={"metadata_mode": "preserve"})
    _inject_shim_reasoning(ctx, shim, body.get("model", ""))

    # 1. Source → IR
    _debug_dump("1_request_received", body, config)
    try:
        ir_request = source_converter.request_from_provider(body, context=ctx)
    except Exception as exc:
        return _error_response(source_provider, 400, f"Failed to parse request: {exc}")

    if config.verbose:
        log_debug(f"IR request keys: {list(ir_request.keys())}", context="dispatch")

    # 2. IR → Target
    try:
        convert_kwargs: dict[str, str] = {}
        if target_provider == "google":
            convert_kwargs["output_format"] = "rest"
        target_body, warnings = target_converter.request_to_provider(
            ir_request, context=ctx, **convert_kwargs
        )
    except Exception as exc:
        return _error_response(source_provider, 400, f"Conversion error: {exc}")

    if warnings:
        log_info(f"Conversion warnings: {warnings}", context="dispatch")

    # Apply shim to_transforms (e.g. strip unsupported fields, rename fields)
    if shim and shim.to_transforms:
        target_body = apply_transforms(shim.to_transforms, target_body)

    _ensure_user_field(target_body, config.user)
    _downgrade_developer_role(target_body)
    _normalize_null_content(target_body)

    return _PreparedConvert(
        source_converter=source_converter,
        target_converter=target_converter,
        shim=shim,
        ctx=ctx,
        target_body=target_body,
        source_provider=source_provider,
        target_provider=target_provider,
    )


async def _execute_convert(
    prepared: _PreparedConvert,
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    config: ArgoConfig,
    *,
    force_stream: bool = False,
) -> web.Response:
    """Forward prepared request to upstream and convert the response back.

    When ``force_stream`` is True the upstream leg uses SSE and the event
    stream is aggregated into a single JSON dict before conversion.
    """
    target_body = dict(prepared.target_body)  # shallow copy for mutation

    if force_stream:
        target_body = _inject_stream_flags(target_body, prepared.target_provider)
        headers = dict(headers)
        headers["Accept"] = "text/event-stream"
        headers["Accept-Encoding"] = "identity"
        log_info(
            "Forcing streaming on upstream leg (client requested non-streaming)",
            context="dispatch",
        )

    _debug_dump("2_request_converted", target_body, config)

    if config.verbose:
        log_converted_request(
            target_body, verbose=True, max_history_items=config.max_log_history
        )

    try:
        async with session.post(
            upstream_url, headers=headers, json=target_body
        ) as upstream_resp:
            if upstream_resp.status >= 400:
                error_text = await upstream_resp.text()
                log_upstream_error(
                    upstream_resp.status,
                    error_text,
                    endpoint=str(prepared.target_provider),
                    is_streaming=force_stream,
                )
                _dump_error_request(
                    body,
                    upstream_resp.status,
                    error_text,
                    upstream_url,
                    source_provider=prepared.source_provider,
                    target_provider=prepared.target_provider,
                )
                return web.Response(
                    text=error_text,
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            upstream_fmt = (
                "anthropic" if prepared.target_provider == "anthropic" else "openai"
            )

            if force_stream:
                upstream_json = await _aggregate_anthropic_sse(upstream_resp)
                if upstream_json is None:
                    log_error(ARGO_AUTH_ERROR_MESSAGE, context="dispatch")
                    return _error_response(
                        prepared.source_provider, 403, ARGO_AUTH_ERROR_MESSAGE
                    )
            else:
                try:
                    upstream_json = await upstream_resp.json()
                except (aiohttp.ContentTypeError, json.JSONDecodeError):
                    return _error_response(
                        prepared.source_provider,
                        502,
                        "Upstream returned non-JSON response",
                    )
                if check_response_for_argo_warning(upstream_json, upstream_fmt):
                    log_error(ARGO_AUTH_ERROR_MESSAGE, context="dispatch")
                    return _error_response(
                        prepared.source_provider, 403, ARGO_AUTH_ERROR_MESSAGE
                    )

            _debug_dump("3_response_received", upstream_json, config)

            if prepared.shim and prepared.shim.from_transforms:
                upstream_json = apply_transforms(
                    prepared.shim.from_transforms, upstream_json
                )

            try:
                ir_response = prepared.target_converter.response_from_provider(
                    upstream_json, context=prepared.ctx
                )
            except Exception as exc:
                return _error_response(
                    prepared.source_provider,
                    502,
                    f"Failed to parse upstream response: {exc}",
                )

            try:
                source_response = prepared.source_converter.response_to_provider(
                    ir_response, context=prepared.ctx
                )
            except Exception as exc:
                return _error_response(
                    prepared.source_provider,
                    500,
                    f"Failed to convert response: {exc}",
                )

            _debug_dump("4_response_converted", source_response, config)
            return web.json_response(source_response)

    except aiohttp.ClientError as exc:
        return _error_response(
            prepared.source_provider, 502, f"Upstream request failed: {exc}"
        )


async def _convert(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    source_provider: ProviderType,
    target_provider: ProviderType,
    config: ArgoConfig,
    *,
    force_stream: bool = False,
) -> web.Response:
    """Convenience wrapper: prepare + execute in one call."""
    prepared = _prepare_convert(body, source_provider, target_provider, config)
    if isinstance(prepared, web.Response):
        return prepared
    return await _execute_convert(
        prepared,
        session,
        upstream_url,
        headers,
        body,
        config,
        force_stream=force_stream,
    )


async def _convert_with_retry(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    source_provider: ProviderType,
    target_provider: ProviderType,
    config: ArgoConfig,
) -> web.Response:
    """Try non-streaming, fall back to forced-stream on Anthropic bounce-back.

    Prepares the IR conversion once, then executes twice if needed.
    """
    prepared = _prepare_convert(body, source_provider, target_provider, config)
    if isinstance(prepared, web.Response):
        return prepared

    result = await _execute_convert(
        prepared, session, upstream_url, headers, body, config, force_stream=False
    )

    if result.status != 500 or not result.body:
        return result

    try:
        body_text = result.body.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        return result

    if not _is_anthropic_stream_required_error(500, body_text):
        return result

    log_info(
        "Anthropic returned 'streaming required' error, "
        "retrying with forced streaming (retry mode)",
        context="dispatch",
    )
    _dump_stream_retry_request(body, 500, body_text, upstream_url)
    return await _execute_convert(
        prepared, session, upstream_url, headers, body, config, force_stream=True
    )


async def _convert_streaming(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    source_provider: ProviderType,
    target_provider: ProviderType,
    request: web.Request,
    config: ArgoConfig,
) -> web.StreamResponse:
    """Streaming: source → IR → target → upstream SSE → IR events → source SSE."""
    source_converter = get_converter_for_provider(source_provider)
    target_converter = get_converter_for_provider(target_provider)
    shim = _resolve_shim(target_provider)
    ctx = ConversionContext(options={"metadata_mode": "preserve"})
    _inject_shim_reasoning(ctx, shim, body.get("model", ""))

    # 1. Source → IR
    _debug_dump("s1_request_received", body, config)
    try:
        ir_request = source_converter.request_from_provider(body, context=ctx)
    except Exception as exc:
        return _error_response(source_provider, 400, f"Failed to parse request: {exc}")

    # 2. IR → Target
    try:
        convert_kwargs: dict[str, str] = {}
        if target_provider == "google":
            convert_kwargs["output_format"] = "rest"
        target_body, warnings = target_converter.request_to_provider(
            ir_request, context=ctx, **convert_kwargs
        )
    except Exception as exc:
        return _error_response(source_provider, 400, f"Conversion error: {exc}")

    if warnings:
        log_info(f"Conversion warnings: {warnings}", context="dispatch")

    # Apply shim to_transforms
    if shim and shim.to_transforms:
        target_body = apply_transforms(shim.to_transforms, target_body)

    # 3. Inject stream flags
    target_body = _inject_stream_flags(target_body, target_provider)
    _debug_dump("s2_request_converted", target_body, config)
    if config.verbose:
        log_converted_request(
            target_body, verbose=True, max_history_items=config.max_log_history
        )

    _ensure_user_field(target_body, config.user)
    _downgrade_developer_role(target_body)
    _normalize_null_content(target_body)

    format_sse = _SSE_FORMATTERS[source_provider]

    try:
        async with session.post(
            upstream_url, headers=headers, json=target_body
        ) as upstream_resp:
            if upstream_resp.status != 200:
                error_text = await upstream_resp.text()
                log_upstream_error(
                    upstream_resp.status,
                    error_text,
                    endpoint=str(target_provider),
                    is_streaming=True,
                )
                _dump_error_request(
                    body,
                    upstream_resp.status,
                    error_text,
                    upstream_url,
                    source_provider=source_provider,
                    target_provider=target_provider,
                )
                return web.json_response(
                    {
                        "error": f"Upstream API error: {upstream_resp.status} {error_text}"
                    },
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # Prepare streaming response (deferred until first chunk validated)
            response = web.StreamResponse(status=200, headers=_STREAMING_HEADERS)
            response.enable_chunked_encoding()
            prepared = False

            from_ctx = StreamContext()  # upstream → IR
            to_ctx = StreamContext()  # IR → source
            # Bridge preserve-mode metadata from request phase
            to_ctx.options["metadata_mode"] = "preserve"
            if "_request_echo" in ctx.metadata:
                to_ctx.metadata["_request_echo"] = ctx.metadata["_request_echo"]
            chunk_count = 0
            t0 = time.monotonic()
            _auth_checked = False
            _raw_chunks: list[Any] = []
            _converted_chunks: list[Any] = []

            # Buffer for partial SSE lines from byte chunks
            line_buffer = ""

            async for raw_chunk in upstream_resp.content.iter_any():
                if not raw_chunk:
                    continue

                # Check the first raw bytes for ARGO auth warning before
                # committing to the streaming response.
                if not _auth_checked:
                    raw_text = raw_chunk.decode("utf-8", errors="replace")
                    if contains_argo_auth_warning(raw_text):
                        log_error(ARGO_AUTH_ERROR_MESSAGE, context="dispatch")
                        return _error_response(
                            source_provider, 403, ARGO_AUTH_ERROR_MESSAGE
                        )
                    _auth_checked = True

                if not prepared:
                    await response.prepare(request)
                    prepared = True

                # Decode bytes and split into SSE lines
                text = line_buffer + raw_chunk.decode("utf-8", errors="replace")
                lines = text.split("\n")
                # Last element may be incomplete; save for next iteration
                line_buffer = lines.pop()

                for line in lines:
                    parsed = _parse_sse_line(line)
                    if parsed is None:
                        continue
                    field, value = parsed

                    if field == "event":
                        continue
                    if field != "data" or value is None:
                        continue
                    if _is_openai_done(value):
                        break

                    try:
                        chunk_data = json.loads(value)
                    except json.JSONDecodeError:
                        log_debug(
                            f"Skipping malformed SSE data: {value[:200]}",
                            context="dispatch",
                        )
                        continue

                    chunk_count += 1

                    _raw_chunks.append(chunk_data)

                    # Log first chunk and error chunks for diagnostics
                    if chunk_count == 1 and config.verbose:
                        log_debug(
                            f"First upstream chunk: {json.dumps(chunk_data)[:500]}",
                            context="dispatch",
                        )
                    if "error" in chunk_data:
                        log_warning(
                            f"Upstream error in stream chunk: {json.dumps(chunk_data)[:500]}",
                            context="dispatch",
                        )
                        _dump_error_request(
                            body,
                            upstream_resp.status,
                            json.dumps(chunk_data, ensure_ascii=False),
                            upstream_url,
                            source_provider=source_provider,
                            target_provider=target_provider,
                        )

                    # Upstream chunk → IR events
                    ir_events = target_converter.stream_response_from_provider(
                        chunk_data, context=from_ctx
                    )

                    # IR events → source-format chunks
                    for ir_event in ir_events:
                        source_chunks = source_converter.stream_response_to_provider(
                            ir_event, context=to_ctx
                        )
                        _converted_chunks.extend(source_chunks)
                        await _write_sse_chunks(response, source_chunks, format_sse)

            # Ensure response is prepared even if no chunks were received
            if not prepared:
                await response.prepare(request)

            # ----------------------------------------------------------
            # Fallback: ensure stream is properly terminated.
            # If upstream never sent a final empty-choices chunk (e.g.
            # it ignores stream_options.include_usage), the converter
            # may not have emitted StreamEndEvent.  Synthesize the
            # missing termination events so the client sees a valid
            # end-of-stream sequence.
            # ----------------------------------------------------------
            if not from_ctx.is_ended:
                from llm_rosetta.types.ir.stream import StreamEndEvent

                log_debug(
                    "Upstream stream ended without StreamEndEvent; "
                    "synthesizing termination events",
                    context="dispatch",
                )
                from_ctx.mark_ended()
                end_event = StreamEndEvent(type="stream_end")
                source_chunks = source_converter.stream_response_to_provider(
                    end_event, context=to_ctx
                )
                await _write_sse_chunks(response, source_chunks, format_sse)

            # Emit end-of-stream marker for OpenAI Chat
            if source_provider == "openai_chat":
                await response.write(b"data: [DONE]\n\n")

            _debug_dump("s3_all_chunks_received", _raw_chunks, config)
            _debug_dump("s4_all_chunks_converted", _converted_chunks, config)

            if config.verbose:
                elapsed = time.monotonic() - t0
                log_debug(
                    f"Stream complete: {chunk_count} chunks in {elapsed:.2f}s",
                    context="dispatch",
                )

            await response.write_eof()
            return response

    except aiohttp.ClientError as exc:
        return _error_response(source_provider, 502, f"Upstream request failed: {exc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def proxy_request(
    request: web.Request,
    source_provider: ProviderType,
    *,
    model_override: str | None = None,
    force_stream: bool = False,
) -> Union[web.Response, web.StreamResponse]:
    """Universal proxy entry point.

    Handles any client API format, resolves the model to an upstream target,
    and performs format conversion via llm-rosetta when needed.

    Args:
        request: The aiohttp web request.
        source_provider: The client's API format (e.g. "openai_chat", "anthropic").
        model_override: Override model name (used for Google URL-based routing).
        force_stream: Force streaming mode (used for Google streamGenerateContent).

    Returns:
        A web.Response or web.StreamResponse.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]
    session: aiohttp.ClientSession = request.app["http_session"]

    try:
        body = await request.json()
    except Exception:
        return _error_response(source_provider, 400, "Invalid JSON body")

    # Apply username passthrough early so all subsequent logs carry the user tag
    apply_username_passthrough(body, request, config.user)
    user_token = None
    if should_use_username_passthrough():
        user_token = set_request_user(body.get("user", ""))

    try:
        log_original_request(
            body, verbose=config.verbose, max_history_items=config.max_log_history
        )

        # Extract and resolve model
        model = model_override or body.get("model")
        if not model:
            return _error_response(source_provider, 400, "Missing 'model' field")

        original_model = model
        # For Anthropic source, use as_is=True to preserve bare model names
        as_is = source_provider == "anthropic"
        resolved_model = model_registry.resolve_model_name(model, "chat", as_is=as_is)

        if resolved_model != original_model and config.verbose:
            log_info(
                f"Model resolved: {original_model} -> {resolved_model}",
                context="dispatch",
            )

        # Update body with resolved model
        body["model"] = resolved_model

        # Determine upstream target
        target_provider, upstream_url = model_registry.resolve_model_target(
            resolved_model, config
        )

        if config.verbose:
            log_debug(
                f"Routing: {source_provider} -> {target_provider} ({upstream_url})",
                context="dispatch",
            )

        # Preprocess images (format-specific, before conversion)
        body = await _preprocess_images(session, body, source_provider, config)

        # Anthropic target: also set metadata.user_id
        if target_provider == "anthropic":
            _apply_anthropic_user_id(body, config.user)

        # Strip temperature for reasoning models that reject it
        _strip_temperature_for_reasoning_models(body, resolved_model)

        # Detect streaming
        stream = force_stream or _detect_stream(source_provider, body)

        # Build upstream headers
        headers = _build_upstream_headers(
            request, target_provider, fallback_user=config.user, stream=stream
        )

        # Reorder parallel tool calls for Gemini models — the ARGO gateway
        # rejects requests where a single assistant message contains multiple
        # tool_calls.  Split them into sequential call-result pairs.
        if model_registry._classify_model_by_family(resolved_model) == "google":
            messages = body.get("messages")
            if messages and isinstance(messages, list):
                body["messages"] = reorder_parallel_tool_calls(messages)

        # All requests go through the full converter + shim pipeline.
        # Same-format (e.g. anthropic → anthropic) still benefits from
        # shim reasoning config, transforms, and unsigned reasoning policy.
        if config.verbose:
            if source_provider == target_provider:
                log_debug(
                    f"Same-format conversion: {source_provider} -> IR -> {target_provider}",
                    context="dispatch",
                )
            else:
                log_debug(
                    f"Cross-format: {source_provider} -> {target_provider}",
                    context="dispatch",
                )

        if stream:
            return await _convert_streaming(
                session,
                upstream_url,
                headers,
                body,
                source_provider,
                target_provider,
                request,
                config,
            )

        # Handle Anthropic non-streaming requests: pick a strategy that
        # accounts for Anthropic's "long requests require streaming" bounce.
        if target_provider == "anthropic":
            mode = config.anthropic_stream_mode
            if mode == "force":
                # Always upgrade the upstream leg to streaming and aggregate.
                return await _convert(
                    session,
                    upstream_url,
                    headers,
                    body,
                    source_provider,
                    target_provider,
                    config,
                    force_stream=True,
                )
            if mode == "retry":
                # Try non-streaming first, only force-stream on bounce-back.
                return await _convert_with_retry(
                    session,
                    upstream_url,
                    headers,
                    body,
                    source_provider,
                    target_provider,
                    config,
                )
            # "passthrough": fall through to the plain non-streaming path.

        return await _convert(
            session,
            upstream_url,
            headers,
            body,
            source_provider,
            target_provider,
            config,
            force_stream=False,
        )
    except (
        ConnectionResetError,
        ConnectionAbortedError,
        aiohttp.ClientConnectionResetError,
    ) as exc:
        log_warning(
            f"Client disconnected during request: {exc}",
            context="dispatch",
        )
        return _error_response(source_provider, 499, "Client closed connection")
    except Exception as exc:
        if "Cannot write to closing transport" in str(exc):
            log_warning(
                f"Client disconnected during request: {exc}",
                context="dispatch",
            )
            return _error_response(source_provider, 499, "Client closed connection")
        log_error(
            f"Unhandled dispatch error: {exc}\n{traceback.format_exc()}",
            context="dispatch",
        )
        return _error_response(source_provider, 500, f"Internal error: {exc}")
    finally:
        if user_token is not None:
            clear_request_user(user_token)
