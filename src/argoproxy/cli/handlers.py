"""Subcommand handlers for the Argo Proxy CLI."""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from packaging import version

from ..__init__ import __version__
from ..config import PATHS_TO_TRY, validate_config
from ..utils.attack_logger import get_attack_logger
from ..utils.logging import log_error, log_info, log_warning
from .display import CHANGELOG_URL, display_startup_banner


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


def handle_serve(args: argparse.Namespace):
    """Handle the ``serve`` subcommand."""
    from ..app import run

    # Import setup_logging lazily to avoid circular imports
    from . import setup_logging

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


def _migrate_config(config_path: str | None = None):
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


def _open_in_editor(config_path: str | None = None):
    """Open the configuration file in the user's preferred editor.

    Args:
        config_path: Optional explicit path to the config file.
    """
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


def handle_config(args: argparse.Namespace):
    """Handle the ``config`` subcommand."""
    if not args.config_action:
        # No action given -- show help
        from .parser import create_parser

        create_parser().parse_args(["config", "--help"])
        return

    config_path = getattr(args, "config", None)

    if args.config_action == "edit":
        _open_in_editor(config_path)
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
        _migrate_config(config_path)


# ---------------------------------------------------------------------------
# Logs handler
# ---------------------------------------------------------------------------


def _collect_leaked_logs(config_path: str | None = None):
    """Collect all leaked tool call logs into a tar.gz archive.

    Args:
        config_path: Optional explicit path to the config file.
    """
    import tarfile
    from datetime import datetime

    from ..config import load_config

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


def handle_logs(args: argparse.Namespace):
    """Handle the ``logs`` subcommand."""
    if not args.logs_action:
        from .parser import create_parser

        create_parser().parse_args(["logs", "--help"])
        return

    config_path = getattr(args, "config", None)

    if args.logs_action == "collect":
        _collect_leaked_logs(config_path)


# ---------------------------------------------------------------------------
# Update handler
# ---------------------------------------------------------------------------


def _get_pypi_versions() -> dict[str, str | None]:
    """Query PyPI for the latest stable and pre-release versions.

    Returns:
        Dict with keys ``stable`` and ``pre``, values are version strings
        or None.
    """
    import urllib.request

    url = "https://pypi.org/pypi/argo-proxy/json"
    result: dict[str, str | None] = {"stable": None, "pre": None}

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
                    f"  Stable:      v{stable}  \u2190 upgrade available", context="cli"
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
                log_info(
                    f"  Pre-release: v{pre}  \u2190 upgrade available", context="cli"
                )
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
    """Install the latest version using the detected package manager.

    Args:
        pre: If True, install the latest pre-release instead of stable.
    """
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

    log_info(
        f"Upgrading argo-proxy: v{current} \u2192 v{target} ({label})", context="cli"
    )
    log_info(f"Running: {' '.join(cmd)}", context="cli")
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        log_error("Update failed. See output above for details.", context="cli")
        sys.exit(1)

    log_info(
        "Update complete. Restart argo-proxy to use the new version.", context="cli"
    )


def handle_update(args: argparse.Namespace):
    """Handle the ``update`` subcommand."""
    if not args.update_action:
        from .parser import create_parser

        create_parser().parse_args(["update", "--help"])
        return

    if args.update_action == "check":
        _update_check()
    elif args.update_action == "install":
        _update_install(pre=args.pre)


# ---------------------------------------------------------------------------
# Models handler
# ---------------------------------------------------------------------------


def handle_models(args: argparse.Namespace):
    """Handle the ``models`` subcommand -- list available models and aliases."""
    import json as _json
    import threading
    from collections import defaultdict

    from ..config import load_config
    from ..models import ModelRegistry

    config_data, _ = load_config(args.config, verbose=False)
    if not config_data:
        log_error("No valid configuration found.", context="cli")
        sys.exit(1)

    registry = ModelRegistry(config=config_data)

    # Fetch with spinner
    done = threading.Event()

    def _spinner():
        frames = [
            "\u280b",
            "\u2819",
            "\u2839",
            "\u2838",
            "\u283c",
            "\u2834",
            "\u2826",
            "\u2827",
            "\u2807",
            "\u280f",
        ]
        i = 0
        while not done.is_set():
            print(
                f"\r{frames[i % len(frames)]} Fetching models from upstream...",
                end="",
                flush=True,
            )
            i += 1
            done.wait(0.1)
        print("\r" + " " * 50 + "\r", end="", flush=True)

    spinner_thread = threading.Thread(target=_spinner, daemon=True)
    spinner_thread.start()
    asyncio.run(registry.initialize())
    done.set()
    spinner_thread.join()

    # Build reverse maps: internal_id -> list of aliases (deduplicated)
    chat_id_to_aliases: dict[str, list[str]] = defaultdict(list)
    for alias, internal_id in registry.available_chat_models.items():
        if alias not in chat_id_to_aliases[internal_id]:
            chat_id_to_aliases[internal_id].append(alias)

    embed_id_to_aliases: dict[str, list[str]] = defaultdict(list)
    for alias, internal_id in registry.available_embed_models.items():
        if alias not in embed_id_to_aliases[internal_id]:
            embed_id_to_aliases[internal_id].append(alias)

    # Sort aliases within each group
    for aliases in chat_id_to_aliases.values():
        aliases.sort()
    for aliases in embed_id_to_aliases.values():
        aliases.sort()

    if args.json:
        output = []
        for internal_id, aliases in sorted(chat_id_to_aliases.items()):
            family = registry._classify_model_by_family(internal_id)
            output.append(
                {
                    "upstream_id": internal_id,
                    "type": "chat",
                    "family": family,
                    "aliases": aliases,
                }
            )
        for internal_id, aliases in sorted(embed_id_to_aliases.items()):
            output.append(
                {
                    "upstream_id": internal_id,
                    "type": "embedding",
                    "family": "openai",
                    "aliases": aliases,
                }
            )
        print(_json.dumps(output, indent=2))
        return

    # Table output -- organized by type, then by provider
    stats = registry.get_model_stats()
    print(
        f"Available models: {stats['unique_models']} models, "
        f"{stats['total_aliases']} aliases"
    )

    # --- Chat Models ---
    print(
        f"\n  Chat Models ({stats['unique_chat_models']} models, "
        f"{stats['chat_aliases']} aliases)"
    )

    family_order = ["openai", "anthropic", "google", "unknown"]
    family_labels = {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google",
        "unknown": "Other",
    }

    # Classify chat models by family
    chat_families: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for internal_id, aliases in sorted(chat_id_to_aliases.items()):
        family = registry._classify_model_by_family(internal_id)
        chat_families[family].append((internal_id, aliases))

    for family in family_order:
        entries = chat_families.get(family, [])
        if not entries:
            continue
        label = family_labels.get(family, family)
        print(f"\n    {label} ({len(entries)} models)")
        for internal_id, aliases in entries:
            alias_str = ", ".join(aliases)
            print(f"      {internal_id:<30s} {alias_str}")

    # --- Embedding Models ---
    if embed_id_to_aliases:
        embed_count = len(embed_id_to_aliases)
        embed_alias_count = sum(len(a) for a in embed_id_to_aliases.values())
        print(
            f"\n  Embedding Models ({embed_count} models, {embed_alias_count} aliases)"
        )
        for internal_id, aliases in sorted(embed_id_to_aliases.items()):
            alias_str = ", ".join(aliases)
            print(f"      {internal_id:<30s} {alias_str}")

    print()
