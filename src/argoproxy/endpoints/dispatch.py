"""Universal dispatch module — core of argo-proxy v3.0.0.

Routes any client API format (OpenAI Chat, OpenAI Responses, Anthropic Messages,
Google GenAI) to the optimal upstream (native Anthropic for Claude, OpenAI Chat
for everything else), using llm-rosetta for cross-format conversion.

When source and target formats match, requests pass through without conversion.
"""

from __future__ import annotations

import json
import time
import traceback
from typing import Any, Union

import aiohttp
from aiohttp import web

from llm_rosetta import get_converter_for_provider
from llm_rosetta.auto_detect import ProviderType
from llm_rosetta.converters.base.stream_context import StreamContext
from llm_rosetta.converters.openai_chat.tool_ops import _sanitize_schema

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..utils.image_processing import process_anthropic_images, process_openai_images
from ..utils.logging import (
    log_converted_request,
    log_debug,
    log_error,
    log_info,
    log_original_request,
    log_upstream_error,
)
from ..utils.misc import apply_username_passthrough

# ---------------------------------------------------------------------------
# SSE formatting (IR events → source-format SSE text)
# ---------------------------------------------------------------------------


def _format_sse_openai_chat(chunk: dict[str, Any]) -> str:
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _format_sse_openai_responses(chunk: dict[str, Any]) -> str:
    event_type = chunk.get("type", "unknown")
    return f"event: {event_type}\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _format_sse_anthropic(chunk: dict[str, Any]) -> str:
    event_type = chunk.get("type", "unknown")
    return f"event: {event_type}\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _format_sse_google(chunk: dict[str, Any]) -> str:
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


_SSE_FORMATTERS: dict[str, Any] = {
    "openai_chat": _format_sse_openai_chat,
    "openai_responses": _format_sse_openai_responses,
    "anthropic": _format_sse_anthropic,
    "google": _format_sse_google,
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


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def _detect_stream(source_provider: ProviderType, body: dict[str, Any]) -> bool:
    """Detect if the request asks for streaming."""
    if source_provider in ("openai_chat", "openai_responses", "anthropic"):
        return bool(body.get("stream", False))
    # Google streaming is determined by URL, not body
    return False


def _sanitize_tool_schemas(body: dict[str, Any]) -> dict[str, Any]:
    """Sanitize tool parameter schemas for upstream compatibility.

    Strips unsupported JSON Schema keywords and flattens combination keywords
    (``anyOf``/``oneOf``/``allOf``) that upstreams like Vertex AI reject.
    Operates on both OpenAI-format (``function.parameters``) and
    Anthropic-format (``input_schema``) tool definitions.

    Args:
        body: The request body (modified in-place for tool schemas).

    Returns:
        The same body dict with sanitized tool schemas.
    """
    tools = body.get("tools")
    if not tools or not isinstance(tools, list):
        return body

    for tool in tools:
        # OpenAI Chat format: tools[].function.parameters
        func = tool.get("function")
        if isinstance(func, dict):
            params = func.get("parameters")
            if isinstance(params, dict):
                func["parameters"] = _sanitize_schema(params)
            continue

        # Anthropic format: tools[].input_schema
        schema = tool.get("input_schema")
        if isinstance(schema, dict):
            tool["input_schema"] = _sanitize_schema(schema)

    return body


def _build_upstream_headers(
    request: web.Request,
    target_provider: ProviderType,
    *,
    stream: bool = False,
) -> dict[str, str]:
    """Build headers for the upstream request.

    Handles cross-format auth header translation:
    - Anthropic uses ``x-api-key``, OpenAI uses ``Authorization: Bearer ...``
    - When crossing formats, the auth credential is mapped automatically.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}

    # Collect the auth credential from whichever header the client sent
    api_key: str | None = None
    if "Authorization" in request.headers:
        auth_val = request.headers["Authorization"]
        api_key = auth_val.removeprefix("Bearer ").strip() if auth_val else None
    if "x-api-key" in request.headers:
        api_key = request.headers["x-api-key"]

    if target_provider == "anthropic":
        if api_key:
            headers["x-api-key"] = api_key
        if "anthropic-version" in request.headers:
            headers["anthropic-version"] = request.headers["anthropic-version"]
        else:
            # Provide a default version header for cross-format requests
            headers["anthropic-version"] = "2023-06-01"
    else:
        # OpenAI-style target
        if api_key:
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
# Same-format passthrough handlers
# ---------------------------------------------------------------------------


async def _passthrough_non_streaming(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    data: dict[str, Any],
) -> web.Response:
    """Forward request to upstream and return response without conversion."""
    async with session.post(upstream_url, headers=headers, json=data) as upstream_resp:
        try:
            response_data = await upstream_resp.json()
        except (aiohttp.ContentTypeError, json.JSONDecodeError):
            response_text = await upstream_resp.text()
            return web.Response(
                text=response_text,
                status=upstream_resp.status,
                content_type=upstream_resp.content_type or "text/plain",
            )
        return web.json_response(
            response_data,
            status=upstream_resp.status,
            content_type="application/json",
        )


async def _passthrough_streaming(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    data: dict[str, Any],
    request: web.Request,
    target_provider: ProviderType,
) -> web.StreamResponse:
    """Forward streaming request to upstream and pipe bytes directly."""
    data = _inject_stream_flags(data, target_provider)

    async with session.post(upstream_url, headers=headers, json=data) as upstream_resp:
        if upstream_resp.status != 200:
            error_text = await upstream_resp.text()
            log_upstream_error(
                upstream_resp.status,
                error_text,
                endpoint="dispatch_passthrough",
                is_streaming=True,
            )
            return web.json_response(
                {"error": f"Upstream API error: {upstream_resp.status} {error_text}"},
                status=upstream_resp.status,
                content_type="application/json",
            )

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        response.enable_chunked_encoding()
        await response.prepare(request)

        async for chunk in upstream_resp.content.iter_any():
            if chunk:
                await response.write(chunk)

        await response.write_eof()
        return response


# ---------------------------------------------------------------------------
# Cross-format conversion handlers
# ---------------------------------------------------------------------------


async def _convert_non_streaming(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    source_provider: ProviderType,
    target_provider: ProviderType,
    config: ArgoConfig,
) -> web.Response:
    """Non-streaming: source → IR → target → upstream → IR → source."""
    source_converter = get_converter_for_provider(source_provider)
    target_converter = get_converter_for_provider(target_provider)

    # 1. Source → IR
    try:
        ir_request = source_converter.request_from_provider(body)
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
            ir_request, **convert_kwargs
        )
    except Exception as exc:
        return _error_response(source_provider, 400, f"Conversion error: {exc}")

    if warnings:
        log_info(f"Conversion warnings: {warnings}", context="dispatch")

    # Log the converted body
    log_converted_request(target_body, verbose=config.verbose)

    # 3. Forward to upstream
    try:
        async with session.post(
            upstream_url, headers=headers, json=target_body
        ) as upstream_resp:
            # 4. Handle errors
            if upstream_resp.status >= 400:
                error_text = await upstream_resp.text()
                log_upstream_error(
                    upstream_resp.status,
                    error_text,
                    endpoint=str(target_provider),
                )
                return web.Response(
                    text=error_text,
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # 5. Target response → IR
            try:
                upstream_json = await upstream_resp.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                return _error_response(
                    source_provider, 502, "Upstream returned non-JSON response"
                )

            try:
                ir_response = target_converter.response_from_provider(upstream_json)
            except Exception as exc:
                return _error_response(
                    source_provider,
                    502,
                    f"Failed to parse upstream response: {exc}",
                )

            # 6. IR → Source response
            try:
                source_response = source_converter.response_to_provider(ir_response)
            except Exception as exc:
                return _error_response(
                    source_provider,
                    500,
                    f"Failed to convert response: {exc}",
                )

            return web.json_response(source_response)

    except aiohttp.ClientError as exc:
        return _error_response(source_provider, 502, f"Upstream request failed: {exc}")


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

    # 1. Source → IR
    try:
        ir_request = source_converter.request_from_provider(body)
    except Exception as exc:
        return _error_response(source_provider, 400, f"Failed to parse request: {exc}")

    # 2. IR → Target
    try:
        convert_kwargs: dict[str, str] = {}
        if target_provider == "google":
            convert_kwargs["output_format"] = "rest"
        target_body, warnings = target_converter.request_to_provider(
            ir_request, **convert_kwargs
        )
    except Exception as exc:
        return _error_response(source_provider, 400, f"Conversion error: {exc}")

    if warnings:
        log_info(f"Conversion warnings: {warnings}", context="dispatch")

    # 3. Inject stream flags
    target_body = _inject_stream_flags(target_body, target_provider)
    log_converted_request(target_body, verbose=config.verbose)

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
                return web.json_response(
                    {
                        "error": f"Upstream API error: {upstream_resp.status} {error_text}"
                    },
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # Prepare streaming response
            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            response.enable_chunked_encoding()
            await response.prepare(request)

            from_ctx = StreamContext()  # upstream → IR
            to_ctx = StreamContext()  # IR → source
            chunk_count = 0
            t0 = time.monotonic()

            # Buffer for partial SSE lines from byte chunks
            line_buffer = ""

            async for raw_chunk in upstream_resp.content.iter_any():
                if not raw_chunk:
                    continue

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

                    # Upstream chunk → IR events
                    ir_events = target_converter.stream_response_from_provider(
                        chunk_data, context=from_ctx
                    )

                    # IR events → source-format chunks
                    for ir_event in ir_events:
                        source_chunks = source_converter.stream_response_to_provider(
                            ir_event, context=to_ctx
                        )
                        if isinstance(source_chunks, list):
                            for sc in source_chunks:
                                if sc:
                                    await response.write(format_sse(sc).encode("utf-8"))
                        elif source_chunks:
                            await response.write(
                                format_sse(source_chunks).encode("utf-8")
                            )

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
                if isinstance(source_chunks, list):
                    for sc in source_chunks:
                        if sc:
                            await response.write(format_sse(sc).encode("utf-8"))
                elif source_chunks:
                    await response.write(format_sse(source_chunks).encode("utf-8"))

            # Emit end-of-stream marker for OpenAI Chat
            if source_provider == "openai_chat":
                await response.write(b"data: [DONE]\n\n")

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

    try:
        log_original_request(body, verbose=config.verbose)

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

        # Apply username passthrough
        apply_username_passthrough(body, request, config.user)

        # Anthropic target: also set metadata.user_id
        if target_provider == "anthropic":
            _apply_anthropic_user_id(body, config.user)

        # Detect streaming
        stream = force_stream or _detect_stream(source_provider, body)

        # Build upstream headers
        headers = _build_upstream_headers(request, target_provider, stream=stream)

        # Same-format passthrough: skip conversion entirely
        if source_provider == target_provider:
            if config.verbose:
                log_debug("Same-format passthrough (no conversion)", context="dispatch")

            # Sanitize tool schemas even in passthrough mode — upstreams
            # like Vertex AI reject unsupported JSON Schema keywords.
            _sanitize_tool_schemas(body)

            if stream:
                return await _passthrough_streaming(
                    session, upstream_url, headers, body, request, target_provider
                )
            return await _passthrough_non_streaming(
                session, upstream_url, headers, body
            )

        # Cross-format conversion
        if config.verbose:
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

        return await _convert_non_streaming(
            session,
            upstream_url,
            headers,
            body,
            source_provider,
            target_provider,
            config,
        )
    except Exception as exc:
        log_error(
            f"Unhandled dispatch error: {exc}\n{traceback.format_exc()}",
            context="dispatch",
        )
        return _error_response(source_provider, 500, f"Internal error: {exc}")
