"""Dev-proxy mode — transparent passthrough without format conversion.

When ``--dev`` is passed, argo-proxy acts as a thin reverse proxy:
requests are forwarded to the ARGO upstream as-is, with only user
injection and auth-warning detection applied.  No model resolution,
no format conversion, no streaming-mode logic.

Both streaming and non-streaming requests are supported.  Stream
detection follows the same per-provider rules as normal mode so that
SSE responses are relayed correctly.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from llm_rosetta._vendor.httpserver import (
    JSONResponse,
    Response,
    StreamingResponse,
)

from .auth import (
    argo_auth_error_response,
    contains_argo_auth_warning,
    should_use_username_passthrough,
)
from .transport import ArgoAuthWarning
from .utils.logging import log_debug, log_info
from .utils.misc import build_user_agent
from .utils.telemetry import record_telemetry

logger = logging.getLogger("argo-proxy")

_DEV_PROVIDER_NAME = "argo-dev"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SSE_CONTENT_TYPE = "text/event-stream"


def _detect_stream(body: dict[str, Any], source: str) -> bool:
    """Simple stream detection based on request body."""
    if source == "google":
        return False  # handled by URL suffix
    return bool(body.get("stream"))


def _extract_api_key(request: Any) -> str | None:
    headers = request.headers
    for name in ("authorization", "x-api-key", "api-key", "x-goog-api-key"):
        value = headers.get(name, "")
        if value:
            if value.lower().startswith("bearer "):
                return value[7:].strip()
            return value.strip()
    params = request.query_params
    if "key" in params:
        return params["key"][0]
    return None


# ---------------------------------------------------------------------------
# Raw passthrough via the transport's HTTP client pool
# ---------------------------------------------------------------------------


async def _raw_passthrough(
    request: Any,
    upstream_url: str,
    body: dict[str, Any],
    *,
    is_stream: bool = False,
    request_id: str = "",
    source: str = "openai_chat",
    effective_user: str | None = None,
) -> Response | StreamingResponse:
    """Forward *body* to *upstream_url* and relay the response.

    Uses the :class:`ArgoTransport`'s inner :class:`HttpTransport` client
    pool directly so we inherit connection pooling and timeouts without
    going through the gateway's routing/conversion pipeline.
    """
    from .transport import ArgoTransport

    transport: ArgoTransport = request.app.transport  # type: ignore[attr-defined]
    client = transport.raw_client()

    extra_headers: dict[str, str] = {
        "Content-Type": "application/json",
        "x-request-id": request_id,
    }
    ua = build_user_agent(request.headers.get("user-agent"))
    if ua:
        extra_headers["User-Agent"] = ua

    # Inject ARGO auth — use passthrough user when available
    config = request.app.argo_config  # type: ignore[attr-defined]
    auth_user = effective_user or config.user
    extra_headers["Authorization"] = f"Bearer {auth_user}"

    try:
        if is_stream:
            resp = await client.post(
                upstream_url, json=body, headers=extra_headers, stream=True
            )
            # resp is httpclient.StreamingResponse

            if resp.status_code >= 400:
                # Read error body and return as regular response
                try:
                    chunks: list[bytes] = []
                    async for chunk in resp.aiter_bytes():
                        chunks.append(
                            chunk if isinstance(chunk, bytes) else chunk.encode()
                        )
                finally:
                    await resp.aclose()
                error_body = b"".join(chunks)
                if contains_argo_auth_warning(
                    error_body.decode("utf-8", errors="replace")
                ):
                    return argo_auth_error_response(source)
                return Response(
                    body=error_body,
                    status_code=resp.status_code,
                    content_type="application/json",
                    headers={"x-request-id": request_id},
                )

            content_type = resp.headers.get("content-type", "")
            is_sse = "text/event-stream" in content_type

            async def _relay() -> AsyncIterator[bytes]:
                try:
                    if is_sse:
                        async for line in resp.aiter_lines():
                            yield f"{line}\n".encode()
                    else:
                        async for chunk in resp.aiter_bytes():
                            yield chunk if isinstance(chunk, bytes) else chunk.encode()
                except Exception:
                    logger.exception("[%s] Stream relay error", request_id)
                finally:
                    await resp.aclose()

            return StreamingResponse(
                _relay(),
                status_code=resp.status_code,
                content_type=_SSE_CONTENT_TYPE
                if is_sse
                else "application/octet-stream",
                headers={"x-request-id": request_id},
            )
        else:
            resp = await client.post(upstream_url, json=body, headers=extra_headers)
            # resp is httpclient.Response
            resp_text = resp.content.decode("utf-8", errors="replace")
            if contains_argo_auth_warning(resp_text):
                return argo_auth_error_response(source)
            return Response(
                body=resp.content,
                status_code=resp.status_code,
                content_type=resp.headers.get("content-type", "application/json"),
                headers={"x-request-id": request_id},
            )

    except ArgoAuthWarning:
        return argo_auth_error_response(source)
    except Exception:
        logger.exception("[%s] Dev-proxy upstream error", request_id)
        return JSONResponse(
            {"error": {"message": "Upstream error", "type": "server_error"}},
            status_code=502,
            headers={"x-request-id": request_id},
        )


# ---------------------------------------------------------------------------
# Request body parsing + user injection
# ---------------------------------------------------------------------------


def _parse_and_inject(
    request: Any, config: Any
) -> tuple[dict[str, Any] | None, str, str]:
    """Parse request JSON and resolve the effective ARGO username.

    Returns ``(body, request_id, effective_user)``.  *body* is ``None``
    on parse failure.
    """
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    try:
        body: dict[str, Any] = request.json()
    except Exception:
        return None, request_id, config.user

    if should_use_username_passthrough():
        api_key = _extract_api_key(request)
        effective_user = api_key or config.user
    else:
        effective_user = config.user

    return body, request_id, effective_user


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


def _extract_error_detail(resp: Response | StreamingResponse) -> str | None:
    """Extract a short error message from an error response body."""
    if resp.status_code < 400:
        return None
    body = getattr(resp, "body", None)
    if not body:
        return f"HTTP {resp.status_code}"
    try:
        data = json.loads(body)
        err = data.get("error", data)
        if isinstance(err, dict):
            return err.get("message") or err.get("type") or f"HTTP {resp.status_code}"
        return str(err)[:200]
    except Exception:
        text = body.decode("utf-8", errors="replace")[:200]
        return text or f"HTTP {resp.status_code}"


async def _passthrough_with_telemetry(
    request: Any,
    url: str,
    body: dict[str, Any],
    *,
    is_stream: bool,
    request_id: str,
    source: str,
    model: str,
    effective_user: str | None = None,
) -> Response | StreamingResponse:
    """Forward a request and record telemetry for the admin dashboard."""
    t0 = time.monotonic()
    resp = await _raw_passthrough(
        request,
        url,
        body,
        is_stream=is_stream,
        request_id=request_id,
        source=source,
        effective_user=effective_user,
    )
    record_telemetry(
        request,
        model=model,
        source_provider=source,
        target_provider=source,
        provider_name=_DEV_PROVIDER_NAME,
        is_stream=is_stream,
        status_code=resp.status_code,
        duration_ms=(time.monotonic() - t0) * 1000,
        error_detail=_extract_error_detail(resp),
        decrement_active_streams=False,
    )
    return resp


async def handle_dev_openai_chat(request: Any) -> Response | StreamingResponse:
    """Passthrough for ``/v1/chat/completions``."""
    log_info("[dev] /v1/chat/completions", context="app")
    config = request.app.argo_config  # type: ignore[attr-defined]
    body, rid, eff_user = _parse_and_inject(request, config)
    if body is None:
        return JSONResponse(
            {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
            headers={"x-request-id": rid},
        )
    url = f"{config.native_openai_base_url}/chat/completions"
    is_stream = _detect_stream(body, "openai_chat")
    log_debug(f"[dev] -> {url} stream={is_stream}", context="app")
    return await _passthrough_with_telemetry(
        request,
        url,
        body,
        is_stream=is_stream,
        request_id=rid,
        source="openai_chat",
        model=body.get("model", "unknown"),
        effective_user=eff_user,
    )


async def handle_dev_openai_responses(request: Any) -> Response | StreamingResponse:
    """Passthrough for ``/v1/responses``."""
    log_info("[dev] /v1/responses", context="app")
    config = request.app.argo_config  # type: ignore[attr-defined]
    body, rid, eff_user = _parse_and_inject(request, config)
    if body is None:
        return JSONResponse(
            {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
            headers={"x-request-id": rid},
        )
    url = f"{config.native_openai_base_url}/responses"
    is_stream = _detect_stream(body, "openai_responses")
    log_debug(f"[dev] -> {url} stream={is_stream}", context="app")
    return await _passthrough_with_telemetry(
        request,
        url,
        body,
        is_stream=is_stream,
        request_id=rid,
        source="openai_responses",
        model=body.get("model", "unknown"),
        effective_user=eff_user,
    )


async def handle_dev_anthropic(request: Any) -> Response | StreamingResponse:
    """Passthrough for ``/v1/messages``."""
    log_info("[dev] /v1/messages", context="app")
    config = request.app.argo_config  # type: ignore[attr-defined]
    body, rid, eff_user = _parse_and_inject(request, config)
    if body is None:
        return JSONResponse(
            {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
            headers={"x-request-id": rid},
        )

    # Anthropic-specific: inject metadata.user_id
    body.setdefault("metadata", {})
    if isinstance(body["metadata"], dict):
        body["metadata"]["user_id"] = eff_user

    url = f"{config.native_anthropic_base_url}/v1/messages"
    is_stream = _detect_stream(body, "anthropic")
    log_debug(f"[dev] -> {url} stream={is_stream}", context="app")
    return await _passthrough_with_telemetry(
        request,
        url,
        body,
        is_stream=is_stream,
        request_id=rid,
        source="anthropic",
        model=body.get("model", "unknown"),
        effective_user=eff_user,
    )


async def handle_dev_google(
    request: Any, model_path: str = ""
) -> Response | StreamingResponse:
    """Passthrough for ``/v1beta/models/<model_path>``."""
    log_info(f"[dev] /v1beta/models/{model_path}", context="app")
    config = request.app.argo_config  # type: ignore[attr-defined]
    body, rid, eff_user = _parse_and_inject(request, config)
    if body is None:
        return JSONResponse(
            {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
            headers={"x-request-id": rid},
        )

    is_stream = model_path.endswith(":streamGenerateContent")
    # Google GenAI lives under argo_base_url, not the OpenAI-compatible /v1 tree
    url = f"{config.argo_base_url}/v1beta/models/{model_path}"
    log_debug(f"[dev] -> {url} stream={is_stream}", context="app")
    model_name = model_path.split(":")[0] if model_path else "unknown"
    return await _passthrough_with_telemetry(
        request,
        url,
        body,
        is_stream=is_stream,
        request_id=rid,
        source="google",
        model=model_name,
        effective_user=eff_user,
    )


async def handle_dev_embeddings(request: Any) -> Response | StreamingResponse:
    """Passthrough for ``/v1/embeddings``."""
    log_info("[dev] /v1/embeddings", context="app")
    config = request.app.argo_config  # type: ignore[attr-defined]
    body, rid, eff_user = _parse_and_inject(request, config)
    if body is None:
        return JSONResponse(
            {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
            headers={"x-request-id": rid},
        )
    url = f"{config.native_openai_base_url}/embeddings"
    log_debug(f"[dev] -> {url}", context="app")
    return await _passthrough_with_telemetry(
        request,
        url,
        body,
        is_stream=False,
        request_id=rid,
        source="openai_embeddings",
        model=body.get("model", "unknown"),
        effective_user=eff_user,
    )


async def handle_dev_models(request: Any) -> Response | StreamingResponse:
    """Passthrough for ``/v1/models`` — forwards to upstream model list."""
    log_info("[dev] /v1/models", context="app")
    config = request.app.argo_config  # type: ignore[attr-defined]
    rid = request.headers.get("x-request-id") or str(uuid.uuid4())
    url = f"{config.native_openai_base_url}/models"

    from .transport import ArgoTransport

    transport: ArgoTransport = request.app.transport  # type: ignore[attr-defined]
    client = transport.raw_client()

    headers: dict[str, str] = {
        "Authorization": f"Bearer {config.user}",
        "x-request-id": rid,
    }
    ua = build_user_agent(request.headers.get("user-agent"))
    if ua:
        headers["User-Agent"] = ua

    try:
        resp = await client.get(url, headers=headers)
        return Response(
            body=resp.content,
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", "application/json"),
            headers={"x-request-id": rid},
        )
    except Exception:
        logger.exception("[%s] Dev-proxy /v1/models error", rid)
        return JSONResponse(
            {"error": {"message": "Upstream error", "type": "server_error"}},
            status_code=502,
            headers={"x-request-id": rid},
        )
