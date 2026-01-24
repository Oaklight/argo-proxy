import asyncio
import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..tool_calls.output_handle import tool_calls_to_openai
from ..types import (
    Response,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseInProgressEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
)
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.tokens import (
    calculate_prompt_tokens_async,
    count_tokens,
    count_tokens_async,
)
from ..utils.usage import calculate_completion_tokens_async, create_usage
from ..utils.transports import send_off_sse
from .chat import (
    prepare_chat_request_data,
    send_non_streaming_request,
)

INCOMPATIBLE_INPUT_FIELDS = {
    "include",
    "metadata",
    "parallel_tool_calls",
    "previous_response_id",
    "reasoning",
    "service_tier",
    "store",
    "text",
    "tool_choice",
    "tools",
    "truncation",
}


def transform_non_streaming_response(
    content: str,
    *,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Transforms a non-streaming custom API response into a format compatible with OpenAI's API.

    Args:
        content: The response obtained from the custom API.
        model_name: The name of the model that generated the completion.
        create_timestamp: The creation timestamp of the completion.
        prompt_tokens: The number of tokens in the input prompt.

    Returns:
        A dictionary representing the OpenAI-compatible JSON response.
    """
    try:
        # Note: using sync count_tokens here as the original function was sync.
        # However, our unified calculate_completion_tokens_async is async.
        # Since transform_non_streaming_response is sync, we'll keep it as is or
        # just use the async version in the async counterpart.
        completion_tokens = count_tokens(content, model_name)
        if tool_calls:
            if (
                tool_calls
                and len(tool_calls) > 0
                and hasattr(tool_calls[0], "serialize")
            ):
                serializable_tool_calls = [
                    tc.serialize("openai-response") for tc in tool_calls
                ]
            else:
                serializable_tool_calls = tool_calls
            tool_tokens = count_tokens(json.dumps(serializable_tool_calls), model_name)
            completion_tokens += tool_tokens
        usage = create_usage(prompt_tokens, completion_tokens, api_type="response")

        output = []
        if tool_calls:
            output.extend(tool_calls_to_openai(tool_calls, api_format="response"))
        output.append(
            ResponseOutputMessage(
                id=f"msg_{uuid.uuid4().hex}",
                status="completed",
                content=[
                    ResponseOutputText(
                        text=content,
                    )
                ],
            )
        )

        openai_response = Response(
            id=f"resp_{uuid.uuid4().hex}",
            created_at=create_timestamp,
            model=model_name,
            output=output,
            status="completed",
            usage=usage,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        logger.error(f"Error decoding JSON: {err}")
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        logger.error(f"An error occurred: {err}")
        return {"error": f"An error occurred: {err}"}


async def transform_non_streaming_response_async(
    content: str,
    *,
    model_name: str,
    create_timestamp: int,
    prompt_tokens: int,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Asynchronously transforms a non-streaming custom API response into a format compatible with OpenAI's API.

    Args:
        content: The response obtained from the custom API.
        model_name: The name of the model that generated the completion.
        create_timestamp: The creation timestamp of the completion.
        prompt_tokens: The number of tokens in the input prompt.

    Returns:
        A dictionary representing the OpenAI-compatible JSON response.
    """
    try:
        completion_tokens = await calculate_completion_tokens_async(
            content, tool_calls, model_name, api_format="response"
        )
        usage = create_usage(prompt_tokens, completion_tokens, api_type="response")

        output = []
        if tool_calls:
            output.extend(tool_calls_to_openai(tool_calls, api_format="response"))
        output.append(
            ResponseOutputMessage(
                id=f"msg_{uuid.uuid4().hex}",
                status="completed",
                content=[
                    ResponseOutputText(
                        text=content,
                    )
                ],
            )
        )

        openai_response = Response(
            id=f"resp_{uuid.uuid4().hex}",
            created_at=create_timestamp,
            model=model_name,
            output=output,
            status="completed",
            usage=usage,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        logger.error(f"Error decoding JSON: {err}")
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        logger.error(f"An error occurred: {err}")
        return {"error": f"An error occurred: {err}"}


def transform_streaming_response(
    custom_response: Any,
    **kwargs,
) -> Dict[str, Any]:
    """
    Transforms a streaming custom API response into a format compatible with OpenAI's API.

    Args:
        custom_response: The response obtained from the custom API.
        model_name: The name of the model that generated the completion.

    Returns:
        A dictionary representing the OpenAI-compatible JSON response.
    """
    try:
        if isinstance(custom_response, str):
            custom_response_dict = json.loads(custom_response)
        else:
            custom_response_dict = custom_response

        response_text = custom_response_dict.get("response", "")
        content_index = kwargs.get("content_index", 0)
        output_index = kwargs.get("output_index", 0)
        sequence_number = kwargs.get("sequence_number", 0)
        id = kwargs.get("id", f"msg_{str(uuid.uuid4().hex)}")

        openai_response = ResponseTextDeltaEvent(
            content_index=content_index,
            delta=response_text,
            item_id=id,
            output_index=output_index,
            sequence_number=sequence_number,
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        logger.error(f"Error decoding JSON: {err}")
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        logger.error(f"An error occurred: {err}")
        return {"error": f"An error occurred: {err}"}


def prepare_request_data(
    data: Dict[str, Any], config: ArgoConfig, model_registry: ModelRegistry
) -> Dict[str, Any]:
    """
    Prepares the incoming request data for response models.

    Args:
        data: The original request data.
        config: Application configuration.
        model_registry: The ModelRegistry object containing model mappings.

    Returns:
        The modified and prepared request data.
    """
    # Insert instructions and format messages from input
    messages = data.get("input", [])
    if instructions := data.get("instructions", ""):
        messages.insert(0, {"role": "system", "content": instructions})
        del data["instructions"]
    data["messages"] = messages
    del data["input"]

    if max_tokens := data.get("max_output_tokens", None):
        data["max_tokens"] = max_tokens
        del data["max_output_tokens"]

    # Use shared chat request preparation logic
    data = prepare_chat_request_data(data, config, model_registry)

    # Drop unsupported fields
    for key in list(data.keys()):
        if key in INCOMPATIBLE_INPUT_FIELDS:
            del data[key]

    return data


async def _handle_pseudo_stream_events(
    response: web.StreamResponse,
    response_data: Dict[str, Any],
    output_msg: ResponseOutputMessage,
    content_part: ResponseContentPartAddedEvent,
    output_item: ResponseOutputItemAddedEvent,
    sequence_number: int,
) -> Tuple[int, str]:
    """
    Handles fake streaming events by simulating chunked responses.

    Args:
        response: The web.StreamResponse object for sending SSE events.
        response_data: The JSON payload of the upstream response.
        output_msg: The ResponseOutputMessage object for the current output.
        content_part: The ResponseContentPartAddedEvent object for the content part.
        output_item: The ResponseOutputItemAddedEvent object for the output item.
        sequence_number: The current sequence number for the streaming events.

    Returns:
        A tuple containing the updated sequence number and the cumulated response text.
    """
    response_text = response_data.get("response", "")
    cumulated_response = response_text
    chunk_size = 20
    for i in range(0, len(response_text), chunk_size):
        sequence_number += 1
        chunk_text = response_text[i : i + chunk_size]
        text_delta = transform_streaming_response(
            json.dumps({"response": chunk_text}),
            content_index=content_part.content_index,
            output_index=output_item.output_index,
            sequence_number=sequence_number,
            id=output_msg.id,
        )
        await send_off_sse(response, text_delta)
        await asyncio.sleep(0.02)
    return sequence_number, cumulated_response


async def _handle_real_stream_events(
    response: web.StreamResponse,
    upstream_resp: aiohttp.ClientResponse,
    output_msg: ResponseOutputMessage,
    content_part: ResponseContentPartAddedEvent,
    output_item: ResponseOutputItemAddedEvent,
    sequence_number: int,
) -> Tuple[int, str]:
    """
    Handles real streaming events by processing chunks from the upstream response.

    Args:
        response: The web.StreamResponse object for sending SSE events.
        upstream_resp: The upstream aiohttp.ClientResponse object.
        output_msg: The ResponseOutputMessage object for the current output.
        content_part: The ResponseContentPartAddedEvent object for the content part.
        output_item: The ResponseOutputItemAddedEvent object for the output item.
        sequence_number: The current sequence number for the streaming events.

    Returns:
        A tuple containing the updated sequence number and the cumulated response text.
    """
    cumulated_response = ""
    async for chunk in upstream_resp.content.iter_any():
        sequence_number += 1
        chunk_text = chunk.decode()
        cumulated_response += chunk_text
        text_delta = transform_streaming_response(
            json.dumps({"response": chunk_text}),
            content_index=content_part.content_index,
            output_index=output_item.output_index,
            sequence_number=sequence_number,
            id=output_msg.id,
        )
        await send_off_sse(response, text_delta)
    return sequence_number, cumulated_response


async def send_streaming_request(
    session: aiohttp.ClientSession,
    config: ArgoConfig,
    data: Dict[str, Any],
    request: web.Request,
    *,
    pseudo_stream: bool = False,
) -> web.StreamResponse:
    """Sends a streaming request to an API and streams the response to the client.

    Args:
        session: The client session for making the request.
        config: The configuration object containing the API URLs.
        data: The JSON payload of the request.
        request: The web request used for streaming responses.
        convert_to_openai: If True, converts the response to OpenAI format.
        pseudo_stream: If True, simulates streaming even if the upstream does not support it.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "Accept-Encoding": "identity",
    }

    # Set response headers based on the mode
    response_headers = {"Content-Type": "text/event-stream"}
    created_timestamp = int(time.time())
    prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])

    if pseudo_stream:
        data["stream"] = False  # disable streaming in upstream request
        api_url = config.argo_url
    else:
        api_url = config.argo_stream_url

    async with session.post(api_url, headers=headers, json=data) as upstream_resp:
        if upstream_resp.status != 200:
            error_text = await upstream_resp.text()
            return web.json_response(
                {"error": f"Upstream API error: {upstream_resp.status} {error_text}"},
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

        # =======================================
        # Start event flow with ResponseCreatedEvent
        sequence_number = 0
        id = str(uuid.uuid4().hex)  # Generate a unique ID for the response

        onset_response = Response(
            id=f"resp_{id}",
            created_at=created_timestamp,
            model=data["model"],
            output=[],
            status="in_progress",
        )
        created_event = ResponseCreatedEvent(
            response=onset_response,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, created_event.model_dump())

        # =======================================
        # ResponseInProgressEvent, start streaming the response
        sequence_number += 1
        in_progress_event = ResponseInProgressEvent(
            response=onset_response,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, in_progress_event.model_dump())

        # =======================================
        # ResponseOutputItemAddedEvent, add the output item
        sequence_number += 1
        output_msg = ResponseOutputMessage(
            id=f"msg_{id}",
            content=[],
            status="in_progress",
        )
        output_item = ResponseOutputItemAddedEvent(
            item=output_msg,
            output_index=0,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, output_item.model_dump())

        # =======================================
        # ResponseContentPartAddedEvent, add the content part
        sequence_number += 1
        content_index = 0
        content_part = ResponseContentPartAddedEvent(
            content_index=content_index,
            item_id=output_msg.id,
            output_index=output_item.output_index,
            part=ResponseOutputText(text=""),
            sequence_number=sequence_number,
        )
        await send_off_sse(response, content_part.model_dump())

        # =======================================
        # ResponseTextDeltaEvent, stream the response chunk by chunk
        cumulated_response = ""
        if pseudo_stream:
            response_data = await upstream_resp.json()
            sequence_number, cumulated_response = await _handle_pseudo_stream_events(
                response,
                response_data,
                output_msg,
                content_part,
                output_item,
                sequence_number,
            )
        else:
            sequence_number, cumulated_response = await _handle_real_stream_events(
                response,
                upstream_resp,
                output_msg,
                content_part,
                output_item,
                sequence_number,
            )

        # =======================================
        # ResponseTextDoneEvent, signal the end of the text stream
        sequence_number += 1
        text_done = ResponseTextDoneEvent(
            content_index=content_part.content_index,
            item_id=output_msg.id,
            output_index=output_item.output_index,
            sequence_number=sequence_number,
            text=cumulated_response,  # Use the cumulated response tex
        )
        await send_off_sse(response, text_done.model_dump())

        # =======================================
        # ResponseContentPartDoneEvent, signal the end of the content part
        sequence_number += 1
        output_text = ResponseOutputText(text=cumulated_response)
        content_part_done = ResponseContentPartDoneEvent(
            content_index=content_part.content_index,
            item_id=output_msg.id,
            output_index=output_item.output_index,
            part=output_text,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, content_part_done.model_dump())

        # =======================================
        # ResponseOutputItemDoneEvent, signal the end of the output item
        sequence_number += 1
        output_msg.content = [output_text]
        output_msg.status = "completed"

        output_item_done = ResponseOutputItemDoneEvent(
            item=output_msg,
            output_index=output_item.output_index,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, output_item_done.model_dump())

        # =======================================
        # ResponseCompletedEvent, signal the end of the response
        sequence_number += 1
        onset_response.output.append(output_msg)
        onset_response.status = "completed"
        output_tokens = await count_tokens_async(cumulated_response, data["model"])
        onset_response.usage = create_usage(
            prompt_tokens, output_tokens, api_type="response"
        )
        completed_event = ResponseCompletedEvent(
            response=onset_response,
            sequence_number=sequence_number,
        )
        await send_off_sse(response, completed_event.model_dump())

        # =======================================
        # Ensure response is properly closed

        await response.write_eof()

        return response


async def proxy_request(
    request: web.Request,
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

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[response] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        # Prepare the request data (includes message scrutinization and normalization)
        data = prepare_request_data(data, config, model_registry)

        # Apply username passthrough if enabled
        apply_username_passthrough(data, request, config.user)

        # Use the shared HTTP session from app context for connection pooling
        session = request.app["http_session"]

        if stream:
            return await send_streaming_request(
                session,
                config,
                data,
                request,
                pseudo_stream=config.pseudo_stream,
            )
        else:
            return await send_non_streaming_request(
                session,
                config,
                data,
                convert_to_openai=True,
                openai_compat_fn=transform_non_streaming_response_async,
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
