import asyncio
import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union, cast

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..tool_calls.input_handle import handle_tools
from ..tool_calls.output_handle import (
    ToolInterceptor,
    tool_calls_to_openai,
    tool_calls_to_openai_stream,
)
from ..types import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChoiceDelta,
    NonStreamChoice,
    StreamChoice,
)
from ..types.chat_completion import FINISH_REASONS
from ..utils.image_processing import process_chat_images, sanitize_data_for_logging
from ..utils.input_handle import (
    handle_multiple_entries_prompt,
    handle_no_sys_msg,
    handle_option_2_input,
    scrutinize_message_entries,
)
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.models import determine_model_family
from ..utils.tokens import (
    calculate_prompt_tokens_async,
    count_tokens_async,
)
from ..utils.transports import pseudo_chunk_generator, send_off_sse
from ..utils.usage import (
    calculate_completion_tokens_async,
    create_usage,
    generate_usage_chunk,
)

DEFAULT_MODEL = "argo:gpt-4o"


async def transform_chat_completions_streaming_async(
    content: Optional[str] = None,
    *,
    model_name: str,
    create_timestamp: int,
    finish_reason: FINISH_REASONS = "stop",
    tool_calls: Optional[Dict[str, Any]] = None,
    tc_index: int = 0,
    is_first_chunk: bool = False,
    chunk_id: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Transforms the custom API response into a streaming OpenAI-compatible format.

    Args:
        content: The text content of the delta.
        model_name: The model name.
        create_timestamp: The creation timestamp.
        finish_reason: The finish reason for the completion.
        tool_calls: The tool calls data.
        tc_index: The tool call index.
        is_first_chunk: Whether this is the first chunk (should include role).
        chunk_id: Optional ID for the chunk. If not provided, generates a new one.
    """
    try:
        # Handle tool calls for streaming
        tool_calls_obj = None
        if tool_calls:
            logger.warning(f"transforming tool_calls: {tool_calls}")
            tool_calls_obj = [
                tool_calls_to_openai_stream(
                    tool_calls,
                    tc_index=tc_index,
                    api_format="chat_completion",
                )
            ]

        # For the first chunk, include role: assistant
        delta = ChoiceDelta(
            content=content,
            tool_calls=tool_calls_obj,
            role="assistant" if is_first_chunk else None,
        )

        openai_response = ChatCompletionChunk(
            id=chunk_id if chunk_id is not None else str(uuid.uuid4().hex),
            created=create_timestamp,
            model=model_name,
            choices=[
                StreamChoice(
                    index=0,
                    delta=delta,
                    finish_reason=finish_reason,
                )
            ],
        )
        return openai_response.model_dump()
    except Exception as err:
        return {"error": f"An error occurred in streaming response: {err}"}


async def transform_chat_completions_non_streaming_async(
    content: Optional[str] = None,
    *,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    finish_reason: FINISH_REASONS = "stop",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Asynchronously transforms the custom API response into a non-streaming OpenAI-compatible format.
    """
    try:
        # Calculate token usage asynchronously
        completion_tokens = await calculate_completion_tokens_async(
            content, tool_calls, model_name, api_format="chat_completion"
        )
        usage = create_usage(
            prompt_tokens, completion_tokens, api_type="chat_completion"
        )

        # Handle tool calls
        tool_calls_obj = None
        if tool_calls and isinstance(tool_calls, list):
            tool_calls_obj = tool_calls_to_openai(
                tool_calls, api_format="chat_completion"
            )

        openai_response = ChatCompletion(
            id=str(uuid.uuid4().hex),
            created=create_timestamp,
            model=model_name,
            choices=[
                NonStreamChoice(
                    index=0,
                    message=ChatCompletionMessage(
                        content=content,
                        tool_calls=tool_calls_obj,
                    ),
                    finish_reason=finish_reason,
                )
            ],
            usage=usage,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred in non-streaming response: {err}"}


def prepare_chat_request_data(
    data: Dict[str, Any],
    config: ArgoConfig,
    model_registry: ModelRegistry,
    *,
    enable_tools: bool = False,
) -> Dict[str, Any]:
    """
    Prepares chat request data for upstream APIs based on model type.

    Args:
        data: The incoming request data.
        config: The ArgoConfig object containing configuration settings.
        model_registry: The ModelRegistry object containing model mappings.
        enable_tools: Determines whether we enables tool calls related fields - tools, tool_choice, parallel_tool_calls.

    Returns:
        The modified request data.
    """

    # Automatically replace or insert user information
    data["user"] = config.user

    # Remap the model name
    if "model" not in data:
        data["model"] = DEFAULT_MODEL
    data["model"] = model_registry.resolve_model_name(data["model"], model_type="chat")

    # Scrutinize and normalize message entries (includes system/developer content normalization)
    data = scrutinize_message_entries(data)

    # Convert prompt to list if necessary
    if "prompt" in data and not isinstance(data["prompt"], list):
        data["prompt"] = [data["prompt"]]

    if enable_tools:
        model_family = determine_model_family(data["model"])
        if model_family == "unknown":
            data = handle_tools(
                data, native_tools=False
            )  # use prompting based tool handling for unknown models
        else:  # openai, anthropic, google
            data = handle_tools(data, native_tools=config.native_tools)
    else:
        # remove incompatible fields for direct ARGO API calls
        data.pop("tools", None)
        data.pop("tool_choice", None)
        data.pop("parallel_tool_calls", None)

    # Apply transformations based on model type
    if data["model"] in model_registry.option_2_input_models:
        # Transform data for models requiring `system` and `prompt` structure only
        data = handle_option_2_input(data)

    # flatten the list of strings into a single string in case of multiple prompts
    if isinstance(data.get("prompt"), list):
        data["prompt"] = ["\n\n".join(data["prompt"]).strip()]

    if data["model"] in model_registry.no_sys_msg_models:
        data = handle_no_sys_msg(data)

    data = handle_multiple_entries_prompt(data)

    # if config.verbose:
    #     logger.info(make_bar("Transformed Request"))
    #     logger.info(f"{json.dumps(data, indent=2)}")

    return data


async def send_non_streaming_request(
    session: aiohttp.ClientSession,
    config: ArgoConfig,
    data: Dict[str, Any],
    *,
    convert_to_openai: bool = False,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]], Callable[..., Awaitable[Dict[str, Any]]]
    ] = transform_chat_completions_non_streaming_async,
) -> web.Response:
    """Sends a non-streaming request to an API and processes the response.

    Args:
        session: The client session for making the request.
        config: The configuration object containing the API URLs.
        data: The JSON payload of the request.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.

    Returns:
        A web.Response with the processed JSON data.
    """
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(
            config.argo_url, headers=headers, json=data
        ) as upstream_resp:
            try:
                response_data = await upstream_resp.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                return web.json_response(
                    {
                        "object": "error",
                        "message": "Upstream error: Invalid JSON response from upstream server",
                        "type": "upstream_invalid_json",
                    },
                    status=502,
                )

            # Handle both legacy and new response formats
            response_content = response_data.get("response")
            if response_content is None:
                return web.json_response(
                    {
                        "object": "error",
                        "message": "Upstream model returned no response. Please try different request parameters.",
                        "type": "upstream_no_response",
                    },
                    status=502,
                )

            if not convert_to_openai:  # direct pass-through
                return web.json_response(
                    response_data,
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # convert_to_openai is True
            prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])
            cs = ToolInterceptor()

            # Process response content with the updated ToolInterceptor
            tool_calls, clean_text = cs.process(
                response_content,
                determine_model_family(data["model"]),
                request_data=data,
            )
            finish_reason = "tool_calls" if tool_calls else "stop"

            if asyncio.iscoroutinefunction(openai_compat_fn):
                openai_response = await openai_compat_fn(
                    clean_text,
                    model_name=data.get("model"),
                    create_timestamp=int(time.time()),
                    prompt_tokens=prompt_tokens,
                    finish_reason=finish_reason,
                    tool_calls=tool_calls,
                )
            else:
                openai_response = openai_compat_fn(
                    clean_text,
                    model_name=data.get("model"),
                    create_timestamp=int(time.time()),
                    prompt_tokens=prompt_tokens,
                    finish_reason=finish_reason,
                    tool_calls=tool_calls,
                )
            return web.json_response(
                openai_response,
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


async def _handle_pseudo_stream(
    response: web.StreamResponse,
    upstream_resp: aiohttp.ClientResponse,
    data: Dict[str, Any],
    created_timestamp: int,
    prompt_tokens: int,
    convert_to_openai: bool,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]],
        Callable[..., Awaitable[Dict[str, Any]]],
    ],
) -> None:
    """
    Handles fake streaming by simulating chunked responses.

    Args:
        response: The web.StreamResponse object for sending SSE events.
        upstream_resp: The upstream aiohttp.ClientResponse object.
        data: The JSON payload of the request.
        created_timestamp: The timestamp when the request was created.
        prompt_tokens: The number of tokens in the input prompt.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.
    """
    logger.warning("Pseudo streaming!")

    try:
        response_data = await upstream_resp.json()
        response_content = response_data.get("response", "")
    except (aiohttp.ContentTypeError, json.JSONDecodeError) as e:
        response_content = await upstream_resp.text()
        logger.warning(f"Upstream response is not JSON in pseudo_stream mode: {e}")
    if convert_to_openai:
        # Generate a shared ID for all chunks in this stream
        shared_id = str(uuid.uuid4().hex)
        cs = ToolInterceptor()
        # Process response content with the updated ToolInterceptor
        tool_calls, cleaned_text = cs.process(
            response_content, determine_model_family(data["model"]), request_data=data
        )
        is_first_chunk = True

        if tool_calls:
            for i, tc_dict in enumerate(tool_calls):
                if asyncio.iscoroutinefunction(openai_compat_fn):
                    chunk_json = await openai_compat_fn(
                        None,
                        model_name=data["model"],
                        create_timestamp=created_timestamp,
                        prompt_tokens=prompt_tokens,
                        is_streaming=True,
                        finish_reason="tool_calls",
                        tool_calls=tc_dict,
                        tc_index=i,
                        is_first_chunk=is_first_chunk,
                        chunk_id=shared_id,
                    )
                else:
                    chunk_json = openai_compat_fn(
                        None,
                        model_name=data["model"],
                        create_timestamp=created_timestamp,
                        prompt_tokens=prompt_tokens,
                        is_streaming=True,
                        finish_reason="tool_calls",
                        tool_calls=tc_dict,
                        tc_index=i,
                        is_first_chunk=is_first_chunk,
                        chunk_id=shared_id,
                    )
                await send_off_sse(response, cast(Dict[str, Any], chunk_json))
                is_first_chunk = False  # Only the first chunk gets role: assistant

        total_processed = 0
        total_response_content = ""
        async for chunk_text in pseudo_chunk_generator(cleaned_text):
            total_processed += len(chunk_text)
            total_response_content += chunk_text
            finish_reason = None
            if total_processed >= len(cleaned_text):
                finish_reason = "tool_calls" if tool_calls else "stop"
            if asyncio.iscoroutinefunction(openai_compat_fn):
                chunk_json = await openai_compat_fn(
                    chunk_text,
                    model_name=data["model"],
                    create_timestamp=created_timestamp,
                    prompt_tokens=prompt_tokens,
                    is_streaming=True,
                    finish_reason=finish_reason,
                    tool_calls=None,
                    is_first_chunk=is_first_chunk,
                    chunk_id=shared_id,
                )
            else:
                chunk_json = openai_compat_fn(
                    chunk_text,
                    model_name=data["model"],
                    create_timestamp=created_timestamp,
                    prompt_tokens=prompt_tokens,
                    is_streaming=True,
                    finish_reason=finish_reason,
                    tool_calls=None,
                    is_first_chunk=is_first_chunk,
                    chunk_id=shared_id,
                )
            await send_off_sse(response, cast(Dict[str, Any], chunk_json))
            is_first_chunk = False  # Only the first chunk gets role: assistant

        # Count completion tokens and send usage
        completion_tokens = await count_tokens_async(
            total_response_content, data["model"]
        )
        usage_chunk = generate_usage_chunk(
            prompt_tokens,
            completion_tokens,
            api_type="chat_completion",
            model=data["model"],
            created_timestamp=created_timestamp,
            chunk_id=shared_id,
        )
        await send_off_sse(response, usage_chunk)
    else:
        # For non-OpenAI conversion, we need to handle the response_content appropriately
        if isinstance(response_content, dict):
            # If it's a dict, convert to string for streaming
            response_text = response_content.get("content", "") or json.dumps(
                response_content
            )
        else:
            response_text = str(response_content)
        async for chunk_text in pseudo_chunk_generator(response_text):
            await send_off_sse(response, chunk_text.encode())


async def _handle_real_stream(
    response: web.StreamResponse,
    upstream_resp: aiohttp.ClientResponse,
    data: Dict[str, Any],
    created_timestamp: int,
    prompt_tokens: int,
    convert_to_openai: bool,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]],
        Callable[..., Awaitable[Dict[str, Any]]],
    ],
) -> None:
    """
    Handles real streaming by processing chunks from the upstream response.

    Args:
        response: The web.StreamResponse object for sending SSE events.
        upstream_resp: The upstream aiohttp.ClientResponse object.
        data: The JSON payload of the request.
        created_timestamp: The timestamp when the request was created.
        prompt_tokens: The number of tokens in the input prompt.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.
    """
    if convert_to_openai:
        # Generate a shared ID for all chunks in this stream
        shared_id = str(uuid.uuid4().hex)
        # Collect all chunks for usage calculation
        total_response_content = ""
        chunk_iterator = upstream_resp.content.iter_any()
        is_first_chunk = True

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
                        tool_calls=None,
                        is_first_chunk=is_first_chunk,
                        chunk_id=shared_id,
                    )
                else:
                    chunk_json = openai_compat_fn(
                        chunk_text,
                        model_name=data["model"],
                        create_timestamp=created_timestamp,
                        prompt_tokens=prompt_tokens,
                        is_streaming=True,
                        finish_reason=None,
                        tool_calls=None,
                        is_first_chunk=is_first_chunk,
                        chunk_id=shared_id,
                    )
                await send_off_sse(response, cast(Dict[str, Any], chunk_json))
                is_first_chunk = False  # Only the first chunk gets role: assistant

        # Count completion tokens and send usage
        completion_tokens = await count_tokens_async(
            total_response_content, data["model"]
        )
        usage_chunk = generate_usage_chunk(
            prompt_tokens,
            completion_tokens,
            api_type="chat_completion",
            model=data["model"],
            created_timestamp=created_timestamp,
            chunk_id=shared_id,
        )
        await send_off_sse(response, usage_chunk)
    else:
        # For non-OpenAI conversion, forward chunks directly
        chunk_iterator = upstream_resp.content.iter_any()
        async for chunk_bytes in chunk_iterator:
            await send_off_sse(response, chunk_bytes)


async def send_streaming_request(
    session: aiohttp.ClientSession,
    config: ArgoConfig,
    data: Dict[str, Any],
    request: web.Request,
    *,
    convert_to_openai: bool = False,
    openai_compat_fn: Union[
        Callable[..., Dict[str, Any]],
        Callable[..., Awaitable[Dict[str, Any]]],
    ] = transform_chat_completions_streaming_async,
    pseudo_stream: bool = False,
) -> web.StreamResponse:
    """Sends a streaming request to an API and streams the response to the client.

    Args:
        session: The client session for making the request.
        config: The configuration object containing the API URLs.
        data: The JSON payload of the request.
        request: The web request used for streaming responses.
        convert_to_openai: If True, converts the response to OpenAI format.
        openai_compat_fn: Function for conversion to OpenAI-compatible format.
        pseudo_stream: If True, simulates streaming by sending the response in chunks.
    """

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "Accept-Encoding": "identity",
    }

    # Set response headers based on the mode
    created_timestamp = int(time.time())
    prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])
    if convert_to_openai:
        response_headers = {"Content-Type": "text/event-stream"}
    else:
        response_headers = {"Content-Type": "text/plain; charset=utf-8"}

    if pseudo_stream:
        data["stream"] = False  # disable streaming in upstream request
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

            # Initialize the streaming response
            response_headers.update(
                {
                    k: v
                    for k, v in upstream_resp.headers.items()
                    if k.lower()
                    not in (
                        "content-type",
                        "content-encoding",
                        "transfer-encoding",
                        "content-length",  # in case of fake streaming
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
                await _handle_pseudo_stream(
                    response,
                    upstream_resp,
                    data,
                    created_timestamp,
                    prompt_tokens,
                    convert_to_openai,
                    openai_compat_fn,
                )
            else:
                await _handle_real_stream(
                    response,
                    upstream_resp,
                    data,
                    created_timestamp,
                    prompt_tokens,
                    convert_to_openai,
                    openai_compat_fn,
                )

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


async def proxy_request(
    request: web.Request,
    *,
    convert_to_openai: bool = True,
) -> Union[web.Response, web.StreamResponse]:
    """Proxies the client's request to an upstream API, handling response streaming and conversion.

    Args:
        request: The client's web request object.
        convert_to_openai: If True, translates the response to an OpenAI-compatible format.

    Returns:
        A web.Response or web.StreamResponse with the final response from the upstream API.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]
    try:
        # Retrieve the incoming JSON data from request if input_data is not provided

        data = await request.json()
        stream = data.get("stream", False)
        # use pseudo_stream to handle tools
        pseudo_stream_override = False
        if "tools" in data:
            pseudo_stream_override = True

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[chat] input"))
            logger.info(json.dumps(sanitize_data_for_logging(data), indent=4))
            logger.info(make_bar())

        # Use the shared HTTP session from app context for connection pooling
        session = request.app["http_session"]

        # Process image URLs before other transformations
        data = await process_chat_images(session, data, config)

        # Prepare the request data (includes message scrutinization and normalization)
        data = prepare_chat_request_data(
            data, config, model_registry, enable_tools=True
        )

        # Apply username passthrough if enabled
        apply_username_passthrough(data, request, config.user)

        logger.warning(
            f"[chat] data: {json.dumps(sanitize_data_for_logging(data), indent=4)}"
        )

        if stream:
            return await send_streaming_request(
                session,
                config,
                data,
                request,
                convert_to_openai=convert_to_openai,
                openai_compat_fn=transform_chat_completions_streaming_async,
                pseudo_stream=config.pseudo_stream or pseudo_stream_override,
            )
        else:
            return await send_non_streaming_request(
                session,
                config,
                data,
                convert_to_openai=convert_to_openai,
                openai_compat_fn=transform_chat_completions_non_streaming_async,
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
