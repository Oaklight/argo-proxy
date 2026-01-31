import os
import random
import socket
from typing import Optional

from aiohttp import web

from .logging import log_error


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
        log_error(f"Unknown endpoint: {endpoint}", context="misc.validate_input")
        return False

    # check required field presence and type
    for field in required_fields:
        if field not in json_input:
            log_error(f"Missing required field: {field}", context="misc.validate_input")
            return False
        if field == "messages" and not isinstance(json_input[field], list):
            log_error(f"Field {field} must be a list", context="misc.validate_input")
            return False
        if field == "prompt" and not isinstance(json_input[field], (str, list)):
            log_error(
                f"Field {field} must be a string or list", context="misc.validate_input"
            )
            return False
        if field == "input" and not isinstance(json_input[field], (str, list)):
            log_error(
                f"Field {field} must be a string or list", context="misc.validate_input"
            )
            return False

    return True


def get_random_port(low: int, high: int) -> int:
    """
    Generates a random port within the specified range and ensures it is available.

    Args:
        low (int): The lower bound of the port range.
        high (int): The upper bound of the port range.

    Returns:
        int: A random available port within the range.

    Raises:
        ValueError: If no available port can be found within the range.
    """
    if low < 1024 or high > 65535 or low >= high:
        raise ValueError("Invalid port range. Ports should be between 1024 and 65535.")

    attempts = high - low  # Maximum attempts to check ports in the range
    for _ in range(attempts):
        port = random.randint(low, high)
        if is_port_available(port):
            return port

    raise ValueError(f"No available port found in the range {low}-{high}.")


def is_port_available(port: int, timeout: float = 0.1) -> bool:
    """
    Checks if a given port is available (not already in use).

    Args:
        port (int): The port number to check.
        timeout (float): Timeout in seconds for the connection attempt.

    Returns:
        bool: True if the port is available, False otherwise.
    """
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.settimeout(timeout)
                s.bind(("127.0.0.1", port))
                s.close()
                return True
        except (OSError, socket.timeout):
            continue
    return False


def str_to_bool(value: str) -> bool:
    """Convert string to boolean"""
    return value.lower() in {"true", "1", "t", "yes", "on"}


def extract_api_key_from_request(request: web.Request) -> Optional[str]:
    """
    Extract API key from request headers for username passthrough functionality.

    Args:
        request: The web request object containing headers

    Returns:
        The extracted API key if found, None otherwise

    Note:
        Supports multiple header formats:
        - Authorization: Bearer <token>
        - Authorization: <token>
        - X-API-Key: <token>
        - API-Key: <token>
    """
    # Try to get API key from various common header names
    for header_name in ["authorization", "x-api-key", "api-key"]:
        header_value = request.headers.get(header_name, "")
        if header_value:
            # Handle "Bearer <token>" format
            if header_value.lower().startswith("bearer "):
                api_key = header_value[7:].strip()
            else:
                api_key = header_value.strip()

            # Return the first non-empty API key found
            if api_key:
                return api_key

    return None


def should_use_username_passthrough() -> bool:
    """
    Check if username passthrough mode is enabled via environment variable.

    Returns:
        True if username passthrough is enabled, False otherwise
    """
    return os.getenv("USERNAME_PASSTHROUGH", "False").lower() == "true"


def apply_username_passthrough(
    data: dict, request: web.Request, fallback_user: str
) -> str:
    """
    Apply username passthrough logic to determine the user field value.

    Args:
        data: The request data dictionary (will be modified in place)
        request: The web request object
        fallback_user: The fallback user value if no API key is found

    Returns:
        The user value that was applied
    """
    if should_use_username_passthrough():
        api_key = extract_api_key_from_request(request)
        if api_key:
            data["user"] = api_key
            return api_key

    # Fallback to the provided user
    data["user"] = fallback_user
    return fallback_user
