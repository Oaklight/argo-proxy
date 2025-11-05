import asyncio
import base64
import io
import mimetypes
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import aiohttp
from loguru import logger

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not available. Image downsampling will be disabled.")

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

            # Convert to base64 (downsampling will be done later based on total payload size)
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


def downsample_images_for_payload(
    images: List[tuple[bytes, str]], max_payload_size: int = 20971520
) -> List[tuple[bytes, str]]:
    """
    Reduce image quality to fit within the total payload size limit.

    Args:
        images: List of (image_data, content_type) tuples.
        max_payload_size: Maximum allowed total payload size in bytes (default 20MB).

    Returns:
        List of (processed_image_data, final_content_type) tuples that fits within the payload limit.
    """
    if not PIL_AVAILABLE:
        logger.warning("PIL not available, skipping image downsampling")
        return [img_data for img_data, _ in images]

    total_size = sum(len(img_data) for img_data, _ in images)
    if total_size <= max_payload_size:
        return [(img_data, content_type) for img_data, content_type in images]

    logger.info(
        f"Total payload size {total_size} bytes exceeds limit {max_payload_size} bytes, reducing image quality"
    )

    # Calculate target compression ratio
    target_ratio = max_payload_size / total_size

    processed_images = []
    for img_data, content_type in images:
        try:
            # Open image with PIL
            image = Image.open(io.BytesIO(img_data))
            original_size = len(img_data)
            final_content_type = content_type  # Track the final content type

            # Determine output format and progressive quality reduction
            if content_type in ["image/jpeg", "image/jpg"]:
                # For JPEG, reduce quality
                quality = max(int(85 * target_ratio), 20)  # Min quality 20
                output_format = "JPEG"
                save_kwargs = {"quality": quality, "optimize": True}
                final_content_type = "image/jpeg"

            elif content_type == "image/png":
                # For PNG, convert to JPEG with reduced quality for better compression
                if image.mode in ("RGBA", "LA", "P"):
                    # Handle transparency by creating white background
                    background = Image.new("RGB", image.size, (255, 255, 255))
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    background.paste(
                        image,
                        mask=image.split()[-1]
                        if image.mode in ("RGBA", "LA")
                        else None,
                    )
                    image = background
                else:
                    image = image.convert("RGB")

                quality = max(
                    int(75 * target_ratio), 15
                )  # Lower quality for PNG->JPEG conversion
                output_format = "JPEG"
                save_kwargs = {"quality": quality, "optimize": True}
                final_content_type = "image/jpeg"  # PNG converted to JPEG

            elif content_type == "image/webp":
                # For WebP, reduce quality
                quality = max(int(80 * target_ratio), 15)
                output_format = "WEBP"
                save_kwargs = {"quality": quality, "method": 6, "optimize": True}
                final_content_type = "image/webp"

            elif content_type == "image/gif":
                # For GIF, convert to JPEG with reduced quality
                if image.mode != "RGB":
                    image = image.convert("RGB")
                quality = max(int(70 * target_ratio), 15)
                output_format = "JPEG"
                save_kwargs = {"quality": quality, "optimize": True}
                final_content_type = "image/jpeg"  # GIF converted to JPEG

            else:
                # Default: convert to JPEG with reduced quality
                if image.mode != "RGB":
                    image = image.convert("RGB")
                quality = max(int(75 * target_ratio), 15)
                output_format = "JPEG"
                save_kwargs = {"quality": quality, "optimize": True}
                final_content_type = "image/jpeg"  # Default conversion to JPEG

            # Save to bytes
            output_buffer = io.BytesIO()
            image.save(output_buffer, format=output_format, **save_kwargs)
            downsampled_data = output_buffer.getvalue()

            logger.info(
                f"Image quality reduced: {original_size} bytes -> {len(downsampled_data)} bytes "
                f"(quality: {save_kwargs.get('quality', 'optimized')}, format: {output_format}, "
                f"content-type: {content_type} -> {final_content_type})"
            )

            processed_images.append((downsampled_data, final_content_type))

        except Exception as e:
            logger.warning(f"Failed to reduce image quality: {e}, using original")
            processed_images.append((img_data, content_type))

    return processed_images


def downsample_image_if_needed(
    image_data: bytes, content_type: str, max_size: int = 5242880
) -> bytes:
    """
    Downsample image if it exceeds the maximum size limit.

    DEPRECATED: Use downsample_images_for_payload for payload-based limiting.

    Args:
        image_data: The raw image data.
        content_type: The MIME type.
        max_size: Maximum allowed size in bytes (default 5MB).

    Returns:
        The original or downsampled image data.
    """
    if not PIL_AVAILABLE:
        logger.warning("PIL not available, skipping image downsampling")
        return image_data

    if len(image_data) <= max_size:
        return image_data

    try:
        # Open image with PIL
        image = Image.open(io.BytesIO(image_data))
        original_size = len(image_data)

        # Calculate reduction factor based on file size
        # Rough estimation: reduce dimensions by sqrt of size ratio
        size_ratio = max_size / len(image_data)
        dimension_ratio = size_ratio**0.5

        # Calculate new dimensions
        new_width = int(image.width * dimension_ratio)
        new_height = int(image.height * dimension_ratio)

        # Ensure minimum dimensions
        new_width = max(new_width, 64)
        new_height = max(new_height, 64)

        # Resize image
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # Determine output format and quality
        output_format = "JPEG"
        save_kwargs = {"quality": 85, "optimize": True}

        if content_type == "image/png":
            output_format = "PNG"
            save_kwargs = {"optimize": True}
        elif content_type == "image/webp":
            output_format = "WEBP"
            save_kwargs = {"quality": 85, "method": 6}

        # Save to bytes
        output_buffer = io.BytesIO()
        resized_image.save(output_buffer, format=output_format, **save_kwargs)
        downsampled_data = output_buffer.getvalue()

        logger.info(
            f"Image downsampled: {original_size} bytes -> {len(downsampled_data)} bytes "
            f"({image.width}x{image.height} -> {new_width}x{new_height})"
        )

        return downsampled_data

    except Exception as e:
        logger.warning(f"Failed to downsample image: {e}, using original")
        return image_data


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
    session: aiohttp.ClientSession, data: Dict[str, Any], config: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Processes chat completion data to convert image URLs to base64 with parallel downloading.

    This function intercepts direct image URLs in chat messages and downloads
    them concurrently, then converts them to base64 data URLs before
    sending to the upstream service.

    Args:
        session: The aiohttp ClientSession for making requests.
        data: The chat completion request data.
        config: Optional configuration object with image processing settings.

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

    # Get configuration values
    timeout = getattr(config, "image_timeout", 30) if config else 30
    enable_payload_control = (
        getattr(config, "enable_payload_control", True) if config else True
    )
    max_payload_mb = getattr(config, "max_payload_size", 20) if config else 20
    max_payload_size = max_payload_mb * 1024 * 1024  # Convert MB to bytes

    # Step 2: Download all images concurrently
    logger.info(f"Starting parallel download of {len(all_urls)} images")
    download_tasks = [
        download_image_to_base64(session, url, timeout=timeout) for url in all_urls
    ]

    # Use asyncio.gather for concurrent downloads
    download_results = await asyncio.gather(*download_tasks, return_exceptions=True)

    # Step 3: Process downloaded images and check payload size
    successful_downloads = []
    url_to_base64 = {}

    for url, result in zip(all_urls, download_results):
        if isinstance(result, Exception):
            logger.error(f"Failed to download image {url}: {result}")
            url_to_base64[url] = None
        else:
            if result:
                # Extract image data from base64 for size checking
                if ";base64," in result:
                    header, b64_data = result.split(";base64,", 1)
                    content_type = header.replace("data:", "")
                    img_data = base64.b64decode(b64_data)
                    successful_downloads.append((img_data, content_type, url, result))
                    logger.info(f"Successfully downloaded image: {url}")
                else:
                    url_to_base64[url] = None
            else:
                url_to_base64[url] = None

    # Step 4: Check total payload size and downsample if needed
    if successful_downloads:
        total_size = sum(len(img_data) for img_data, _, _, _ in successful_downloads)
        logger.info(
            f"Total image payload size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)"
        )

        if enable_payload_control and total_size > max_payload_size:
            logger.warning(
                f"Payload size [{total_size / 1024 / 1024:.2f}] MB exceeds limit [{max_payload_mb}] MB, reducing image quality"
            )
            # Prepare data for downsampling
            images_for_processing = [
                (img_data, content_type)
                for img_data, content_type, _, _ in successful_downloads
            ]
            processed_images_with_types = downsample_images_for_payload(
                images_for_processing, max_payload_size
            )

            # Update the base64 data with processed images
            for i, (_, _, url, _) in enumerate(successful_downloads):
                if i < len(processed_images_with_types):
                    processed_img_data, final_content_type = (
                        processed_images_with_types[i]
                    )
                    processed_b64 = base64.b64encode(processed_img_data).decode("utf-8")
                    url_to_base64[url] = (
                        f"data:{final_content_type};base64,{processed_b64}"
                    )
                else:
                    url_to_base64[url] = None
        else:
            # Use original images (either payload control disabled or size within limit)
            if not enable_payload_control and total_size > max_payload_size:
                logger.info(
                    f"Payload control disabled - passing through {total_size / 1024 / 1024:.2f} MB payload (exceeds {max_payload_mb} MB limit)"
                )
            for _, _, url, original_result in successful_downloads:
                url_to_base64[url] = original_result

    # Step 5: Apply downloaded images to all messages
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
