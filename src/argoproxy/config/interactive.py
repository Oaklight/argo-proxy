"""Interactive user input helpers and config creation wizard."""

import threading
from typing import Any, Union

from ..utils.logging import log_error, log_info, log_warning
from ..utils.misc import get_random_port, is_port_available
from .model import ArgoConfig


def _get_yes_no_input(
    prompt: str,
    default_choice: str = "y",
    accept_value: dict[str, type] | None = None,
) -> Union[bool, Any]:
    """General helper to get yes/no or specific value input from user.

    Args:
        prompt: The prompt to display.
        default_choice: Default choice if user just presses enter.
        accept_value: If provided, allows user to input a specific value.
            Should be a dict with single key-value pair like {"port": int}.

    Returns:
        True/False for yes/no, or the accepted value if provided.
    """
    while True:
        choice = input(prompt).strip().lower()

        # Handle empty input
        if not choice:
            choice = default_choice

        # Handle yes/no
        if not accept_value:
            if choice in ("y", "yes"):
                return True
            if choice in ("n", "no"):
                return False
            log_info("Invalid input, please enter Y/n", context="config")
            continue

        # Handle value input
        if accept_value:
            if len(accept_value) != 1:
                raise ValueError(
                    "accept_value should contain exactly one key-value pair"
                )

            key, value_type = next(iter(accept_value.items()))
            if choice in ("y", "yes"):
                return True
            if choice in ("n", "no"):
                return False

            try:
                return value_type(choice)
            except ValueError:
                log_info(
                    f"Invalid input, please enter Y/n or a valid {key}",
                    context="config",
                )


def _get_yes_no_input_with_timeout(
    prompt: str,
    default_choice: str = "y",
    accept_value: dict[str, type] | None = None,
    timeout: int = 30,
):
    """Get yes/no input with timeout.

    Args:
        prompt: Input prompt string.
        default_choice: Default choice if user just presses enter.
        accept_value: If provided, allows user to input a specific value.
        timeout: Timeout in seconds.

    Returns:
        True for yes, False for no, or the accepted value.

    Raises:
        TimeoutError: If timeout occurs and no default is provided.
    """
    result = None

    def input_thread():
        nonlocal result
        try:
            result = _get_yes_no_input(prompt, default_choice, accept_value)
        except Exception:
            pass

    thread = threading.Thread(target=input_thread)
    thread.daemon = True
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        if default_choice is not None:
            return default_choice
        raise TimeoutError("Input timed out")
    return result


def _get_valid_username(username: str = "") -> str:
    """Get a valid username through interactive input.

    Ensures username is not empty, contains no whitespace, and is not 'cels'.

    Args:
        username: Pre-existing username to validate.

    Returns:
        Validated username.
    """
    is_valid = False
    while not is_valid:
        username = (
            username.strip().lower()
            if username
            else input("Enter your username: ").strip()
        )

        if not username:
            log_warning("Username cannot be empty.", context="config")
            username = ""
            continue
        if " " in username:
            log_warning("Invalid username: Must not contain spaces.", context="config")
            username = ""
            continue
        if username.lower() == "cels":
            log_warning("Invalid username: 'cels' is not allowed.", context="config")
            username = ""
            continue

        is_valid = True

    return username


def _get_user_port_choice(prompt: str, default_port: int) -> int:
    """Helper to get port choice from user with validation."""
    result = _get_yes_no_input(
        prompt=prompt, default_choice="y", accept_value={"port": int}
    )

    if result is True:
        return default_port
    elif result is False:
        raise ValueError("Port selection aborted by user")
    else:  # port number
        if is_port_available(result):
            return result
        log_warning(
            f"Port {result} is not available, please try again", context="config"
        )
        return _get_user_port_choice(prompt, default_port)


def _get_base_url_input(default: str) -> str:
    """Prompt user for the upstream base URL with a default value.

    Args:
        default: The default URL shown in brackets.

    Returns:
        The user-provided URL or the default if input is empty.
    """
    while True:
        url = input(f"Enter upstream base URL [{default}]: ").strip()
        if not url:
            return default
        if not url.startswith(("http://", "https://")):
            log_warning(
                "Invalid URL: must start with http:// or https://", context="config"
            )
            continue
        return url.rstrip("/")


def create_config(config_path: str | None = None) -> ArgoConfig:
    """Interactive method to create and persist config.

    Args:
        config_path: Optional path to save the config file. If not
            provided, saves to the default location.
    """
    # Lazy imports to avoid circular dependencies
    from .io import save_config
    from .validation import _validate_base_url, validate_user

    log_info("Creating new configuration...", context="config")

    default_base = ArgoConfig._argo_dev_base
    while True:
        base_url = _get_base_url_input(default_base)
        log_info("Validating upstream connectivity...", context="config")
        if _validate_base_url(base_url):
            log_info(f"Upstream {base_url} is reachable.", context="config")
            break
        log_error(
            f"Cannot reach {base_url}/v1/models. "
            "Check the URL and your network connection.",
            context="config",
        )

    random_port = get_random_port(49152, 65535)
    port = _get_user_port_choice(
        prompt=f"Use port [{random_port}]? [Y/n/<port>]: ",
        default_port=random_port,
    )

    # Create config with base URL and port so validate_user() can reach upstream
    config_data = ArgoConfig(_argo_base_url=base_url, port=port, config_version="3")
    validate_user(config_data)

    config_data.verbose = _get_yes_no_input(prompt="Enable verbose mode? [Y/n] ")

    saved_path = save_config(config_data, config_path)
    log_info(f"Created new configuration at: {saved_path}", context="config")

    return config_data
