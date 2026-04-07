"""Argument parser construction for Argo Proxy CLI."""

import argparse
import os
import sys
from argparse import RawTextHelpFormatter
from difflib import get_close_matches

from .display import version_check

# Known subcommands -- used for default-subcommand detection
_SUBCOMMANDS = {"serve", "config", "logs", "update", "models"}

_DOCS_BASE = "https://argo-proxy.readthedocs.io/en/latest"


def _docs_epilog(path: str) -> str:
    """Build a help epilog line pointing to the ReadTheDocs page."""
    return f"Docs: {_DOCS_BASE}/{path}"


def _add_serve_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the ``serve`` subcommand."""
    parser.add_argument(
        "config",
        type=str,
        nargs="?",
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

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose logging",
    )
    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Disable verbose logging",
    )

    parser.add_argument(
        "--show",
        "-s",
        action="store_true",
        help="Show the current configuration during launch",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        default=False,
        help="Suppress the ASCII banner on startup",
    )
    parser.add_argument(
        "--username-passthrough",
        action="store_true",
        help="Use API key from request headers as user field",
    )
    parser.add_argument(
        "--legacy-argo",
        action="store_true",
        default=False,
        help="Use the legacy ARGO gateway pipeline instead of universal dispatch",
    )
    parser.add_argument(
        "--enable-leaked-tool-fix",
        action="store_true",
        default=False,
        help="[Legacy only] Enable AST-based leaked tool call detection and fixing",
    )
    parser.add_argument(
        "--anthropic-stream-mode",
        type=str,
        choices=["force", "retry", "passthrough"],
        default=None,
        help=(
            "How to handle non-streaming requests to Anthropic upstream.\n"
            "  force:       Always force streaming, aggregate back (default)\n"
            "  retry:       Try non-streaming first, retry with streaming on error\n"
            "  passthrough: Never force streaming, pass through as-is"
        ),
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )

    # Legacy-only streaming options
    stream_group = parser.add_mutually_exclusive_group()
    stream_group.add_argument(
        "--real-stream",
        "-rs",
        action="store_true",
        default=False,
        help="[Legacy only] Enable real streaming (default behavior)",
    )
    stream_group.add_argument(
        "--pseudo-stream",
        "-ps",
        action="store_true",
        default=False,
        help="[Legacy only] Enable pseudo streaming",
    )
    parser.add_argument(
        "--tool-prompting",
        action="store_true",
        help="[Legacy only] Enable prompting-based tool calls",
    )


def _add_config_subparsers(parser: argparse.ArgumentParser) -> None:
    """Add sub-subcommands for the ``config`` subcommand."""
    sub = parser.add_subparsers(dest="config_action", metavar="action")

    edit_parser = sub.add_parser("edit", help="Open config in the default editor")
    edit_parser.add_argument("config", nargs="?", default=None, help="Config file path")

    validate_parser = sub.add_parser("validate", help="Validate config and exit")
    validate_parser.add_argument(
        "config", nargs="?", default=None, help="Config file path"
    )

    show_parser = sub.add_parser("show", help="Show the current configuration")
    show_parser.add_argument("config", nargs="?", default=None, help="Config file path")

    migrate_parser = sub.add_parser(
        "migrate", help="Migrate config from v1/v2 to v3 (creates .bak backup)"
    )
    migrate_parser.add_argument(
        "config", nargs="?", default=None, help="Config file path"
    )

    init_parser = sub.add_parser(
        "init", help="Create a new config interactively (overwrites if exists)"
    )
    init_parser.add_argument("config", nargs="?", default=None, help="Config file path")
    init_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        default=False,
        help="Overwrite existing config without confirmation",
    )

    sub.add_parser("list", help="List all config files found in search paths")

    env_parser = sub.add_parser(
        "env", help="Show or switch upstream environment (prod/dev/test)"
    )
    env_parser.add_argument(
        "environment",
        nargs="?",
        default=None,
        choices=["prod", "dev", "test"],
        help="Target environment to switch to",
    )
    env_parser.add_argument(
        "--config", "-c", default=None, dest="config", help="Config file path"
    )


def _add_logs_subparsers(parser: argparse.ArgumentParser) -> None:
    """Add sub-subcommands for the ``logs`` subcommand."""
    sub = parser.add_subparsers(dest="logs_action", metavar="action")

    collect_parser = sub.add_parser(
        "collect", help="Collect diagnostic logs into a tar.gz archive"
    )
    collect_parser.add_argument(
        "config", nargs="?", default=None, help="Config file path"
    )
    collect_parser.add_argument(
        "--type",
        "-t",
        type=str,
        choices=["leaked-tool", "stream-retry", "error-dump", "all"],
        default="all",
        help=(
            "Type of diagnostic logs to collect (default: all)\n"
            "  leaked-tool:  Leaked tool call logs\n"
            "  stream-retry: Anthropic stream retry request dumps\n"
            "  error-dump:   Upstream error request/response dumps\n"
            "  all:          All diagnostic logs"
        ),
    )


def _add_update_subparsers(parser: argparse.ArgumentParser) -> None:
    """Add sub-subcommands for the ``update`` subcommand."""
    sub = parser.add_subparsers(dest="update_action", metavar="action")

    sub.add_parser("check", help="Check for available updates (stable and pre-release)")

    install_parser = sub.add_parser("install", help="Install the latest version")
    install_parser.add_argument(
        "--pre",
        action="store_true",
        default=False,
        help="Install the latest pre-release version instead of stable",
    )


def _add_models_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments for the ``models`` subcommand."""
    parser.add_argument(
        "config",
        type=str,
        nargs="?",
        help="Path to the configuration file",
        default=None,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output in JSON format",
    )


def create_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="argo-proxy",
        description="Argo Proxy -- universal API gateway for LLM services",
        formatter_class=RawTextHelpFormatter,
        epilog=_docs_epilog("usage/basics/cli/"),
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {version_check()}",
        help="Show the version and check for updates",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    # serve
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the proxy server (default)",
        formatter_class=RawTextHelpFormatter,
        epilog=_docs_epilog("usage/running/"),
    )
    _add_serve_arguments(serve_parser)

    # config
    config_parser = subparsers.add_parser(
        "config",
        help="Manage configuration files",
        formatter_class=RawTextHelpFormatter,
        epilog=_docs_epilog("usage/basics/configuration/"),
    )
    _add_config_subparsers(config_parser)

    # logs
    logs_parser = subparsers.add_parser(
        "logs",
        help="Collect diagnostic logs",
        formatter_class=RawTextHelpFormatter,
        epilog=_docs_epilog("usage/basics/cli/#logs--collect-diagnostic-logs"),
    )
    _add_logs_subparsers(logs_parser)

    # update
    update_parser = subparsers.add_parser(
        "update",
        help="Check for and install updates",
        formatter_class=RawTextHelpFormatter,
        epilog=_docs_epilog("usage/basics/cli/#update--check-and-install-updates"),
    )
    _add_update_subparsers(update_parser)

    # models
    models_parser = subparsers.add_parser(
        "models",
        help="List available upstream models and their aliases",
        formatter_class=RawTextHelpFormatter,
        epilog=_docs_epilog("usage/models/"),
    )
    _add_models_arguments(models_parser)

    return parser


def insert_default_subcommand() -> None:
    """Insert ``serve`` into sys.argv when no subcommand is given.

    This keeps backward compatibility: ``argo-proxy config.yaml`` still works
    as ``argo-proxy serve config.yaml``.
    """
    if len(sys.argv) < 2:
        return  # Will show help via parser

    # Don't insert if only top-level flags are present
    top_level_flags = {"-h", "--help", "-V", "--version"}
    if all(arg in top_level_flags for arg in sys.argv[1:]):
        return

    # Skip over the program name, find the first non-flag argument
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        # If the first positional is a known subcommand, nothing to do
        if arg in _SUBCOMMANDS:
            return
        # Check for typos before falling back to ``serve``.
        # Skip fuzzy matching if the arg looks like a file path or exists on disk.
        looks_like_path = "." in arg or "/" in arg or "\\" in arg or os.path.isfile(arg)
        close = (
            get_close_matches(arg, _SUBCOMMANDS, n=1, cutoff=0.9)
            if not looks_like_path
            else []
        )
        if close:
            print(
                f"argo-proxy: unknown command '{arg}'. Did you mean '{close[0]}'?",
                file=sys.stderr,
            )
            sys.exit(2)
        # Otherwise it's a config path -- assume ``serve``
        break

    # If only flags are present (e.g. ``argo-proxy --verbose``), also assume serve
    sys.argv.insert(1, "serve")
