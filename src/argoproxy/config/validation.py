"""Configuration validation: user, port, and URL connectivity checks."""

import asyncio
import json
from hashlib import md5
from typing import Any

from ..utils.logging import log_error, log_info, log_warning
from ..utils.misc import get_random_port, is_port_available
from ..utils.transports import (
    validate_api_async,
    validate_url_get_async,
    validate_user_async,
)
from .interactive import _get_user_port_choice, _get_valid_username, _get_yes_no_input
from .model import ArgoConfig


def validate_config_fields(config: ArgoConfig) -> bool:
    """Validate and patch all configuration aspects.

    Args:
        config: The ArgoConfig instance to validate.

    Returns:
        True if configuration changed after validation, False otherwise.
    """
    config_dict = config.to_dict()
    for key in config.REQUIRED_KEYS:
        if key not in config_dict:
            raise ValueError(f"Missing required configuration: '{key}'")

    hash_original = md5(json.dumps(config_dict).encode()).hexdigest()
    validate_user(config)
    validate_port(config)
    validate_urls(config)
    hash_after_validation = md5(json.dumps(config.to_dict()).encode()).hexdigest()

    return hash_original != hash_after_validation


def validate_user(config: ArgoConfig) -> None:
    """Validate and update the user attribute.

    First checks local format rules (non-empty, no spaces, not 'cels'),
    then validates the username against the upstream ARGO API by making
    a test request and checking for the authentication warning.

    Args:
        config: The ArgoConfig instance to validate.
    """
    while True:
        config.user = _get_valid_username(config.user)

        if config._skip_url_validation or config._user_validated:
            break

        # Validate against upstream ARGO
        chat_url = f"{config.native_openai_base_url}/chat/completions"
        try:
            is_valid = asyncio.run(
                validate_user_async(
                    chat_url,
                    config.user,
                    timeout=config.connection_test_timeout,
                    resolver_overrides=config.resolve_overrides or None,
                )
            )
        except Exception:
            log_warning(
                "Could not validate username against ARGO upstream "
                "(network may be unavailable). Skipping user validation.",
                context="config",
            )
            config._user_validated = True
            break

        if is_valid:
            log_info(
                f"Username '{config.user}' validated against ARGO.",
                context="config",
            )
            config._user_validated = True
            break

        log_error(
            f"Username '{config.user}' is not registered in ARGO. "
            "Please enter a valid ANL username.",
            context="config",
        )
        config.user = ""  # Reset to trigger re-prompt


def validate_port(config: ArgoConfig) -> None:
    """Validate and patch the port attribute.

    Args:
        config: The ArgoConfig instance to validate.
    """
    if config.port and is_port_available(config.port):
        log_info(f"Using port {config.port}...", context="config")
        return  # Valid port already set

    if config.port:
        log_warning(f"Warning: Port {config.port} is already in use.", context="config")

    suggested_port = get_random_port(49152, 65535)
    config.port = _get_user_port_choice(
        prompt=f"Enter port [{suggested_port}] [Y/n/number]: ",
        default_port=suggested_port,
    )
    log_info(f"Using port {config.port}...", context="config")


def validate_urls(config: ArgoConfig) -> None:
    """Validate URL connectivity.

    In v3 universal mode, tests the native OpenAI models endpoint (GET)
    and the native Anthropic messages endpoint (POST).
    In legacy mode, tests the legacy ARGO chat and embedding endpoints.

    Args:
        config: The ArgoConfig instance to validate.
    """
    if config._skip_url_validation:
        log_info("URL validation skipped (skip_url_validation=True)", context="config")
        return

    timeout = config.connection_test_timeout
    attempts = 2
    failed_urls: list[str] = []

    if config.use_legacy_argo:
        # Legacy mode: POST-based validation against ARGO gateway
        post_urls: list[tuple[str, dict[str, Any]]] = [
            (
                config.argo_url,
                {
                    "model": "gpt4o",
                    "messages": [{"role": "user", "content": "What are you?"}],
                },
            ),
            (
                config.argo_embedding_url,
                {"model": "v3small", "prompt": ["hello"]},
            ),
        ]
        get_urls: list[str] = []
    else:
        # Universal mode: test native endpoints
        post_urls = []
        get_urls = [
            f"{config.native_openai_base_url}/models",
        ]

    log_info("Validating URL connectivity...", context="config")

    async def _validate_post(url: str, payload: dict) -> None:
        if not url.startswith(("http://", "https://")):
            log_error(f"Invalid URL format: {url}", context="config")
            failed_urls.append(url)
            return
        try:
            await validate_api_async(
                url,
                config.user,
                payload,
                timeout=timeout,
                attempts=attempts,
                resolver_overrides=config.resolve_overrides or None,
            )
        except Exception:
            failed_urls.append(url)

    async def _validate_get(url: str) -> None:
        if not url.startswith(("http://", "https://")):
            log_error(f"Invalid URL format: {url}", context="config")
            failed_urls.append(url)
            return
        try:
            await validate_url_get_async(
                url,
                timeout=timeout,
                attempts=attempts,
                resolver_overrides=config.resolve_overrides or None,
            )
        except Exception:
            failed_urls.append(url)

    async def _main():
        tasks = [_validate_post(url, payload) for url, payload in post_urls] + [
            _validate_get(url) for url in get_urls
        ]
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_main())
    except RuntimeError:
        log_error("Async validation failed unexpectedly.", context="config")
        raise

    if failed_urls:
        log_error("Failed to validate the following URLs: ", context="config")
        for url in failed_urls:
            log_error(url, context="config")
        log_warning(
            "Are you running the proxy on ANL network?\nIf yes, it's likely a temporary network glitch. In case of persistent issues, check your network or reach out to ANL CELS Helpdesk.\nIf not, 1. set up VPN and try again, OR 2. deploy it on an ANL machine you can create ssh tunnel to.",
            context="config",
        )

        if not _get_yes_no_input(
            prompt="Continue despite connectivity issue? [Y/n] ", default_choice="y"
        ):
            raise ValueError("URL validation aborted by user")
        log_info(
            "Continuing with configuration despite URL issues...", context="config"
        )
    else:
        log_info("All URLs connectivity validated successfully.", context="config")


def _validate_base_url(base_url: str, timeout: int = 5) -> bool:
    """Validate upstream base URL connectivity via GET /v1/models.

    Args:
        base_url: The upstream base URL to validate.
        timeout: Request timeout seconds.

    Returns:
        True if the endpoint is reachable, False otherwise.
    """
    models_url = f"{base_url.rstrip('/')}/v1/models"
    try:
        asyncio.run(validate_url_get_async(models_url, timeout=timeout, attempts=2))
        return True
    except Exception:
        return False
