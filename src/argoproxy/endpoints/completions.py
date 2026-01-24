import json
import uuid
from http import HTTPStatus
from typing import Any, Dict, Optional, Union

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..types import Completion, CompletionChoice
from ..types.completions import FINISH_REASONS
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.tokens import count_tokens, count_tokens_async
from ..utils.usage import create_usage
from .chat import (
    prepare_chat_request_data,
    send_non_streaming_request,
    send_streaming_request,
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
    **kwargs,  # in case of receiving tools, which is not handled in this endpoint
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
        # Calculate token counts (simplified example, actual tokenization may differ)
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
            usage=usage
            if not is_streaming
            else None,  # Usage is not provided in streaming mode
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
    **kwargs,  # in case of receiving tools, which is not handled in this endpoint
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
        # Calculate token counts asynchronously
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
            usage=usage
            if not is_streaming
            else None,  # Usage is not provided in streaming mode
        )

        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred: {err}"}


async def proxy_request(
    request: web.Request,
) -> Union[web.Response, web.StreamResponse]:
    """Proxies incoming requests to the upstream API and processes responses.

    Args:
        request (web.Request): The incoming HTTP request object.
        convert_to_openai (bool, optional): Whether to convert the response to OpenAI-compatible format. Defaults to False.

    Returns:
        web.Response or web.StreamResponse: The HTTP response sent back to the client.

    Raises:
        ValueError: Raised when the request data is invalid or missing.
        aiohttp.ClientError: Raised when there is an HTTP client error.
        Exception: Raised for unexpected runtime errors.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        # Retrieve the incoming JSON data
        data: Dict[str, Any] = await request.json()
        stream: bool = data.get("stream", DEFAULT_STREAM)

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[completion] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        # Prepare the request data (includes message scrutinization and normalization)
        data = prepare_chat_request_data(data, config, model_registry)

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
                convert_to_openai=True,
                openai_compat_fn=transform_completions_compat_async,
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
