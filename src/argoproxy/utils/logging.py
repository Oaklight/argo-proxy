"""
Logging utilities for argo-proxy.

This module provides utilities for logging request/response data in a clean,
configurable manner. It helps reduce log verbosity while maintaining useful
debugging information.
"""

import copy
import json
from typing import Any, Dict, List

from loguru import logger

from .misc import make_bar


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to max_length with suffix.

    Args:
        s: The string to truncate.
        max_length: Maximum length before truncation.
        suffix: Suffix to append when truncated.

    Returns:
        Truncated string with remaining character count.
    """
    if len(s) <= max_length:
        return s
    remaining = len(s) - max_length
    return f"{s[:max_length]}{suffix}[{remaining} more chars]"


def truncate_base64(data_url: str, max_length: int = 100) -> str:
    """
    Truncates base64 data URLs for cleaner logging.

    Args:
        data_url: The data URL containing base64 content.
        max_length: Maximum length to show before truncation.

    Returns:
        Truncated string with placeholder for readability.
    """
    if not data_url.startswith("data:"):
        return data_url

    # Split into header and data parts
    if ";base64," in data_url:
        header, base64_data = data_url.split(";base64,", 1)
        if len(base64_data) > max_length:
            truncated = base64_data[:max_length]
            remaining_chars = len(base64_data) - max_length
            return f"{header};base64,{truncated}...[{remaining_chars} more chars]"

    return data_url


def sanitize_request_data(
    data: Dict[str, Any],
    *,
    max_base64_length: int = 100,
    max_content_length: int = 500,
    max_tool_desc_length: int = 100,
    truncate_tools: bool = True,
    truncate_messages: bool = True,
) -> Dict[str, Any]:
    """
    Sanitizes request data for logging by truncating long content.

    Args:
        data: The request data dictionary.
        max_base64_length: Maximum length to show for base64 content.
        max_content_length: Maximum length to show for message content.
        max_tool_desc_length: Maximum length to show for tool descriptions.
        truncate_tools: Whether to truncate tool definitions.
        truncate_messages: Whether to truncate message content.

    Returns:
        Sanitized data dictionary with truncated content for cleaner logging.
    """
    # Deep copy to avoid modifying original data
    sanitized = copy.deepcopy(data)

    # Process messages if they exist
    if (
        truncate_messages
        and "messages" in sanitized
        and isinstance(sanitized["messages"], list)
    ):
        for message in sanitized["messages"]:
            if isinstance(message, dict) and "content" in message:
                content = message["content"]

                # Process string content (truncate long system prompts, etc.)
                if isinstance(content, str) and len(content) > max_content_length:
                    message["content"] = truncate_string(content, max_content_length)

                # Process list-type content (multimodal messages)
                elif isinstance(content, list):
                    for content_part in content:
                        if isinstance(content_part, dict):
                            # Handle image URLs
                            if (
                                content_part.get("type") == "image_url"
                                and "image_url" in content_part
                                and "url" in content_part["image_url"]
                            ):
                                url = content_part["image_url"]["url"]
                                if url.startswith("data:"):
                                    content_part["image_url"]["url"] = truncate_base64(
                                        url, max_base64_length
                                    )
                            # Handle text content
                            elif (
                                content_part.get("type") == "text"
                                and "text" in content_part
                                and isinstance(content_part["text"], str)
                                and len(content_part["text"]) > max_content_length
                            ):
                                content_part["text"] = truncate_string(
                                    content_part["text"], max_content_length
                                )

    # Process tools if they exist and truncation is enabled
    if truncate_tools and "tools" in sanitized and isinstance(sanitized["tools"], list):
        tool_count = len(sanitized["tools"])
        # Replace tools with a summary
        sanitized["tools"] = f"[{tool_count} tools defined - truncated for logging]"

    return sanitized


def create_request_summary(data: Dict[str, Any]) -> str:
    """
    Creates a concise one-line summary of a request for logging.

    Args:
        data: The request data dictionary.

    Returns:
        A concise summary string.
    """
    summary_parts = []

    # Model
    if "model" in data:
        summary_parts.append(f"model={data['model']}")

    # Message count
    if "messages" in data and isinstance(data["messages"], list):
        msg_count = len(data["messages"])
        summary_parts.append(f"messages={msg_count}")

    # Tools
    if "tools" in data and isinstance(data["tools"], list):
        tool_count = len(data["tools"])
        summary_parts.append(f"tools={tool_count}")

    # Stream
    if "stream" in data:
        summary_parts.append(f"stream={data['stream']}")

    # Max tokens
    if "max_tokens" in data:
        summary_parts.append(f"max_tokens={data['max_tokens']}")

    # User
    if "user" in data:
        summary_parts.append(f"user={data['user']}")

    return ", ".join(summary_parts)


def log_request(
    data: Dict[str, Any],
    label: str = "REQUEST",
    *,
    show_summary: bool = True,
    show_full: bool = False,
    sanitize: bool = True,
    max_content_length: int = 500,
    truncate_tools: bool = True,
) -> None:
    """
    Log a request with configurable verbosity.

    Args:
        data: The request data dictionary.
        label: Label for the log entry (e.g., "ORIGINAL", "CONVERTED").
        show_summary: Whether to show a one-line summary.
        show_full: Whether to show the full request data.
        sanitize: Whether to sanitize the data before logging.
        max_content_length: Maximum content length when sanitizing.
        truncate_tools: Whether to truncate tools when sanitizing.
    """
    if show_summary:
        summary = create_request_summary(data)
        logger.info(f"[{label}] {summary}")

    if show_full:
        if sanitize:
            log_data = sanitize_request_data(
                data,
                max_content_length=max_content_length,
                truncate_tools=truncate_tools,
            )
        else:
            log_data = data

        logger.debug(make_bar(f"[{label}]"))
        logger.debug(json.dumps(log_data, indent=4, ensure_ascii=False))
        logger.debug(make_bar())


def log_original_request(
    data: Dict[str, Any],
    *,
    verbose: bool = False,
    max_content_length: int = 500,
) -> None:
    """
    Log the original request before any transformation.

    Args:
        data: The original request data.
        verbose: Whether to show full request details.
        max_content_length: Maximum content length when sanitizing.
    """
    log_request(
        data,
        label="ORIGINAL",
        show_summary=True,
        show_full=verbose,
        max_content_length=max_content_length,
    )


def log_converted_request(
    data: Dict[str, Any],
    *,
    verbose: bool = False,
    max_content_length: int = 500,
) -> None:
    """
    Log the converted request after transformation.

    Args:
        data: The converted request data.
        verbose: Whether to show full request details.
        max_content_length: Maximum content length when sanitizing.
    """
    log_request(
        data,
        label="CONVERTED",
        show_summary=True,
        show_full=verbose,
        max_content_length=max_content_length,
    )


def log_request_diff(
    original: Dict[str, Any],
    converted: Dict[str, Any],
    *,
    verbose: bool = False,
) -> None:
    """
    Log the difference between original and converted requests.

    This is useful for debugging to see what transformations were applied.

    Args:
        original: The original request data.
        converted: The converted request data.
        verbose: Whether to show detailed diff.
    """
    # Create summaries
    original_summary = create_request_summary(original)
    converted_summary = create_request_summary(converted)

    # Log summaries
    logger.info(f"[ORIGINAL]  {original_summary}")
    logger.info(f"[CONVERTED] {converted_summary}")

    # Highlight key differences
    diffs: List[str] = []

    # Model change
    orig_model = original.get("model", "")
    conv_model = converted.get("model", "")
    if orig_model != conv_model:
        diffs.append(f"model: {orig_model} -> {conv_model}")

    # Tools change
    orig_tools = len(original.get("tools", []))
    conv_tools = len(converted.get("tools", []))
    if orig_tools != conv_tools:
        diffs.append(f"tools: {orig_tools} -> {conv_tools}")

    # User added
    if "user" not in original and "user" in converted:
        diffs.append(f"user: added ({converted['user']})")

    if diffs:
        logger.info(f"[CHANGES] {', '.join(diffs)}")


def log_upstream_error(
    status_code: int,
    error_text: str,
    *,
    endpoint: str = "unknown",
    is_streaming: bool = False,
) -> None:
    """
    Log an upstream API error in a consistent format.

    Args:
        status_code: The HTTP status code from the upstream response.
        error_text: The error text/body from the upstream response.
        endpoint: The endpoint name (e.g., "chat", "embed", "response", "native_openai").
        is_streaming: Whether this was a streaming request.
    """
    request_type = "streaming" if is_streaming else "non-streaming"
    logger.error(
        f"[UPSTREAM ERROR] endpoint={endpoint}, type={request_type}, "
        f"status={status_code}, error={error_text}"
    )
