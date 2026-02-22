import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Optional, Union

import aiohttp
from aiohttp import web


async def pseudo_chunk_generator(
    complete_text: Optional[str],
    chunk_size: int = 30,
    sleep_time: float = 0.01,
) -> AsyncGenerator[str, None]:
    """Generate text chunks asynchronously to simulate streaming responses.

    Args:
        complete_text: The complete text to be chunked.
        chunk_size: Size of each chunk in characters. Defaults to 20.
        sleep_time: Time to sleep between chunks in seconds. Defaults to 0.02.

    Yields:
        str: Text chunks of the specified size.

    Example:
        >>> async for chunk in pseudo_chunk_generator("Hello World", 5):
        ...     print(chunk)
        "Hello"
        " Worl"
        "d"
    """
    if complete_text is None:
        return

    for i in range(0, len(complete_text), chunk_size):
        chunk = complete_text[i : i + chunk_size]
        await asyncio.sleep(sleep_time)
        yield chunk


async def send_off_sse(
    response: web.StreamResponse, data: Union[Dict[str, Any], bytes]
) -> None:
    """
    Sends a chunk of data as a Server-Sent Events (SSE) event.

    Args:
        response (web.StreamResponse): The response object used to send the SSE event.
        data (Union[Dict[str, Any], bytes]): The chunk of data to be sent as an SSE event.
            It can be either a dictionary (which will be converted to a JSON string and then to bytes)
            or preformatted bytes.

    Returns:
        None
    """
    # Send the chunk as an SSE event
    if isinstance(data, bytes):
        sse_chunk = data
    else:
        # Convert the chunk to OpenAI-compatible JSON and then to bytes
        sse_chunk = f"data: {json.dumps(data)}\n\n".encode()
    await response.write(sse_chunk)


async def validate_api_async(
    url: str,
    user: str,
    payload: dict,
    timeout: int = 2,
    attempts: int = 3,
    resolver_overrides: Optional[dict[str, str]] = None,
) -> bool:
    """Asynchronously validates API connectivity with retries using aiohttp.

    Args:
        url: The API URL to validate.
        user: The username for payload.
        payload: Request payload.
        timeout: Request timeout seconds.
        attempts: Total attempts (including the first).
        resolver_overrides: Optional dict mapping "host:port" to IP address
            for custom DNS resolution.

    Returns:
        True if validation succeeds.

    Raises:
        ValueError: If all attempts fail.
    """
    from ..performance import StaticOverrideResolver

    payload_copy = payload.copy()
    payload_copy["user"] = user

    connector = None
    if resolver_overrides:
        resolver = StaticOverrideResolver(resolver_overrides)
        connector = aiohttp.TCPConnector(resolver=resolver)

    client_timeout = aiohttp.ClientTimeout(total=timeout)

    last_err: Optional[Exception] = None
    for attempt in range(attempts + 1):  # tries = 1 + attempts
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=client_timeout,
            ) as session:
                async with session.post(
                    url,
                    json=payload_copy,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"API returned status code {response.status}")
                    return True
        except Exception as e:
            last_err = e
            if attempt < attempts:
                await asyncio.sleep(0.5)
            # Recreate connector for next attempt if needed
            if resolver_overrides and attempt < attempts:
                resolver = StaticOverrideResolver(resolver_overrides)
                connector = aiohttp.TCPConnector(resolver=resolver)
            else:
                connector = None

    # If we reach here, all attempts failed
    if last_err is not None:
        raise last_err
    raise ValueError("API validation failed after all attempts")
