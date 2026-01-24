import asyncio
import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Awaitable, Callable, Dict, Optional, Union, cast

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..types import Completion, CompletionChoice
from ..types.completions import FINISH_REASONS
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.tokens import count_tokens, count_tokens_async
from ..utils.transports import pseudo_chunk_generator, send_off_sse
from ..utils.usage import create_usage, generate_usage_chunk
from .chat import (
    prepare_chat_request_data,
    send_non_streaming_request,
)

DEFAULT_STREAM = False


def transform_completions_compat(
    content: str,
    *,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    is_streaming: bool = False,
    finish_reason: Optional[FINISH_REASONS] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Converts a custom API response to an OpenAI-compatible completion API response.

    Args:
        content (str): The custom API response in JSON format.
        model_name (str): The model name used for generating the completion.
        create_timestamp (int): Timestamp indicating when the completion was created.
        prompt_tokens (int): Number of tokens in the input prompt.
        is_streaming (bool, optional): Indicates if the response is in streaming mode. Defaults to False.
        finish_reason (str, optional): Reason for the completion stop. Defaults to None.

    Returns:
        Union[Dict[str, Any], str]: OpenAI-compatible JSON response or an error message.
    """
    try:
        usage = None
        if not is_streaming:
            completion_tokens: int = count_tokens(content, model_name)
            usage = create_usage(
                prompt_tokens, completion_tokens, api_type="completion"
            )

        openai_response = Completion(
            id=f"cmpl-{uuid.uuid4().hex}",
            created=create_timestamp,
            model=model_name,
            choices=[
                CompletionChoice(
                    text=content,
                    index=0,
                    finish_reason=finish_reason or "stop",
                )
            ],
            usage=usage if not is_streaming else None,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred: {err}"}


async def transform_completions_compat_async(
    content: str,
    *,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    is_streaming: bool = False,
    finish_reason: Optional[FINISH_REASONS] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Asynchronously converts a custom API response to an OpenAI-compatible completion API response.

    Args:
        content (str): The custom API response in JSON format.
        model_name (str): The model name used for generating the completion.
        create_timestamp (int): Timestamp indicating when the completion was created.
        prompt_tokens (int): Number of tokens in the input prompt.
        is_streaming (bool, optional): Indicates if the response is in streaming mode. Defaults to False.
        finish_reason (str, optional): Reason for the completion stop. Defaults to None.

    Returns:
        Union[Dict[str, Any], str]: OpenAI-compatible JSON response or an error message.
    """
    try:
        usage = None
        if not is_streaming:
            completion_tokens: int = await count_tokens_async(content, model_name)
            usage = create_usage(
                prompt_tokens, completion_tokens, api_type="completion"
            )

        openai_response = Completion(
            id=f"cmpl-{uuid.uuid4().hex}",
            created=create_timestamp,
            model=model_name,
            choices=[
                CompletionChoice(
                    text=content,
                    index=0,
                    finish_reason=finish_reason or "stop",
                )
            ],
            usage=usage if not is_streaming else None,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred: {err}"}


async def _handle_pseudo_stream_completions(
    response: web.StreamResponse,
    upstream_resp: aiohttp.ClientResponse,
    data: Dict[str, Any],
    created_timestamp: int,
    prompt_tokens: int,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]], Callable[..., Awaitable[Dict[str, Any]]]
    ],
) -> None:
    """Handles fake streaming for completions by simulating chunked responses."""
    try:
        response_data = await upstream_resp.json()
        response_content = response_data.get("response", "")
    except (aiohttp.ContentTypeError, json.JSONDecodeError):
        response_content = await upstream_resp.text()

    if isinstance(response_content, dict):
        response_text = response_content.get("content", "") or json.dumps(
            response_content
        )
    else:
        response_text = str(response_content)

    total_processed = 0
    total_response_content = ""
    async for chunk_text in pseudo_chunk_generator(response_text):
        total_processed += len(chunk_text)
        total_response_content += chunk_text
        finish_reason = None
        if total_processed >= len(response_text):
            finish_reason = "stop"
        if asyncio.iscoroutinefunction(openai_compat_fn):
            chunk_json = await openai_compat_fn(
                chunk_text,
                model_name=data["model"],
                create_timestamp=created_timestamp,
                prompt_tokens=prompt_tokens,
                is_streaming=True,
                finish_reason=finish_reason,
            )
        else:
            chunk_json = openai_compat_fn(
                chunk_text,
                model_name=data["model"],
                create_timestamp=created_timestamp,
                prompt_tokens=prompt_tokens,
                is_streaming=True,
                finish_reason=finish_reason,
            )
        await send_off_sse(response, cast(Dict[str, Any], chunk_json))

    # Send usage chunk
    completion_tokens = await count_tokens_async(total_response_content, data["model"])
    usage_chunk = generate_usage_chunk(
        prompt_tokens,
        completion_tokens,
        api_type="completion",
        model=data["model"],
        created_timestamp=created_timestamp,
    )
    await send_off_sse(response, usage_chunk)


async def _handle_real_stream_completions(
    response: web.StreamResponse,
    upstream_resp: aiohttp.ClientResponse,
    data: Dict[str, Any],
    created_timestamp: int,
    prompt_tokens: int,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]], Callable[..., Awaitable[Dict[str, Any]]]
    ],
) -> None:
    """Handles real streaming for completions by processing chunks from the upstream response."""
    total_response_content = ""
    chunk_iterator = upstream_resp.content.iter_any()
    async for chunk_bytes in chunk_iterator:
        if chunk_bytes:
            chunk_text = chunk_bytes.decode()
            total_response_content += chunk_text
            if asyncio.iscoroutinefunction(openai_compat_fn):
                chunk_json = await openai_compat_fn(
                    chunk_text,
                    model_name=data["model"],
                    create_timestamp=created_timestamp,
                    prompt_tokens=prompt_tokens,
                    is_streaming=True,
                    finish_reason=None,
                )
            else:
                chunk_json = openai_compat_fn(
                    chunk_text,
                    model_name=data["model"],
                    create_timestamp=created_timestamp,
                    prompt_tokens=prompt_tokens,
                    is_streaming=True,
                    finish_reason=None,
                )
            await send_off_sse(response, cast(Dict[str, Any], chunk_json))

    # Send usage chunk
    completion_tokens = await count_tokens_async(total_response_content, data["model"])
    usage_chunk = generate_usage_chunk(
        prompt_tokens,
        completion_tokens,
        api_type="completion",
        model=data["model"],
        created_timestamp=created_timestamp,
    )
    await send_off_sse(response, usage_chunk)


async def send_streaming_completions_request(
    session: aiohttp.ClientSession,
    config: ArgoConfig,
    data: Dict[str, Any],
    request: web.Request,
    *,
    convert_to_openai: bool = False,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]], Callable[..., Awaitable[Dict[str, Any]]]
    ] = transform_completions_compat_async,
    pseudo_stream: bool = False,
) -> web.StreamResponse:
    """Sends a streaming request to an API and streams the response to the client."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "Accept-Encoding": "identity",
    }

    created_timestamp = int(time.time())
    # Calculate prompt tokens for usage calculation
    from ..utils.tokens import calculate_prompt_tokens_async

    prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])

    if convert_to_openai:
        response_headers = {"Content-Type": "text/event-stream"}
    else:
        response_headers = {"Content-Type": "text/plain; charset=utf-8"}

    if pseudo_stream:
        data["stream"] = False
        api_url = config.argo_url
    else:
        api_url = config.argo_stream_url

    try:
        async with session.post(api_url, headers=headers, json=data) as upstream_resp:
            if upstream_resp.status != 200:
                error_text = await upstream_resp.text()
                return web.json_response(
                    {
                        "error": f"Upstream API error: {upstream_resp.status} {error_text}"
                    },
                    status=upstream_resp.status,
                    content_type="application/json",
                )

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

            if pseudo_stream:
                await _handle_pseudo_stream_completions(
                    response,
                    upstream_resp,
                    data,
                    created_timestamp,
                    prompt_tokens,
                    openai_compat_fn,
                )
            else:
                await _handle_real_stream_completions(
                    response,
                    upstream_resp,
                    data,
                    created_timestamp,
                    prompt_tokens,
                    openai_compat_fn,
                )

            await response.write_eof()
            return response

    except aiohttp.ClientResponseError as err:
        return web.json_response(
            {"error": f"Upstream error: {err}"},
            status=err.status,
            content_type="application/json",
        )


async def proxy_request(
    request: web.Request,
) -> Union[web.Response, web.StreamResponse]:
    """Proxies incoming requests to the upstream API and processes responses.

    Args:
        request (web.Request): The incoming HTTP request object.

    Returns:
        web.Response or web.StreamResponse: The HTTP response sent back to the client.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        data: Dict[str, Any] = await request.json()
        stream: bool = data.get("stream", DEFAULT_STREAM)

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[completion] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        data = prepare_chat_request_data(data, config, model_registry)
        apply_username_passthrough(data, request, config.user)

        session = request.app["http_session"]

        if stream:
            return await send_streaming_completions_request(
                session,
                config,
                data,
                request,
                convert_to_openai=True,
                openai_compat_fn=transform_completions_compat_async,
                pseudo_stream=config.pseudo_stream,
            )
        else:
            return await send_non_streaming_request(
                session,
                config,
                data,
                convert_to_openai=True,
                openai_compat_fn=transform_completions_compat_async,
            )

    except ValueError as err:
        return web.json_response(
            {"error": str(err)},
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json",
        )
    except aiohttp.ClientError as err:
        error_message = f"HTTP error occurred: {err}"
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json",
        )
    except Exception as err:
        error_message = f"An unexpected error occurred: {err}"
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json",
        )
