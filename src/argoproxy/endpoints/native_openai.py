"""
Native OpenAI endpoint passthrough module.

This module provides direct passthrough to the native OpenAI-compatible endpoint
without any transformation or processing.
"""

import json
from http import HTTPStatus
from typing import Union

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..tool_calls.input_handle import handle_tools
from ..utils.image_processing import process_chat_images
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.models import determine_model_family


async def proxy_native_openai_request(
    request: web.Request,
    endpoint_path: str,
) -> Union[web.Response, web.StreamResponse]:
    """
    Proxies requests directly to the native OpenAI endpoint without any transformation.

    This is a pure passthrough - all request data is forwarded as-is to the upstream
    native OpenAI endpoint, and responses are returned without modification.

    Args:
        request: The client's web request object.
        endpoint_path: The endpoint path to append to the base URL (e.g., "chat/completions").

    Returns:
        A web.Response or web.StreamResponse with the response from the upstream API.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        # Get the incoming request data
        data = await request.json()

        if config.verbose:
            logger.info(make_bar(f"[native-openai/{endpoint_path}] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        # Use the shared HTTP session from app context
        session = request.app["http_session"]

        # Resolve model name if present (supports argo: aliases)
        if "model" in data:
            original_model = data["model"]
            # Determine model type based on endpoint
            model_type = "embed" if endpoint_path == "embeddings" else "chat"
            data["model"] = model_registry.resolve_model_name(
                original_model, model_type
            )

            if config.verbose and data["model"] != original_model:
                logger.info(f"Model name resolved: {original_model} -> {data['model']}")

        # Process image URLs for chat endpoints (download and convert to base64)
        if endpoint_path == "chat/completions":
            data = await process_chat_images(session, data, config)

            # Handle tool calls if present
            if "tools" in data:
                model_family = determine_model_family(data.get("model", "gpt4o"))
                if model_family in ["google", "unknown"]:
                    # Use prompting based tool handling for Google and unknown models
                    data = handle_tools(data, native_tools=False)
                else:
                    # Use native tool handling for OpenAI and Anthropic models
                    data = handle_tools(data, native_tools=config.native_tools)

        # Apply username passthrough if enabled
        apply_username_passthrough(data, request, config.user)

        # Construct the full upstream URL
        upstream_url = f"{config.native_openai_base_url}{endpoint_path}"

        # Check if this is a streaming request
        stream = data.get("stream", False)

        # Prepare headers - forward most headers from the original request
        headers = {
            "Content-Type": "application/json",
        }

        # Forward authorization header if present
        if "Authorization" in request.headers:
            headers["Authorization"] = request.headers["Authorization"]

        if config.verbose:
            logger.info(f"Forwarding to: {upstream_url}")
            logger.info(f"Stream mode: {stream}")

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
        logger.error(f"ValueError: {err}")
        return web.json_response(
            {"error": str(err)},
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json",
        )
    except aiohttp.ClientError as err:
        error_message = f"HTTP error occurred: {err}"
        logger.error(error_message)
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json",
        )
    except Exception as err:
        error_message = f"An unexpected error occurred: {err}"
        logger.error(error_message)
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json",
        )


async def _handle_non_streaming_passthrough(
    session: aiohttp.ClientSession,
    upstream_url: str,
    headers: dict,
    data: dict,
) -> web.Response:
    """
    Handle non-streaming passthrough request.

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
                "object": "error",
                "message": f"Upstream error: {err}",
                "type": "upstream_api_error",
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
    """
    Handle streaming passthrough request.

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
                "object": "error",
                "message": f"Upstream error: {err}",
                "type": "upstream_api_error",
            },
            status=err.status,
        )
