#!/usr/bin/env python3
import argparse
import asyncio
import logging
import os
import subprocess
import sys
from argparse import RawTextHelpFormatter
from pathlib import Path
from typing import Optional

from packaging import version

from .__init__ import __version__
from .app import run
from .config import PATHS_TO_TRY, validate_config
from .endpoints.extras import get_latest_pypi_version
from .utils.attack_logger import get_attack_logger, setup_attack_logging
from .utils.logging import (
    log_error,
    log_info,
    log_warning,
)
from .utils.logging import (
    setup_logging as setup_app_logging,
)


def setup_logging(verbose: bool = False, config_path: Optional[str] = None):
    """Setup logging with attack filter.

    Args:
        verbose: Enable verbose logging.
        config_path: Path to config file for attack log directory.
    """

    # Setup the application logger using standard library
    setup_app_logging(verbose=verbose)

    # Setup attack logging with config path
    path = Path(config_path) if config_path else None
    attack_filter = setup_attack_logging(path)

    # Apply filter to all aiohttp-related loggers
    # These loggers may emit attack-related errors at different levels
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

    # Also filter asyncio logs which may contain similar errors
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.addFilter(attack_filter)


# Initialize logging with default settings
setup_logging()


def parsing_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Argo Proxy CLI",
        formatter_class=RawTextHelpFormatter,
    )
    parser.add_argument(
        "config",
        type=str,
        nargs="?",  # makes argument optional
        help="Path to the configuration file",
        default=None,
    )
    parser.add_argument(
        "--host",
        "-H",
        type=str,
        help="Host address to bind the server to",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        help="Port number to bind the server to",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,  # default is False, so --verbose will set it to True
        help="Enable verbose logging, override if `verbose` set False in config",
    )
    group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,  # default is False, so --quiet will set it to True
        help="Disable verbose logging, override if `verbose` set True in config",
    )

    # Streaming mode group (mutually exclusive)
    stream_group = parser.add_mutually_exclusive_group()
    stream_group.add_argument(
        "--real-stream",
        "-rs",
        action="store_true",
        default=False,  # Will be handled in logic to default to True when neither option is specified
        help="Enable real streaming (default behavior), override if `real_stream` set False in config",
    )
    stream_group.add_argument(
        "--pseudo-stream",
        "-ps",
        action="store_true",
        default=False,
        help="Enable pseudo streaming, override if `real_stream` set True or omitted in config",
    )

    parser.add_argument(
        "--tool-prompting",
        action="store_true",
        help="Enable prompting-based tool calls/function calling, otherwise use native tool calls/function calling",
    )
    parser.add_argument(
        "--provider-tool-format",
        action="store_true",
        help="Enable provider-specific tool format, user should handle the tool calls as they arrive, otherwise all tool calls will be converted to the openai format",
    )
    parser.add_argument(
        "--username-passthrough",
        action="store_true",
        help="Enable username passthrough mode - use API key from request headers as user field",
    )
    parser.add_argument(
        "--native-openai",
        action="store_true",
        default=False,
        help="Enable native OpenAI endpoint passthrough mode - directly forward requests to native OpenAI endpoint without transformation",
    )
    parser.add_argument(
        "--enable-leaked-tool-fix",
        action="store_true",
        default=False,
        help="Enable AST-based leaked tool call detection and fixing (experimental). When disabled, leaked tool calls will be logged for analysis.",
    )

    parser.add_argument(
        "--edit",
        "-e",
        action="store_true",
        help="Open the configuration file in the system's default editor for editing",
    )
    parser.add_argument(
        "--validate",
        "-vv",
        action="store_true",
        help="Validate the configuration file and exit",
    )
    parser.add_argument(
        "--show",
        "-s",
        action="store_true",
        help="Show the current configuration during launch",
    )
    parser.add_argument(
        "--version",
        "-V",
        # action="store_true",  # Changed from 'version' to 'store_true'
        action="version",
        version=f"%(prog)s {version_check()}",
        help="Show the version and check for updates",
    )
    parser.add_argument(
        "--collect-leaked-logs",
        action="store_true",
        help="Collect all leaked tool call logs into a tar.gz archive for analysis",
    )

    args = parser.parse_args()

    return args


def set_config_envs(args: argparse.Namespace):
    if args.config:
        os.environ["CONFIG_PATH"] = args.config

    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.verbose:
        os.environ["VERBOSE"] = str(True)
    if args.quiet:
        os.environ["VERBOSE"] = str(False)

    # Handle streaming mode: default to real stream if neither option is specified
    if args.real_stream:
        os.environ["REAL_STREAM"] = str(True)
    if args.pseudo_stream:
        os.environ["REAL_STREAM"] = str(False)
    if args.tool_prompting:
        os.environ["TOOL_PROMPT"] = str(True)
    if args.provider_tool_format:
        os.environ["PROVIDER_TOOL_FORMAT"] = str(True)
    if args.username_passthrough:
        os.environ["USERNAME_PASSTHROUGH"] = str(True)
    if args.native_openai:
        os.environ["USE_NATIVE_OPENAI"] = str(True)
    if args.enable_leaked_tool_fix:
        os.environ["ENABLE_LEAKED_TOOL_FIX"] = str(True)


def open_in_editor(config_path: Optional[str] = None):
    paths_to_try = [config_path] if config_path else PATHS_TO_TRY

    # Add EDITOR from environment variable if set, followed by defaults
    editors_to_try = [os.getenv("EDITOR")] if os.getenv("EDITOR") else []
    editors_to_try += ["notepad"] if os.name == "nt" else ["nano", "vi", "vim"]
    # Filter out None editors
    editors_to_try = [e for e in editors_to_try if e is not None]

    for path in paths_to_try:
        if path and os.path.exists(path):
            for editor in editors_to_try:
                try:
                    subprocess.run([editor, path], check=True)
                    return
                except FileNotFoundError:
                    continue  # Try the next editor in the list
                except Exception as e:
                    log_error(
                        f"Failed to open editor with {editor} for {path}: {e}",
                        context="cli",
                    )
                    sys.exit(1)

    log_error("No valid configuration file found to edit.", context="cli")
    sys.exit(1)


def get_ascii_banner() -> str:
    """Generate ASCII banner for Argo Proxy"""
    return """
 █████╗ ██████╗  ██████╗  ██████╗     ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗
██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗    ██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝
███████║██████╔╝██║  ███╗██║   ██║    ██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝
██╔══██║██╔══██╗██║   ██║██║   ██║    ██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝
██║  ██║██║  ██║╚██████╔╝╚██████╔╝    ██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝     ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝
"""


# ReadTheDocs changelog URL
CHANGELOG_URL = "https://argo-proxy.readthedocs.io/en/latest/changelog/"


def version_check() -> str:
    ver_content = [__version__]
    latest = asyncio.run(get_latest_pypi_version())

    if latest:
        # Use packaging.version to compare versions correctly
        if version.parse(latest) > version.parse(__version__):
            ver_content.extend(
                [
                    f"New version available: {latest}",
                    "Update with `pip install --upgrade argo-proxy`",
                    f"Changelog: {CHANGELOG_URL}",
                ]
            )

    return "\n".join(ver_content)


def display_startup_banner():
    """Display startup banner with version information"""
    banner = get_ascii_banner()
    latest = asyncio.run(get_latest_pypi_version())

    # Print banner
    print(banner)

    # Version information with styling
    log_info("=" * 80, context="cli")
    if latest and version.parse(latest) > version.parse(__version__):
        log_warning(f"🚀 ARGO PROXY v{__version__}", context="cli")
        log_warning(f"🆕 UPDATE AVAILABLE: v{latest}", context="cli")
        log_info("   ├─ Run: pip install --upgrade argo-proxy", context="cli")
        log_info(f"   └─ Changelog: {CHANGELOG_URL}", context="cli")
    else:
        log_warning(f"🚀 ARGO PROXY v{__version__} (Latest)", context="cli")
    log_info("=" * 80, context="cli")


def collect_leaked_logs(config_path: Optional[str] = None):
    """Collect all leaked tool call logs into a tar.gz archive."""
    import tarfile
    from datetime import datetime
    from pathlib import Path

    from .config import load_config

    # Get log directory
    config_data, actual_config_path = load_config(config_path, verbose=False)

    if actual_config_path:
        log_dir = actual_config_path.parent / "leaked_tool_calls"
    else:
        log_dir = Path.cwd() / "leaked_tool_calls"

    if not log_dir.exists():
        log_error(f"Log directory not found: {log_dir}", context="cli")
        log_info("No leaked tool call logs to collect.", context="cli")
        return

    # Find all log files (both .json and .json.gz)
    json_files = list(log_dir.glob("leaked_tool_*.json"))
    gz_files = list(log_dir.glob("leaked_tool_*.json.gz"))

    if not json_files and not gz_files:
        log_info(f"No leaked tool call logs found in {log_dir}", context="cli")
        return

    # Create archive filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"leaked_tool_logs_{timestamp}.tar.gz"
    archive_path = Path.cwd() / archive_name

    log_info(
        f"Collecting {len(json_files)} JSON and {len(gz_files)} compressed logs...",
        context="cli",
    )
    log_info(f"Creating archive: {archive_path}", context="cli")

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            # Add all JSON files (will be compressed by tar.gz)
            for json_file in json_files:
                tar.add(json_file, arcname=json_file.name)

            # Add all .json.gz files (already compressed, but tar.gz will try again)
            for gz_file in gz_files:
                tar.add(gz_file, arcname=gz_file.name)

        # Get archive size
        archive_size = archive_path.stat().st_size
        log_info("=" * 80, context="cli")
        log_info("✅ Archive created successfully!", context="cli")
        log_info(f"   Location: {archive_path}", context="cli")
        log_info(f"   Size: {archive_size / 1024 / 1024:.2f} MB", context="cli")
        log_info(f"   Files: {len(json_files) + len(gz_files)} logs", context="cli")
        log_info("=" * 80, context="cli")
        log_info("", context="cli")
        log_info(
            "📊 These logs are crucial for improving argo-proxy and Argo API!",
            context="cli",
        )
        log_info("", context="cli")
        log_info(
            "They contain examples of Claude model's tool call buggy forms,",
            context="cli",
        )
        log_info(
            "which help us understand and fix edge cases in tool call handling.",
            context="cli",
        )
        log_info("", context="cli")
        log_info("Please send this archive to:", context="cli")
        log_info(
            "  • Matthew Dearing (Argo API maintainer): mdearing@anl.gov", context="cli"
        )
        log_info(
            "  • Peng Ding (argo-proxy maintainer): dingpeng@uchicago.edu",
            context="cli",
        )
        log_info("", context="cli")
        log_info("Thank you for helping us improve the service! 🙏", context="cli")
        log_info("=" * 80, context="cli")

    except Exception as e:
        log_error(f"Failed to create archive: {e}", context="cli")
        sys.exit(1)


def main():
    args = parsing_args()

    if args.edit:
        open_in_editor(args.config)
        return

    if args.collect_leaked_logs:
        collect_leaked_logs(args.config)
        return

    set_config_envs(args)

    try:
        # Display startup banner
        display_startup_banner()

        # Validate config in main process only
        config_instance = validate_config(args.config, args.show)

        # Re-setup logging with correct verbosity and config path
        # This ensures attack logs go to the right directory
        from pathlib import Path

        config_path = Path(args.config) if args.config else None
        if config_path is None and hasattr(config_instance, "_config_path"):
            config_path = config_instance._config_path
        setup_logging(
            verbose=args.verbose, config_path=str(config_path) if config_path else None
        )

        # Update attack logger with actual config path
        if config_path:
            get_attack_logger().set_config_path(config_path)
        if args.validate:
            log_info("Configuration validation successful.", context="cli")
            return
        run(host=config_instance.host, port=config_instance.port)
    except KeyError:
        log_error("Port not specified in configuration file.", context="cli")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        log_error(f"Failed to start ArgoProxy server: {e}", context="cli")
        sys.exit(1)
    except Exception as e:
        log_error(f"An error occurred while starting the server: {e}", context="cli")
        sys.exit(1)


if __name__ == "__main__":
    main()
