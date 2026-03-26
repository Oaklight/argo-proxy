import asyncio
import json
from typing import Any, Union
from collections.abc import AsyncGenerator

import aiohttp
from aiohttp import web


async def pseudo_chunk_generator(
    complete_text: str | None,
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
    response: web.StreamResponse, data: Union[dict[str, Any], bytes]
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
    resolver_overrides: dict[str, str] | None = None,
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

    last_err: Exception | None = None
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


async def _fetch_first_model(
    models_url: str,
    timeout: int = 5,
    resolver_overrides: dict[str, str] | None = None,
) -> str | None:
    """Fetch the first available model ID from an OpenAI-compatible ``/models`` endpoint.

    Returns:
        A model ID string, or None if the request fails.
    """
    from ..performance import StaticOverrideResolver

    connector = None
    if resolver_overrides:
        resolver = StaticOverrideResolver(resolver_overrides)
        connector = aiohttp.TCPConnector(resolver=resolver)

    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as session:
            async with session.get(models_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                models = data.get("data", [])
                if models:
                    m = models[0]
                    return m.get("internal_id") or m.get("id")
    except Exception:
        pass
    return None


async def validate_user_async(
    chat_url: str,
    user: str,
    timeout: int = 10,
    attempts: int = 2,
    resolver_overrides: dict[str, str] | None = None,
) -> bool:
    """Validate that *user* is registered in ARGO by making a lightweight
    chat request and checking the response for the authentication warning.

    The model name is auto-detected from the ``/models`` endpoint so that
    the function works against both native ARGO upstreams and transparent
    dev-mode proxies (which require internal model IDs).

    Args:
        chat_url: The native OpenAI chat completions endpoint URL.
        user: The username to validate.
        timeout: Request timeout seconds.
        attempts: Total attempts (including the first).
        resolver_overrides: Optional DNS override mapping.

    Returns:
        True if the user is valid (no auth warning), False otherwise.

    Raises:
        ValueError: If connectivity fails after all attempts.
    """
    from ..performance import StaticOverrideResolver
    from .misc import contains_argo_auth_warning, extract_text_from_response

    # Auto-detect a valid model name from the upstream
    models_url = chat_url.rsplit("/chat/completions", 1)[0] + "/models"
    model = await _fetch_first_model(
        models_url, timeout=timeout, resolver_overrides=resolver_overrides
    )
    if not model:
        model = "gpt-4o-latest"  # fallback

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "say ok"}],
        "user": user,
        "max_tokens": 5,
    }

    connector = None
    if resolver_overrides:
        resolver = StaticOverrideResolver(resolver_overrides)
        connector = aiohttp.TCPConnector(resolver=resolver)

    client_timeout = aiohttp.ClientTimeout(total=timeout)

    last_err: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=client_timeout,
            ) as session:
                async with session.post(
                    chat_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {user}",
                    },
                ) as response:
                    if response.status != 200:
                        raise ValueError(f"API returned status code {response.status}")
                    data = await response.json()
                    text = extract_text_from_response(data, "openai")
                    return not contains_argo_auth_warning(text)
        except Exception as e:
            last_err = e
            if attempt < attempts:
                await asyncio.sleep(0.5)
            if resolver_overrides and attempt < attempts:
                resolver = StaticOverrideResolver(resolver_overrides)
                connector = aiohttp.TCPConnector(resolver=resolver)
            else:
                connector = None

    if last_err is not None:
        raise last_err
    raise ValueError("User validation failed after all attempts")


async def validate_url_get_async(
    url: str,
    timeout: int = 5,
    attempts: int = 2,
    resolver_overrides: dict[str, str] | None = None,
) -> bool:
    """Validate URL connectivity with a simple GET request.

    Useful for endpoints like ``/v1/models`` that don't require a POST body.

    Args:
        url: The URL to validate.
        timeout: Request timeout seconds.
        attempts: Total attempts (including the first).
        resolver_overrides: Optional DNS override mapping.

    Returns:
        True if validation succeeds.

    Raises:
        ValueError: If all attempts fail.
    """
    from ..performance import StaticOverrideResolver

    connector = None
    if resolver_overrides:
        resolver = StaticOverrideResolver(resolver_overrides)
        connector = aiohttp.TCPConnector(resolver=resolver)

    client_timeout = aiohttp.ClientTimeout(total=timeout)

    last_err: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=client_timeout,
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise ValueError(f"GET {url} returned status {response.status}")
                    return True
        except Exception as e:
            last_err = e
            if attempt < attempts:
                await asyncio.sleep(0.5)
            if resolver_overrides and attempt < attempts:
                resolver = StaticOverrideResolver(resolver_overrides)
                connector = aiohttp.TCPConnector(resolver=resolver)
            else:
                connector = None

    if last_err is not None:
        raise last_err
    raise ValueError("URL validation failed after all attempts")
