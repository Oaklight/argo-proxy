import os
import sys
from typing import Dict, List, Optional, Union

import tiktoken
from sanic.log import logger

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from argoproxy.constants import ALL_MODELS, TIKTOKEN_ENCODING_PREFIX_MAPPING


def make_bar(message: str = "", bar_length=40) -> str:
    message = " " + message.strip() + " "
    message = message.strip()
    dash_length = (bar_length - len(message)) // 2
    message = "-" * dash_length + message + "-" * dash_length
    return message


def validate_input(json_input: dict, endpoint: str) -> bool:
    """
    Validates the input JSON to ensure it contains the necessary fields.
    """
    if endpoint == "chat/completions":
        required_fields = ["model", "messages"]
    elif endpoint == "completions":
        required_fields = ["model", "prompt"]
    elif endpoint == "embeddings":
        required_fields = ["model", "input"]
    else:
        logger.error(f"Unknown endpoint: {endpoint}")
        return False

    # check required field presence and type
    for field in required_fields:
        if field not in json_input:
            logger.error(f"Missing required field: {field}")
            return False
        if field == "messages" and not isinstance(json_input[field], list):
            logger.error(f"Field {field} must be a list")
            return False
        if field == "prompt" and not isinstance(json_input[field], (str, list)):
            logger.error(f"Field {field} must be a string or list")
            return False
        if field == "input" and not isinstance(json_input[field], (str, list)):
            logger.error(f"Field {field} must be a string or list")
            return False

    return True


def resolve_model_name(
    model_name: str,
    default_model: str,
    avail_models: Optional[Dict[str, str]] = None,
) -> str:
    """
    Resolves a model name to its primary model name using the flattened model mapping.

    Args:
        model_name: The input model name to resolve
        model_mapping: Dictionary mapping primary names to aliases (unused)
        default_model: Default model name to return if no match found

    Returns:
        The resolved primary model name or default_model if no match found
    """
    if not avail_models:
        avail_models = ALL_MODELS

    if model_name in avail_models.values():
        return model_name

    # Check if input exists in the flattened mapping
    if model_name in avail_models:
        return avail_models[model_name]

    return avail_models[default_model]


def get_tiktoken_encoding_model(model: str) -> str:
    """
    Get tiktoken encoding name for a given model.
    If the model starts with 'argo:', use TIKTOKEN_ENCODING_PREFIX_MAPPING to find encoding.
    Otherwise use MODEL_TO_ENCODING mapping.
    """
    if model.startswith("argo:"):
        model = ALL_MODELS[model]

    for prefix, encoding in TIKTOKEN_ENCODING_PREFIX_MAPPING.items():
        if model == prefix:
            return encoding
        if model.startswith(prefix):
            return encoding
    return "cl100k_base"


def count_tokens(text: Union[str, List[str]], model: str) -> int:
    """
    Calculate token count for a given text using tiktoken.
    If the model starts with 'argo:', the part after 'argo:' is used
    to determine the encoding via a MODEL_TO_ENCODING mapping.
    """

    encoding_name = get_tiktoken_encoding_model(model)
    encoding = tiktoken.get_encoding(encoding_name)

    if isinstance(text, list):
        return sum([len(encoding.encode(each)) for each in text])

    return len(encoding.encode(text))


def extract_text_content(content: Union[str, list]) -> str:
    """Extract text content from message content which can be string or list of objects"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
        return " ".join(texts)
    return ""


def calculate_prompt_tokens(data: dict, model: str) -> int:
    """
    Calculate prompt tokens from either messages or prompt field in the request data.
    Supports both string content and list of content objects in messages.

    Args:
        data: The request data dictionary
        model: The model name for token counting

    Returns:
        int: Total token count for the prompt/messages
    """

    if "messages" in data:
        messages_content = [
            extract_text_content(msg["content"])
            for msg in data["messages"]
            if "content" in msg
        ]
        prompt_tokens = count_tokens(messages_content, model)
        return prompt_tokens
    return count_tokens(data.get("prompt", ""), model)
