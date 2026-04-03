"""Thin passthrough for endpoints that don't need format conversion.

Used in universal mode for /v1/embeddings — requests are forwarded to the
native OpenAI-compatible upstream with minimal processing (model alias
resolution and username passthrough only).
"""

import json
from http import HTTPStatus

import aiohttp
from aiohttp import web

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..utils.logging import (
    log_converted_request,
    log_debug,
    log_error,
    log_original_request,
    log_upstream_error,
)
from ..utils.misc import (
    ARGO_AUTH_ERROR_MESSAGE,
    apply_username_passthrough,
    check_response_for_argo_warning,
    contains_argo_auth_warning,
)


async def proxy_embeddings_request(
    request: web.Request,
) -> web.Response:
    """Proxy an embeddings request to the native OpenAI upstream.

    Args:
        request: The incoming client request.

    Returns:
        The upstream response forwarded to the client.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        data = await request.json()

        log_original_request(
            data, verbose=config.verbose, max_history_items=config.max_log_history
        )

        session = request.app["http_session"]

        if "model" in data:
            original_model = data["model"]
            data["model"] = model_registry.resolve_model_name(
                original_model, model_type="embed"
            )
            if config.verbose and data["model"] != original_model:
                log_debug(
                    f"Model name resolved: {original_model} -> {data['model']}",
                    context="passthrough",
                )

        apply_username_passthrough(data, request, config.user)

        upstream_url = f"{config.native_openai_base_url}/embeddings"

        headers = {"Content-Type": "application/json"}
        if "Authorization" in request.headers:
            headers["Authorization"] = request.headers["Authorization"]

        log_converted_request(
            data, verbose=config.verbose, max_history_items=config.max_log_history
        )

        if config.verbose:
            log_debug(f"Forwarding to: {upstream_url}", context="passthrough")

        async with session.post(
            upstream_url, headers=headers, json=data
        ) as upstream_resp:
            if upstream_resp.status != 200:
                error_text = await upstream_resp.text()
                log_upstream_error(
                    upstream_resp.status,
                    error_text,
                    endpoint="passthrough",
                    is_streaming=False,
                )
                if contains_argo_auth_warning(error_text):
                    log_error(ARGO_AUTH_ERROR_MESSAGE, context="passthrough")
                    return web.json_response(
                        {
                            "error": {
                                "message": ARGO_AUTH_ERROR_MESSAGE,
                                "type": "argo_auth_error",
                                "code": "argo_auth_warning",
                            }
                        },
                        status=HTTPStatus.FORBIDDEN,
                    )
                try:
                    error_json = json.loads(error_text)
                    return web.json_response(
                        error_json,
                        status=upstream_resp.status,
                        content_type="application/json",
                    )
                except json.JSONDecodeError:
                    return web.json_response(
                        {
                            "error": f"Upstream error {upstream_resp.status}: {error_text}"
                        },
                        status=upstream_resp.status,
                        content_type="application/json",
                    )

            response_data = await upstream_resp.json()

            if check_response_for_argo_warning(response_data, "openai"):
                log_error(ARGO_AUTH_ERROR_MESSAGE, context="passthrough")
                return web.json_response(
                    {
                        "error": {
                            "message": ARGO_AUTH_ERROR_MESSAGE,
                            "type": "argo_auth_error",
                            "code": "argo_auth_warning",
                        }
                    },
                    status=HTTPStatus.FORBIDDEN,
                )

            return web.json_response(
                response_data,
                status=upstream_resp.status,
                content_type="application/json",
            )

    except ValueError as err:
        log_error(f"ValueError: {err}", context="passthrough")
        return web.json_response(
            {"error": str(err)},
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json",
        )
    except aiohttp.ClientError as err:
        error_message = f"HTTP error occurred: {err}"
        log_error(error_message, context="passthrough")
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json",
        )
    except Exception as err:
        error_message = f"An unexpected error occurred: {err}"
        log_error(error_message, context="passthrough")
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json",
        )
