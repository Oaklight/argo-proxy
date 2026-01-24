import json
from http import HTTPStatus
from typing import Any, Dict, List, Union

import aiohttp
from aiohttp import web
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..types import CreateEmbeddingResponse, Embedding
from ..utils.misc import make_bar
from ..utils.tokens import count_tokens
from ..utils.usage import create_usage

DEFAULT_MODEL = "argo:text-embedding-3-small"


def make_it_openai_embeddings_compat(
    custom_response: Union[str, Dict[str, Any]],
    model_name: str,
    prompt: Union[str, List[str]],
) -> Union[Dict[str, Any], str]:
    """Converts a custom API response to an OpenAI-compatible response.

    Args:
        custom_response (Union[str, Dict[str, Any]]): JSON response from the custom API.
        model_name (str): The name of the model used for generating embeddings.
        prompt (Union[str, List[str]]): The input prompt or list of prompts used in the request.

    Returns:
        Union[Dict[str, Any], str]: An OpenAI-compatible response or error message.
    """
    try:
        # Parse the custom response
        if isinstance(custom_response, str):
            custom_response_dict = json.loads(custom_response)
        else:
            custom_response_dict = custom_response

        # Calculate token counts
        if isinstance(prompt, str):
            prompt_tokens = count_tokens(prompt, model_name)
        else:
            prompt_tokens = sum(count_tokens(text, model_name) for text in prompt)

        # Construct the OpenAI-compatible response
        data = [
            Embedding(embedding=embedding, index=i)
            for i, embedding in enumerate(custom_response_dict["embedding"])
        ]
        openai_response = CreateEmbeddingResponse(
            data=data,
            model=model_name,
            usage=create_usage(prompt_tokens, 0, api_type="embedding"),
        )
        return openai_response.model_dump()

    except json.JSONDecodeError as err:
        return {"error": f"Error decoding JSON: {err}"}
    except Exception as err:
        return {"error": f"An error occurred: {err}"}


def prepare_request_data(
    data: Dict[str, Any],
    config: ArgoConfig,
    model_registry: ModelRegistry,
) -> Dict[str, Any]:
    """
    Modifies and prepares the incoming request data by adding user information
    and remapping the model according to configurations.

    Args:
        data: The incoming request data.
        config: The ArgoConfig object containing configuration settings.
        model_registry: The ModelRegistry object containing model mappings.

    Returns:
        The modified and prepared request data.
    """

    # Automatically replace or insert the user
    data["user"] = config.user
    # Remap the model using EMBED_MODELS
    if "model" not in data:
        data["model"] = DEFAULT_MODEL  # Default model if not provided
    data["model"] = model_registry.resolve_model_name(data["model"], model_type="embed")

    # Transform the incoming payload to match the destination API format
    if "prompt" not in data:  # argo-API uses prompt, openAI-API uses input
        if "input" not in data:
            raise ValueError(
                "Invalid input. Expected 'input' (openAI) or 'prompt' (argo) field."
            )
        data["prompt"] = (
            [data["input"]] if not isinstance(data["input"], list) else data["input"]
        )
        del data["input"]

    return data


async def proxy_request(
    request: web.Request, convert_to_openai: bool = False
) -> web.Response:
    """Proxies a request to the target embedding service, optionally converting responses.

    Args:
        request (web.Request): The incoming HTTP request.
        convert_to_openai (bool): Whether to convert the response to OpenAI-compatible format.

    Returns:
        web.Response: The HTTP response sent back to the client.
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        # Retrieve the incoming JSON data
        data: Dict[str, Any] = await request.json()
        if not data:
            raise ValueError("Invalid input. Expected JSON data.")
        if config.verbose:
            logger.info(make_bar("[embed] input"))
            logger.info(json.dumps(data, indent=4))
            logger.info(make_bar())

        data = prepare_request_data(data, config, model_registry)

        headers: Dict[str, str] = {"Content-Type": "application/json"}

        # Use the shared HTTP session from app context for connection pooling
        session = request.app["http_session"]

        async with session.post(
            config.argo_embedding_url, headers=headers, json=data
        ) as resp:
            response_data: Dict[str, Any] = await resp.json()
            resp.raise_for_status()

            if config.verbose:
                logger.info(make_bar("[embed] fwd. response"))
                # Create a new dict with copied lists to avoid modifying the original
                log_data = {
                    "embedding": [
                        emb[:3]
                        + ["......", f"{len(emb) - 3} elements omitted", "......"]
                        for emb in response_data["embedding"]
                    ]
                }
                logger.info(json.dumps(log_data, indent=4))
                logger.info(make_bar())

            if convert_to_openai:
                openai_response = make_it_openai_embeddings_compat(
                    json.dumps(response_data),
                    data["model"],
                    data["prompt"],
                )
                return web.json_response(
                    openai_response,
                    status=resp.status,
                    content_type="application/json",
                )
            else:
                return web.json_response(
                    response_data,
                    status=resp.status,
                    content_type="application/json",
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
