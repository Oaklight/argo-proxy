"""Shared telemetry helpers for recording metrics and request log entries."""

from __future__ import annotations

from typing import Any


def extract_client_ip(request: Any) -> str | None:
    """Extract the client IP from the request headers or socket address."""
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    addr = getattr(request, "client_addr", None)
    if addr:
        return str(addr[0])
    return None


def record_telemetry(
    request: Any,
    *,
    model: str,
    source_provider: str,
    target_provider: str,
    provider_name: str,
    is_stream: bool,
    status_code: int,
    duration_ms: float,
    error_detail: str | None,
    profile: dict[str, Any] | None = None,
) -> None:
    """Record metrics and a request log entry for the admin dashboard."""
    metrics = getattr(request.app, "metrics", None)
    if is_stream and metrics:
        metrics.active_streams -= 1
    if metrics:
        metrics.record_request(
            model=model,
            source=source_provider,
            target=target_provider,
            status_code=status_code,
            duration_ms=duration_ms,
            is_stream=is_stream,
            provider_name=provider_name,
            error_detail=error_detail,
        )

    request_log = getattr(request.app, "request_log", None)
    if request_log is not None:
        from llm_rosetta.gateway.auth import api_key_context_var
        from llm_rosetta.observability import RequestLogEntry

        key_ctx = api_key_context_var.get()
        entry = RequestLogEntry.create(
            model=model,
            source_provider=source_provider,
            target_provider=target_provider,
            target_provider_name=provider_name,
            is_stream=is_stream,
            status_code=status_code,
            duration_ms=duration_ms,
            error_detail=error_detail,
            api_key_label=key_ctx.label if key_ctx else None,
            client_ip=extract_client_ip(request),
            profile=profile,
        )
        request_log.add(entry)
