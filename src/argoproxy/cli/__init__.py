"""Argo Proxy CLI -- universal API gateway for LLM services.

Subcommands:
    serve   Start the proxy server (default if no subcommand given)
    config  Manage configuration files (edit, validate, show, migrate)
    logs    Collect diagnostic logs
"""

import logging
import sys
from pathlib import Path

from ..utils.attack_logger import setup_attack_logging
from ..utils.logging import setup_logging as setup_app_logging


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging(verbose: bool = False, config_path: str | None = None):
    """Setup logging with attack filter.

    Args:
        verbose: Enable verbose logging.
        config_path: Path to config file for attack log directory.
    """
    setup_app_logging(verbose=verbose)

    path = Path(config_path) if config_path else None
    attack_filter = setup_attack_logging(path)

    aiohttp_loggers = [
        "aiohttp",
        "aiohttp.access",
        "aiohttp.client",
        "aiohttp.internal",
        "aiohttp.server",
        "aiohttp.web",
        "aiohttp.web_protocol",
    ]

    for logger_name in aiohttp_loggers:
        logger = logging.getLogger(logger_name)
        logger.addFilter(attack_filter)

    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.addFilter(attack_filter)


# Initialize logging with default settings
setup_logging()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """CLI entry point for argo-proxy."""
    from .handlers import (
        handle_config,
        handle_logs,
        handle_models,
        handle_serve,
        handle_update,
    )
    from .parser import create_parser, insert_default_subcommand

    insert_default_subcommand()
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        handle_serve(args)
    elif args.command == "config":
        handle_config(args)
    elif args.command == "logs":
        handle_logs(args)
    elif args.command == "update":
        handle_update(args)
    elif args.command == "models":
        handle_models(args)


if __name__ == "__main__":
    main()
