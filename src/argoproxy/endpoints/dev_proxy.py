"""
Dev mode pure reverse proxy module.

This module provides a generic reverse proxy that forwards all requests
to upstream endpoints without any transformation, model resolution,
or tool call processing. Intended for developer use only.
"""

import aiohttp
from aiohttp import web

from ..utils.logging import log_debug, log_error, log_info


async def dev_proxy_handler(
    request: web.Request,
    upstream_url: str,
) -> web.StreamResponse:
    """Generic reverse proxy handler that forwards requests as-is.

    Args:
        request: The incoming aiohttp request.
        upstream_url: The full upstream URL to forward the request to.

    Returns:
        A web.Response or web.StreamResponse with the upstream response.
    """
    session: aiohttp.ClientSession = request.app["http_session"]

    log_info(
        f"[DEV PROXY] {request.method} {request.path} -> {upstream_url}",
        context="dev_proxy",
    )

    # Forward headers, excluding hop-by-hop headers
    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
    forward_headers = {
        k: v for k, v in request.headers.items() if k.lower() not in hop_by_hop
    }

    # Read request body
    body = await request.read()

    try:
        async with session.request(
            method=request.method,
            url=upstream_url,
            headers=forward_headers,
            data=body if body else None,
            allow_redirects=False,
        ) as upstream_resp:
            # Check if the response looks like a streaming response
            content_type = upstream_resp.headers.get("Content-Type", "")
            is_streaming = (
                "text/event-stream" in content_type
                or "chunked" in upstream_resp.headers.get("Transfer-Encoding", "")
            )

            if is_streaming:
                return await _handle_streaming(upstream_resp, request)
            else:
                return await _handle_non_streaming(upstream_resp)

    except aiohttp.ClientError as err:
        log_error(f"Upstream request failed: {err}", context="dev_proxy")
        return web.json_response(
            {"error": f"Upstream request failed: {err}"},
            status=502,
        )
    except Exception as err:
        log_error(f"Unexpected error: {err}", context="dev_proxy")
        return web.json_response(
            {"error": f"Unexpected error: {err}"},
            status=500,
        )


async def _handle_non_streaming(
    upstream_resp: aiohttp.ClientResponse,
) -> web.Response:
    """Handle a non-streaming upstream response.

    Args:
        upstream_resp: The upstream response object.

    Returns:
        A web.Response with the upstream response body and headers.
    """
    body = await upstream_resp.read()

    # Build response headers, excluding hop-by-hop
    skip_headers = {
        "content-encoding",
        "transfer-encoding",
        "content-length",
        "connection",
    }
    resp_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in skip_headers
    }

    return web.Response(
        body=body,
        status=upstream_resp.status,
        headers=resp_headers,
    )


async def _handle_streaming(
    upstream_resp: aiohttp.ClientResponse,
    request: web.Request,
) -> web.StreamResponse:
    """Handle a streaming upstream response.

    Args:
        upstream_resp: The upstream response object.
        request: The original client request (needed to prepare StreamResponse).

    Returns:
        A web.StreamResponse that streams chunks from upstream.
    """
    response_headers = {
        "Content-Type": upstream_resp.headers.get("Content-Type", "text/event-stream"),
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }

    response = web.StreamResponse(
        status=upstream_resp.status,
        headers=response_headers,
    )
    response.enable_chunked_encoding()
    await response.prepare(request)

    async for chunk in upstream_resp.content.iter_any():
        if chunk:
            await response.write(chunk)

    await response.write_eof()
    return response


def register_dev_routes(app: web.Application, config) -> None:
    """Register dev mode proxy routes on the application.

    Args:
        app: The aiohttp web application.
        config: The ArgoConfig instance.
    """
    base_url = config.argo_base_url  # e.g., https://apps-dev.inside.anl.gov/argoapi

    # Route definitions: (local_prefix, upstream_base)
    route_map = [
        ("/chat/", f"{base_url}/api/v1/resource/chat/"),
        ("/stream/", f"{base_url}/api/v1/resource/streamchat/"),
        ("/embed/", f"{base_url}/api/v1/resource/embed/"),
        ("/message/", f"{base_url}/message/"),  # Anthropic compatible
        ("/v1/", f"{base_url}/v1/"),  # OpenAI compatible
    ]

    for local_prefix, upstream_base in route_map:
        _add_prefix_route(app, local_prefix, upstream_base)

    log_debug(
        f"Registered {len(route_map)} dev proxy route groups", context="dev_proxy"
    )


def _add_prefix_route(
    app: web.Application,
    local_prefix: str,
    upstream_base: str,
) -> None:
    """Add a catch-all route for a given prefix.

    Args:
        app: The aiohttp web application.
        local_prefix: The local URL prefix (e.g., "/chat/").
        upstream_base: The upstream base URL to forward to.
    """
    # Use a path pattern like /chat/{path:.*} to catch all sub-paths
    pattern = local_prefix + "{path:.*}"

    async def handler(
        request: web.Request, _upstream_base=upstream_base
    ) -> web.StreamResponse:
        path = request.match_info.get("path", "")
        upstream_url = f"{_upstream_base}{path}"
        # Preserve query string
        if request.query_string:
            upstream_url = f"{upstream_url}?{request.query_string}"
        return await dev_proxy_handler(request, upstream_url)

    app.router.add_route("*", pattern, handler)
