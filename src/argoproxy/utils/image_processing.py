import asyncio
import base64
import mimetypes
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import aiohttp
from loguru import logger

# Supported image formats
SUPPORTED_IMAGE_FORMATS: Set[str] = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}

SUPPORTED_EXTENSIONS: Set[str] = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def truncate_base64_for_logging(data_url: str, max_length: int = 100) -> str:
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


def sanitize_data_for_logging(
    data: Dict[str, Any], max_base64_length: int = 100
) -> Dict[str, Any]:
    """
    Sanitizes request data for logging by truncating base64 content.

    Args:
        data: The request data dictionary.
        max_base64_length: Maximum length to show for base64 content.

    Returns:
        Sanitized data dictionary with truncated base64 content.
    """
    import copy

    # Deep copy to avoid modifying original data
    sanitized = copy.deepcopy(data)

    # Process messages if they exist
    if "messages" in sanitized and isinstance(sanitized["messages"], list):
        for message in sanitized["messages"]:
            if isinstance(message, dict) and "content" in message:
                content = message["content"]

                # Process list-type content (multimodal messages)
                if isinstance(content, list):
                    for content_part in content:
                        if (
                            isinstance(content_part, dict)
                            and content_part.get("type") == "image_url"
                            and "image_url" in content_part
                            and "url" in content_part["image_url"]
                        ):
                            url = content_part["image_url"]["url"]
                            if url.startswith("data:"):
                                content_part["image_url"]["url"] = (
                                    truncate_base64_for_logging(url, max_base64_length)
                                )

    return sanitized


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
            content_type = response.headers.get("content-type", "").lower()
            if not content_type:
                # Fallback to guessing from URL
                mime_type, _ = mimetypes.guess_type(url)
                content_type = (mime_type or "application/octet-stream").lower()

            # Validate it's a supported image format
            if not is_supported_image_format(content_type, url):
                logger.warning(
                    f"Unsupported image format: {url} (content-type: {content_type})"
                )
                logger.info(f"Supported formats: {', '.join(SUPPORTED_IMAGE_FORMATS)}")
                return None

            # Validate image content with magic bytes
            if not validate_image_content(image_data, content_type):
                logger.warning(
                    f"Image content validation failed: {url} (content-type: {content_type})"
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


def is_supported_image_format(content_type: str, url: str = "") -> bool:
    """
    Checks if the content type or URL extension indicates a supported image format.

    Args:
        content_type: The MIME type from HTTP headers.
        url: The URL to check for file extension fallback.

    Returns:
        True if it's a supported image format, False otherwise.
    """
    # Check content type first
    if content_type and content_type.lower() in SUPPORTED_IMAGE_FORMATS:
        return True

    # Fallback to URL extension
    if url:
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        for ext in SUPPORTED_EXTENSIONS:
            if path.endswith(ext):
                return True

    return False


def validate_image_content(image_data: bytes, content_type: str) -> bool:
    """
    Validates image content by checking magic bytes/signatures.

    Args:
        image_data: The raw image data.
        content_type: The MIME type.

    Returns:
        True if the image data matches expected format, False otherwise.
    """
    if not image_data or len(image_data) < 8:
        return False

    # Check magic bytes for different formats
    if content_type in ["image/png"]:
        # PNG signature: 89 50 4E 47 0D 0A 1A 0A
        return image_data[:8] == b"\x89PNG\r\n\x1a\n"

    elif content_type in ["image/jpeg", "image/jpg"]:
        # JPEG signature: FF D8 FF
        return image_data[:3] == b"\xff\xd8\xff"

    elif content_type in ["image/webp"]:
        # WebP signature: RIFF....WEBP
        return (
            len(image_data) >= 12
            and image_data[:4] == b"RIFF"
            and image_data[8:12] == b"WEBP"
        )

    elif content_type in ["image/gif"]:
        # GIF signature: GIF87a or GIF89a
        return image_data[:6] == b"GIF87a" or image_data[:6] == b"GIF89a"

    return True  # Allow other formats to pass through


def collect_image_urls_from_content_part(content_part: Dict[str, Any]) -> List[str]:
    """
    Collects image URLs from a single content part.

    Args:
        content_part: A content part dictionary from a message.

    Returns:
        List of image URLs that need to be downloaded.
    """
    urls = []

    # Only process image_url type content
    if content_part.get("type") != "image_url":
        return urls

    image_url_obj = content_part.get("image_url", {})
    url = image_url_obj.get("url", "")

    # Skip if already a data URL
    if is_data_url(url):
        return urls

    # Only collect HTTP/HTTPS URLs
    if is_http_url(url):
        urls.append(url)
    else:
        logger.warning(f"Unsupported URL scheme for image: {url}")

    return urls


async def apply_downloaded_images_to_content_part(
    content_part: Dict[str, Any], url_to_base64: Dict[str, Optional[str]]
) -> Dict[str, Any]:
    """
    Applies downloaded base64 images to a content part.

    Args:
        content_part: A content part dictionary from a message.
        url_to_base64: Mapping of URLs to their base64 representations.

    Returns:
        The processed content part with image URL converted to base64 if available.
    """
    # Only process image_url type content
    if content_part.get("type") != "image_url":
        return content_part

    image_url_obj = content_part.get("image_url", {})
    url = image_url_obj.get("url", "")

    # Skip if already a data URL
    if is_data_url(url):
        return content_part

    # Apply downloaded base64 if available
    if url in url_to_base64 and url_to_base64[url]:
        base64_url = url_to_base64[url]
        # Update the content part with the base64 data URL
        content_part = content_part.copy()
        content_part["image_url"] = image_url_obj.copy()
        content_part["image_url"]["url"] = base64_url
        logger.info(
            f"Successfully applied downloaded image (size: {len(base64_url)} chars): {truncate_base64_for_logging(base64_url)}"
        )
    else:
        logger.error(f"Failed to convert image URL to base64: {url}")

    return content_part


def collect_image_urls_from_message(message: Dict[str, Any]) -> List[str]:
    """
    Collects all image URLs from a single message.

    Args:
        message: A message dictionary.

    Returns:
        List of image URLs that need to be downloaded.
    """
    urls = []
    content = message.get("content")

    # Only process list-type content (multimodal messages)
    if not isinstance(content, list):
        return urls

    # Collect URLs from each content part
    for content_part in content:
        if isinstance(content_part, dict):
            urls.extend(collect_image_urls_from_content_part(content_part))

    return urls


async def apply_downloaded_images_to_message(
    message: Dict[str, Any], url_to_base64: Dict[str, Optional[str]]
) -> Dict[str, Any]:
    """
    Applies downloaded base64 images to a message.

    Args:
        message: A message dictionary.
        url_to_base64: Mapping of URLs to their base64 representations.

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
            processed_part = await apply_downloaded_images_to_content_part(
                content_part, url_to_base64
            )
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
    Processes chat completion data to convert image URLs to base64 with parallel downloading.

    This function intercepts direct image URLs in chat messages and downloads
    them concurrently, then converts them to base64 data URLs before
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

    # Step 1: Collect all unique image URLs from all messages
    all_urls = set()
    for message in messages:
        if isinstance(message, dict):
            urls = collect_image_urls_from_message(message)
            all_urls.update(urls)

    if not all_urls:
        return data  # No images to process

    # Step 2: Download all images concurrently
    logger.info(f"Starting parallel download of {len(all_urls)} images")
    download_tasks = [download_image_to_base64(session, url) for url in all_urls]

    # Use asyncio.gather for concurrent downloads
    download_results = await asyncio.gather(*download_tasks, return_exceptions=True)

    # Step 3: Create URL to base64 mapping
    url_to_base64 = {}
    for url, result in zip(all_urls, download_results):
        if isinstance(result, Exception):
            logger.error(f"Failed to download image {url}: {result}")
            url_to_base64[url] = None
        else:
            url_to_base64[url] = result
            if result:
                logger.info(f"Successfully downloaded image: {url}")

    # Step 4: Apply downloaded images to all messages
    processed_messages = []
    for message in messages:
        if isinstance(message, dict):
            processed_message = await apply_downloaded_images_to_message(
                message, url_to_base64
            )
            processed_messages.append(processed_message)
        else:
            processed_messages.append(message)

    # Return updated data
    processed_data = data.copy()
    processed_data["messages"] = processed_messages
    return processed_data
