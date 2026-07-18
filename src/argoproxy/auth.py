"""ARGO-specific authentication hook for the gateway.

Unlike the generic gateway auth that validates gateway-level API keys,
ARGO auth simply extracts the client credential and lets the upstream
ARGO server handle validation.  The hook also applies username
passthrough when enabled via environment variable.
"""

from __future__ import annotations

import os
import re
from typing import Any

from llm_rosetta._vendor.httpserver import JSONResponse, Response
from llm_rosetta.gateway.auth import api_key_label_var

_ARGO_AUTH_WARNING_PATTERN = re.compile(
    r"AUTHENTICATION NOTICE FROM ARGO", re.IGNORECASE
)

ARGO_AUTH_ERROR_MESSAGE = (
    "ARGO authentication error: the username is not registered in ARGO. "
    "Please verify your username and update your argo-proxy configuration."
)

_PUBLIC_PATHS = frozenset({"/health", "/health/live", "/health/ready", "/version"})


def _extract_api_key(request: Any) -> str | None:
    """Extract API key from request headers or query parameters."""
    headers = request.headers
    for header_name in ("authorization", "x-api-key", "api-key", "x-goog-api-key"):
        value = headers.get(header_name, "")
        if value:
            if value.lower().startswith("bearer "):
                key = value[7:].strip()
            else:
                key = value.strip()
            if key:
                return key

    params = request.query_params
    if "key" in params:
        return params["key"][0]

    return None


def should_use_username_passthrough() -> bool:
    """Check if username passthrough mode is enabled via environment variable."""
    return os.getenv("USERNAME_PASSTHROUGH", "False").lower() == "true"


def create_argo_auth_hook() -> Any:
    """Return a before-request hook for ARGO credential passthrough.

    ARGO doesn't gate on gateway-level API keys — the upstream ARGO
    server validates the user.  This hook simply extracts the client
    credential and sets the label context var for logging.
    """

    async def argo_auth_hook(request: Any) -> Response | None:
        api_key_label_var.set(None)

        if request.path in _PUBLIC_PATHS:
            return None

        key = _extract_api_key(request)
        if key:
            api_key_label_var.set(key[:8] + "...")
        return None

    return argo_auth_hook


def contains_argo_auth_warning(text: str) -> bool:
    """Check whether *text* contains the ARGO authentication warning."""
    return bool(_ARGO_AUTH_WARNING_PATTERN.search(text))


def check_response_for_argo_warning(response_data: dict, provider: str) -> bool:
    """Check a parsed upstream JSON response for ARGO auth warnings."""
    text = _extract_text_from_response(response_data, provider)
    return contains_argo_auth_warning(text)


def _extract_text_from_response(response_data: dict, provider: str) -> str:
    """Best-effort text extraction from upstream response JSON."""
    try:
        if provider in ("openai", "openai_chat"):
            choices = response_data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                return msg.get("content", "") or ""
        elif provider == "anthropic":
            content = response_data.get("content", [])
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
    except (KeyError, IndexError, TypeError):
        pass
    return ""


def argo_auth_error_response(source_provider: str) -> Response:
    """Return a 403 error response formatted for the source provider."""
    if source_provider == "anthropic":
        body = {
            "type": "error",
            "error": {
                "type": "authentication_error",
                "message": ARGO_AUTH_ERROR_MESSAGE,
            },
        }
    elif source_provider in ("google",):
        body = {
            "error": {
                "code": 403,
                "message": ARGO_AUTH_ERROR_MESSAGE,
                "status": "PERMISSION_DENIED",
            }
        }
    else:
        body = {
            "error": {
                "message": ARGO_AUTH_ERROR_MESSAGE,
                "type": "authentication_error",
                "code": "permission_denied",
            }
        }
    return JSONResponse(body, status_code=403)
