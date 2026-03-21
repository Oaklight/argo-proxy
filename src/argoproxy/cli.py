#!/usr/bin/env python3
"""Argo Proxy CLI — universal API gateway for LLM services.

Subcommands:
    serve   Start the proxy server (default if no subcommand given)
    config  Manage configuration files (edit, validate, show, migrate)
    logs    Collect diagnostic logs
"""

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


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging(verbose: bool = False, config_path: Optional[str] = None):
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
# Argument parsing
# ---------------------------------------------------------------------------

# Known subcommands — used for default-subcommand detection
_SUBCOMMANDS = {"serve", "config", "logs", "update"}


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


def _add_logs_subparsers(parser: argparse.ArgumentParser) -> None:
    """Add sub-subcommands for the ``logs`` subcommand."""
    sub = parser.add_subparsers(dest="logs_action", metavar="action")

    collect_parser = sub.add_parser(
        "collect", help="Collect leaked tool call logs into a tar.gz archive"
    )
    collect_parser.add_argument(
        "config", nargs="?", default=None, help="Config file path"
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


def create_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="argo-proxy",
        description="Argo Proxy — universal API gateway for LLM services",
        formatter_class=RawTextHelpFormatter,
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
    )
    _add_serve_arguments(serve_parser)

    # config
    config_parser = subparsers.add_parser(
        "config",
        help="Manage configuration files",
        formatter_class=RawTextHelpFormatter,
    )
    _add_config_subparsers(config_parser)

    # logs
    logs_parser = subparsers.add_parser(
        "logs",
        help="Collect diagnostic logs",
        formatter_class=RawTextHelpFormatter,
    )
    _add_logs_subparsers(logs_parser)

    # update
    update_parser = subparsers.add_parser(
        "update",
        help="Check for and install updates",
        formatter_class=RawTextHelpFormatter,
    )
    _add_update_subparsers(update_parser)

    return parser


def _insert_default_subcommand() -> None:
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
        # Otherwise it's a config path or unknown — assume ``serve``
        break

    # If only flags are present (e.g. ``argo-proxy --verbose``), also assume serve
    sys.argv.insert(1, "serve")


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def get_ascii_banner() -> str:
    """Generate ASCII banner for Argo Proxy."""
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
        if version.parse(latest) > version.parse(__version__):
            ver_content.extend(
                [
                    f"New version available: {latest}",
                    "Update with `pip install --upgrade argo-proxy`",
                    f"Changelog: {CHANGELOG_URL}",
                ]
            )

    return "\n".join(ver_content)


def display_startup_banner(no_banner: bool = False):
    """Display startup banner with version and mode information."""
    if not no_banner:
        banner = get_ascii_banner()
        print(banner)

    latest = asyncio.run(get_latest_pypi_version())

    log_info("=" * 80, context="cli")
    if latest and version.parse(latest) > version.parse(__version__):
        log_warning(f"🚀 ARGO PROXY v{__version__}", context="cli")
        log_warning(f"🆕 UPDATE AVAILABLE: v{latest}", context="cli")
        log_info("   ├─ Run: pip install --upgrade argo-proxy", context="cli")
        log_info(f"   └─ Changelog: {CHANGELOG_URL}", context="cli")
    else:
        log_warning(f"🚀 ARGO PROXY v{__version__} (Latest)", context="cli")

    from .utils.misc import str_to_bool

    dev_mode = str_to_bool(os.environ.get("DEV_MODE", "false"))

    if str_to_bool(os.environ.get("USE_LEGACY_ARGO", "false")):
        log_warning("⚙️  MODE: Legacy ARGO Gateway", context="cli")
    elif dev_mode:
        log_warning("⚙️  MODE: Transparent Proxy (no conversion)", context="cli")
    else:
        log_info("⚙️  MODE: Universal (llm-rosetta)", context="cli")
    log_info("=" * 80, context="cli")


# ---------------------------------------------------------------------------
# Config migration
# ---------------------------------------------------------------------------


def migrate_config(config_path: Optional[str] = None):
    """Migrate configuration file from v1/v2 to v3 format in place.

    Creates a .bak backup before writing changes.

    Args:
        config_path: Optional explicit path to the config file.
    """
    import shutil

    import yaml

    paths = [config_path] if config_path else PATHS_TO_TRY
    found_path = None
    for p in paths:
        if p and os.path.exists(p):
            found_path = p
            break

    if not found_path:
        log_error("No configuration file found to migrate.", context="cli")
        sys.exit(1)

    log_info(f"Migrating config: {found_path}", context="cli")

    with open(found_path, encoding="utf-8") as f:
        raw = f.read()

    data = yaml.safe_load(raw) or {}
    current_version = data.get("config_version", "")

    if current_version == "3":
        log_info("Config is already v3. Nothing to do.", context="cli")
        return

    backup_path = found_path + ".bak"
    shutil.copy2(found_path, backup_path)
    log_info(f"Backup saved: {backup_path}", context="cli")

    changes: list[str] = []

    old_ver = current_version or "(none)"
    data["config_version"] = "3"
    changes.append(f"config_version: {old_ver} -> 3")

    deprecated_keys = [
        "use_native_openai",
        "use_native_anthropic",
        "provider_tool_format",
    ]
    for key in deprecated_keys:
        if key in data:
            data.pop(key)
            changes.append(f"removed deprecated key: {key}")

    base_url = data.get("argo_base_url", "")
    if base_url:
        base = base_url.rstrip("/")
        if "native_openai_base_url" not in data:
            data["native_openai_base_url"] = f"{base}/v1"
            changes.append(f"added native_openai_base_url: {base}/v1")
        if "native_anthropic_base_url" not in data:
            data["native_anthropic_base_url"] = base
            changes.append(f"added native_anthropic_base_url: {base}")

    with open(found_path, "w", encoding="utf-8") as f:
        yaml.dump(
            data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
        )

    log_info("=" * 60, context="cli")
    log_info("Migration complete:", context="cli")
    for change in changes:
        log_info(f"  - {change}", context="cli")
    log_info("=" * 60, context="cli")


# ---------------------------------------------------------------------------
# Open in editor
# ---------------------------------------------------------------------------


def open_in_editor(config_path: Optional[str] = None):
    paths_to_try = [config_path] if config_path else PATHS_TO_TRY

    editors_to_try = [os.getenv("EDITOR")] if os.getenv("EDITOR") else []
    editors_to_try += ["notepad"] if os.name == "nt" else ["nano", "vi", "vim"]
    editors_to_try = [e for e in editors_to_try if e is not None]

    for path in paths_to_try:
        if path and os.path.exists(path):
            for editor in editors_to_try:
                try:
                    subprocess.run([editor, path], check=True)
                    return
                except FileNotFoundError:
                    continue
                except Exception as e:
                    log_error(
                        f"Failed to open editor with {editor} for {path}: {e}",
                        context="cli",
                    )
                    sys.exit(1)

    log_error("No valid configuration file found to edit.", context="cli")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Collect leaked logs
# ---------------------------------------------------------------------------


def collect_leaked_logs(config_path: Optional[str] = None):
    """Collect all leaked tool call logs into a tar.gz archive."""
    import tarfile
    from datetime import datetime

    from .config import load_config

    config_data, actual_config_path = load_config(config_path, verbose=False)

    if actual_config_path:
        log_dir = actual_config_path.parent / "leaked_tool_calls"
    else:
        log_dir = Path.cwd() / "leaked_tool_calls"

    if not log_dir.exists():
        log_error(f"Log directory not found: {log_dir}", context="cli")
        log_info("No leaked tool call logs to collect.", context="cli")
        return

    json_files = list(log_dir.glob("leaked_tool_*.json"))
    gz_files = list(log_dir.glob("leaked_tool_*.json.gz"))

    if not json_files and not gz_files:
        log_info(f"No leaked tool call logs found in {log_dir}", context="cli")
        return

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
            for json_file in json_files:
                tar.add(json_file, arcname=json_file.name)
            for gz_file in gz_files:
                tar.add(gz_file, arcname=gz_file.name)

        archive_size = archive_path.stat().st_size
        log_info("=" * 80, context="cli")
        log_info("Archive created successfully!", context="cli")
        log_info(f"   Location: {archive_path}", context="cli")
        log_info(f"   Size: {archive_size / 1024 / 1024:.2f} MB", context="cli")
        log_info(f"   Files: {len(json_files) + len(gz_files)} logs", context="cli")
        log_info("=" * 80, context="cli")
        log_info("", context="cli")
        log_info("Please send this archive to:", context="cli")
        log_info(
            "  - Matthew Dearing (Argo API maintainer): mdearing@anl.gov", context="cli"
        )
        log_info(
            "  - Peng Ding (argo-proxy maintainer): dingpeng@uchicago.edu",
            context="cli",
        )
        log_info("=" * 80, context="cli")

    except Exception as e:
        log_error(f"Failed to create archive: {e}", context="cli")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Serve handler
# ---------------------------------------------------------------------------


def set_config_envs(args: argparse.Namespace):
    """Set environment variables from serve CLI arguments."""
    if args.config:
        os.environ["CONFIG_PATH"] = args.config
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.verbose:
        os.environ["VERBOSE"] = str(True)
    if args.quiet:
        os.environ["VERBOSE"] = str(False)

    # Legacy-only streaming flags
    if args.real_stream:
        os.environ["REAL_STREAM"] = str(True)
    if args.pseudo_stream:
        os.environ["REAL_STREAM"] = str(False)
    if args.tool_prompting:
        os.environ["TOOL_PROMPT"] = str(True)
    if args.username_passthrough:
        os.environ["USERNAME_PASSTHROUGH"] = str(True)
    if args.legacy_argo:
        os.environ["USE_LEGACY_ARGO"] = str(True)
    if args.enable_leaked_tool_fix:
        os.environ["ENABLE_LEAKED_TOOL_FIX"] = str(True)
    if args.dev:
        os.environ["DEV_MODE"] = str(True)


def _handle_serve(args: argparse.Namespace):
    """Handle the ``serve`` subcommand."""
    set_config_envs(args)

    try:
        display_startup_banner(no_banner=args.no_banner)

        config_instance = validate_config(args.config, args.show)

        config_path: Path | None = Path(args.config) if args.config else None
        if config_path is None and hasattr(config_instance, "_config_path"):
            val = config_instance._config_path
            if isinstance(val, Path):
                config_path = val

        setup_logging(
            verbose=config_instance.verbose,
            config_path=str(config_path) if config_path else None,
        )

        if config_path is not None:
            get_attack_logger().set_config_path(config_path)

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


# ---------------------------------------------------------------------------
# Config handler
# ---------------------------------------------------------------------------


def _handle_config(args: argparse.Namespace):
    """Handle the ``config`` subcommand."""
    if not args.config_action:
        # No action given — show help
        create_parser().parse_args(["config", "--help"])
        return

    config_path = getattr(args, "config", None)

    if args.config_action == "edit":
        open_in_editor(config_path)
    elif args.config_action == "validate":
        try:
            validate_config(config_path, show_config=True)
            log_info("Configuration validation successful.", context="cli")
        except Exception as e:
            log_error(f"Configuration validation failed: {e}", context="cli")
            sys.exit(1)
    elif args.config_action == "show":
        try:
            validate_config(config_path, show_config=True)
        except Exception as e:
            log_error(f"Failed to load configuration: {e}", context="cli")
            sys.exit(1)
    elif args.config_action == "migrate":
        migrate_config(config_path)


# ---------------------------------------------------------------------------
# Logs handler
# ---------------------------------------------------------------------------


def _handle_logs(args: argparse.Namespace):
    """Handle the ``logs`` subcommand."""
    if not args.logs_action:
        create_parser().parse_args(["logs", "--help"])
        return

    config_path = getattr(args, "config", None)

    if args.logs_action == "collect":
        collect_leaked_logs(config_path)


# ---------------------------------------------------------------------------
# Update handler
# ---------------------------------------------------------------------------


def _get_pypi_versions() -> dict[str, Optional[str]]:
    """Query PyPI for the latest stable and pre-release versions.

    Returns:
        Dict with keys ``stable`` and ``pre``, values are version strings or None.
    """
    import urllib.request

    url = "https://pypi.org/pypi/argo-proxy/json"
    result: dict[str, Optional[str]] = {"stable": None, "pre": None}

    try:
        req = urllib.request.Request(
            url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json as _json

            data = _json.loads(resp.read())
    except Exception:
        return result

    # Latest stable is in info.version
    result["stable"] = data.get("info", {}).get("version")

    # Find the latest pre-release by scanning all releases
    all_versions = list(data.get("releases", {}).keys())
    pre_versions = []
    for v in all_versions:
        try:
            pv = version.parse(v)
            if pv.is_prerelease or pv.is_devrelease:
                pre_versions.append(pv)
        except Exception:
            continue

    if pre_versions:
        latest_pre = max(pre_versions)
        # Only show pre-release if it's newer than stable
        if result["stable"]:
            try:
                if latest_pre > version.parse(result["stable"]):
                    result["pre"] = str(latest_pre)
            except Exception:
                result["pre"] = str(latest_pre)
        else:
            result["pre"] = str(latest_pre)

    return result


def _detect_pip_command() -> list[str]:
    """Detect the best pip command for the current environment.

    Returns:
        Command list, e.g. ``["uv", "pip"]`` or ``["pip"]``.
    """
    import shutil

    if shutil.which("uv"):
        return ["uv", "pip"]
    if shutil.which("pip"):
        return ["pip"]
    # Fallback: use the current interpreter's pip module
    return [sys.executable, "-m", "pip"]


def _handle_update(args: argparse.Namespace):
    """Handle the ``update`` subcommand."""
    if not args.update_action:
        create_parser().parse_args(["update", "--help"])
        return

    if args.update_action == "check":
        _update_check()
    elif args.update_action == "install":
        _update_install(pre=args.pre)


def _update_check():
    """Check for available updates and display results."""
    current = __version__
    versions = _get_pypi_versions()

    print(f"argo-proxy v{current} (installed)")
    print()

    stable = versions.get("stable")
    pre = versions.get("pre")

    cur_parsed = version.parse(current)

    if stable:
        try:
            stable_parsed = version.parse(stable)
            if stable_parsed > cur_parsed:
                log_info(
                    f"  Stable:      v{stable}  ← upgrade available", context="cli"
                )
            elif cur_parsed > stable_parsed:
                log_info(
                    f"  Stable:      v{stable}  (installed is newer)", context="cli"
                )
            else:
                log_info(f"  Stable:      v{stable}  (up to date)", context="cli")
        except Exception:
            log_info(f"  Stable:      v{stable}", context="cli")
    else:
        log_warning("  Stable:      (unable to fetch)", context="cli")

    if pre:
        try:
            pre_parsed = version.parse(pre)
            if pre_parsed > cur_parsed:
                log_info(f"  Pre-release: v{pre}  ← upgrade available", context="cli")
            elif pre_parsed == cur_parsed:
                log_info(f"  Pre-release: v{pre}  (up to date)", context="cli")
            else:
                log_info(f"  Pre-release: v{pre}  (installed is newer)", context="cli")
        except Exception:
            log_info(f"  Pre-release: v{pre}", context="cli")
    else:
        log_info("  Pre-release: (none available)", context="cli")

    print()
    pip_cmd = " ".join(_detect_pip_command())
    if stable and version.parse(stable) > cur_parsed:
        log_info(
            f"  Update:       {pip_cmd} install --upgrade argo-proxy", context="cli"
        )
    if pre and version.parse(pre) > cur_parsed:
        log_info(
            f"  Pre-release:  {pip_cmd} install --upgrade --pre argo-proxy",
            context="cli",
        )
    print(f"  Changelog:    {CHANGELOG_URL}")


def _update_install(pre: bool = False):
    """Install the latest version using the detected package manager."""
    current = __version__
    versions = _get_pypi_versions()

    target = versions.get("pre") if pre else versions.get("stable")
    label = "pre-release" if pre else "stable"

    if not target:
        log_error(f"Unable to fetch {label} version from PyPI.", context="cli")
        sys.exit(1)

    try:
        if version.parse(target) <= version.parse(current):
            log_info(
                f"Already at v{current}, {label} is v{target}. Nothing to do.",
                context="cli",
            )
            return
    except Exception:
        pass

    pip_cmd = _detect_pip_command()
    cmd = [*pip_cmd, "install", "--upgrade"]
    if pre:
        cmd.append("--pre")
    cmd.append("argo-proxy")

    log_info(f"Upgrading argo-proxy: v{current} → v{target} ({label})", context="cli")
    log_info(f"Running: {' '.join(cmd)}", context="cli")
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        log_error("Update failed. See output above for details.", context="cli")
        sys.exit(1)

    log_info(
        "Update complete. Restart argo-proxy to use the new version.", context="cli"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    _insert_default_subcommand()
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        _handle_serve(args)
    elif args.command == "config":
        _handle_config(args)
    elif args.command == "logs":
        _handle_logs(args)
    elif args.command == "update":
        _handle_update(args)


if __name__ == "__main__":
    main()
