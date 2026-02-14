"""
Native Anthropic endpoint passthrough module.

This module provides direct passthrough to the native Anthropic-compatible endpoint
without any transformation or processing.
"""

import json
from http import HTTPStatus
from typing import Union

import aiohttp
from aiohttp import web

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..tool_calls.input_handle import handle_tools
from ..utils.image_processing import process_anthropic_images
from ..utils.logging import (
    log_converted_request,
    log_debug,
    log_error,
    log_info,
    log_original_request,
    log_upstream_error,
)
from ..utils.misc import apply_username_passthrough
from ..utils.models import determine_model_family


async def proxy_native_anthropic_request(
    request: web.Request,
) -> Union[web.Response, web.StreamResponse]:
    """Proxy requests directly to native Anthropic-compatible endpoint.

    This function handles the /v1/messages endpoint, forwarding requests
    in Anthropic's native format to the upstream Anthropic-compatible API.

    Args:
        request: The client's web request object.

    Returns:
        A web.Response or web.StreamResponse with the response from the upstream API.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        # Get the incoming request data
        data = await request.json()

        # Log original request
        log_original_request(data, verbose=config.verbose)

        # Use the shared HTTP session from app context
        session = request.app["http_session"]

        # Resolve model name if present (supports argo: aliases)
        if "model" in data:
            original_model = data["model"]

            # Only resolve argo: prefixed aliases, pass through other model names as-is
            if original_model.startswith("argo:"):
                resolved = model_registry.resolve_model_name(original_model, "chat")
                data["model"] = resolved
                log_info(
                    f"Resolved model alias: {original_model} -> {resolved}",
                    context="native_anthropic",
                )
            else:
                log_info(
                    f"Using model as-is: {original_model}",
                    context="native_anthropic",
                )

        # Process image URLs (download and convert to base64)
        data = await process_anthropic_images(session, data, config)

        # Handle tool calls if present
        if "tools" in data:
            model_family = determine_model_family(data.get("model", "claude"))
            if model_family in ["google", "unknown"]:
                # Use prompting based tool handling for Google and unknown models
                data = handle_tools(data, native_tools=False, input_format="anthropic")
            else:
                # Use native tool handling for OpenAI and Anthropic models
                data = handle_tools(data, native_tools=config.native_tools, input_format="anthropic")

        # Apply username passthrough - Anthropic uses metadata.user_id
        _apply_user_identification(data, request, config)

        # Construct the full upstream URL
        upstream_url = config.native_anthropic_base_url

        # Check if this is a streaming request
        stream = data.get("stream", False)

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
        }

        # Forward authorization header if present
        if "Authorization" in request.headers:
            headers["Authorization"] = request.headers["Authorization"]

        # Forward Anthropic-specific headers
        if "x-api-key" in request.headers:
            headers["x-api-key"] = request.headers["x-api-key"]

        if "anthropic-version" in request.headers:
            headers["anthropic-version"] = request.headers["anthropic-version"]

        # Log converted request
        log_converted_request(data, verbose=config.verbose)

        if config.verbose:
            log_debug(
                f"Forwarding to: {upstream_url}, stream={stream}",
                context="native_anthropic",
            )

        if stream:
            # Handle streaming response
            return await _handle_streaming_passthrough(
                session, upstream_url, headers, data, request
            )
        else:
            # Handle non-streaming response
            return await _handle_non_streaming_passthrough(
                session, upstream_url, headers, data
            )

    except ValueError as err:
        log_error(f"ValueError: {err}", context="native_anthropic.proxy")
        return web.json_response(
            {"error": str(err)},
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json",
        )
    except aiohttp.ClientError as err:
        error_message = f"HTTP error occurred: {err}"
        log_error(error_message, context="native_anthropic.proxy")
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json",
        )
    except Exception as err:
        error_message = f"An unexpected error occurred: {err}"
        log_error(error_message, context="native_anthropic.proxy")
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json",
        )


def _apply_user_identification(
    data: dict, request: web.Request, config: ArgoConfig
) -> None:
    """Apply user identification to the request data.

    For Anthropic API, user identification goes into metadata.user_id
    in addition to the standard 'user' field used for upstream compatibility.

    Args:
        data: The request data dictionary (modified in place).
        request: The web request object.
        config: The application configuration.
    """
    # Apply standard username passthrough for upstream compatibility
    apply_username_passthrough(data, request, config.user)

    # Also set Anthropic-style metadata.user_id
    if "metadata" not in data:
        data["metadata"] = {}
    data["metadata"]["user_id"] = data.get("user", config.user)


async def _handle_non_streaming_passthrough(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict,
    data: dict,
) -> web.Response:
    """Handle non-streaming passthrough request.

    Args:
        session: The client session for making the request.
        upstream_url: The full upstream URL.
        headers: Request headers.
        data: The JSON payload.

    Returns:
        A web.Response with the upstream response.
    """
    try:
        async with session.post(
            upstream_url, headers=headers, json=data
        ) as upstream_resp:
            try:
                response_data = await upstream_resp.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                # If response is not JSON, return as text
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

    except aiohttp.ClientResponseError as err:
        return web.json_response(
            {
                "type": "error",
                "error": {
                    "type": "upstream_api_error",
                    "message": f"Upstream error: {err}",
                },
            },
            status=err.status,
        )


async def _handle_streaming_passthrough(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict,
    data: dict,
    request: web.Request,
) -> web.StreamResponse:
    """Handle streaming passthrough request.

    Args:
        session: The client session for making the request.
        upstream_url: The full upstream URL.
        headers: Request headers.
        data: The JSON payload.
        request: The original web request.

    Returns:
        A web.StreamResponse with the upstream streaming response.
    """
    # Add streaming-specific headers
    headers.update(
        {
            "Accept": "text/event-stream",
            "Accept-Encoding": "identity",
        }
    )

    try:
        async with session.post(
            upstream_url, headers=headers, json=data
        ) as upstream_resp:
            if upstream_resp.status != 200:
                error_text = await upstream_resp.text()
                log_upstream_error(
                    upstream_resp.status,
                    error_text,
                    endpoint="native_anthropic",
                    is_streaming=True,
                )
                return web.json_response(
                    {
                        "error": f"Upstream API error: {upstream_resp.status} {error_text}"
                    },
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # Initialize the streaming response
            response_headers = {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }

            # Forward relevant headers from upstream
            response_headers.update(
                {
                    k: v
                    for k, v in upstream_resp.headers.items()
                    if k.lower()
                    not in (
                        "content-type",
                        "content-encoding",
                        "transfer-encoding",
                        "content-length",
                    )
                }
            )

            response = web.StreamResponse(
                status=upstream_resp.status,
                headers=response_headers,
            )

            response.enable_chunked_encoding()
            await response.prepare(request)

            # Stream the response chunks directly
            async for chunk in upstream_resp.content.iter_any():
                if chunk:
                    await response.write(chunk)

            await response.write_eof()
            return response

    except aiohttp.ClientResponseError as err:
        return web.json_response(
            {
                "type": "error",
                "error": {
                    "type": "upstream_api_error",
                    "message": f"Upstream error: {err}",
                },
            },
            status=err.status,
        )
