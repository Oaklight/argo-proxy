import asyncio
import base64
import mimetypes
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp
from loguru import logger


async def download_image_to_base64(
    session: aiohttp.ClientSession, url: str, timeout: int = 30
) -> Optional[str]:
    """
    Downloads an image from a URL and converts it to a base64 data URL.

    Args:
        session: The aiohttp ClientSession for making requests.
        url: The URL of the image to download.
        timeout: Request timeout in seconds.

    Returns:
        A base64 data URL string, or None if download fails.
    """
    try:
        # Validate URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            logger.warning(f"Invalid URL format: {url}")
            return None

        # Download the image
        timeout_obj = aiohttp.ClientTimeout(total=timeout)
        async with session.get(url, timeout=timeout_obj) as response:
            if response.status != 200:
                logger.warning(
                    f"Failed to download image from {url}: HTTP {response.status}"
                )
                return None

            # Read image data
            image_data = await response.read()

            # Determine MIME type
            content_type = response.headers.get("content-type")
            if not content_type:
                # Fallback to guessing from URL
                mime_type, _ = mimetypes.guess_type(url)
                content_type = mime_type or "application/octet-stream"

            # Validate it's an image
            if not content_type.startswith("image/"):
                logger.warning(
                    f"URL does not point to an image: {url} (content-type: {content_type})"
                )
                return None

            # Convert to base64
            b64_data = base64.b64encode(image_data).decode("utf-8")
            return f"data:{content_type};base64,{b64_data}"

    except asyncio.TimeoutError:
        logger.warning(f"Timeout downloading image from {url}")
        return None
    except Exception as e:
        logger.warning(f"Error downloading image from {url}: {e}")
        return None


def is_data_url(url: str) -> bool:
    """
    Checks if a URL is already a data URL (base64 encoded).

    Args:
        url: The URL to check.

    Returns:
        True if it's a data URL, False otherwise.
    """
    return url.startswith("data:")


def is_http_url(url: str) -> bool:
    """
    Checks if a URL is an HTTP/HTTPS URL.

    Args:
        url: The URL to check.

    Returns:
        True if it's an HTTP/HTTPS URL, False otherwise.
    """
    return url.startswith(("http://", "https://"))


async def process_image_content_part(
    session: aiohttp.ClientSession, content_part: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Processes a single content part that may contain an image URL.

    Args:
        session: The aiohttp ClientSession for making requests.
        content_part: A content part dictionary from a message.

    Returns:
        The processed content part with image URL converted to base64 if needed.
    """
    # Only process image_url type content
    if content_part.get("type") != "image_url":
        return content_part

    image_url_obj = content_part.get("image_url", {})
    url = image_url_obj.get("url", "")

    # Skip if already a data URL
    if is_data_url(url):
        return content_part

    # Only process HTTP/HTTPS URLs
    if not is_http_url(url):
        logger.warning(f"Unsupported URL scheme for image: {url}")
        return content_part

    # Download and convert to base64
    logger.info(f"Converting image URL to base64: {url}")
    base64_url = await download_image_to_base64(session, url)

    if base64_url:
        # Update the content part with the base64 data URL
        content_part = content_part.copy()
        content_part["image_url"] = image_url_obj.copy()
        content_part["image_url"]["url"] = base64_url
        logger.info(
            f"Successfully converted image URL to base64 (size: {len(base64_url)} chars)"
        )
    else:
        logger.error(f"Failed to convert image URL to base64: {url}")

    return content_part


async def process_message_images(
    session: aiohttp.ClientSession, message: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Processes a single message to convert any image URLs to base64.

    Args:
        session: The aiohttp ClientSession for making requests.
        message: A message dictionary.

    Returns:
        The processed message with image URLs converted to base64.
    """
    content = message.get("content")

    # Only process list-type content (multimodal messages)
    if not isinstance(content, list):
        return message

    # Process each content part
    processed_content = []
    for content_part in content:
        if isinstance(content_part, dict):
            processed_part = await process_image_content_part(session, content_part)
            processed_content.append(processed_part)
        else:
            processed_content.append(content_part)

    # Return updated message
    processed_message = message.copy()
    processed_message["content"] = processed_content
    return processed_message


async def process_chat_images(
    session: aiohttp.ClientSession, data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Processes chat completion data to convert image URLs to base64.

    This function intercepts direct image URLs in chat messages and downloads
    them as temporary files, then converts them to base64 data URLs before
    sending to the upstream service.

    Args:
        session: The aiohttp ClientSession for making requests.
        data: The chat completion request data.

    Returns:
        The processed data with image URLs converted to base64.
    """
    if "messages" not in data:
        return data

    messages = data["messages"]
    if not isinstance(messages, list):
        return data

    # Process each message
    processed_messages = []
    for message in messages:
        if isinstance(message, dict):
            processed_message = await process_message_images(session, message)
            processed_messages.append(processed_message)
        else:
            processed_messages.append(message)

    # Return updated data
    processed_data = data.copy()
    processed_data["messages"] = processed_messages
    return processed_data
