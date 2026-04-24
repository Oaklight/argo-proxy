"""Subcommand handlers for the Argo Proxy CLI."""

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from .._vendor.semver import version_parse

from ..__init__ import __version__
from ..config import PATHS_TO_TRY, validate_config
from ..utils.attack_logger import get_attack_logger
from ..utils.logging import log_error
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
    if args.anthropic_stream_mode:
        os.environ["ANTHROPIC_STREAM_MODE"] = args.anthropic_stream_mode
    if args.force_conversion:
        os.environ["FORCE_CONVERSION"] = str(True)
    if args.dump_requests:
        os.environ["DUMP_REQUESTS"] = str(True)
    if args.dump_dir:
        os.environ["DUMP_DIR"] = args.dump_dir


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
            log_to_file=config_instance.log_to_file,
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
    """Migrate configuration file to v3 format in place.

    Loads the config through the standard ``ArgoConfig`` pipeline (which
    normalizes fields, infers ``argo_base_url``, drops unknown keys, and
    bumps the version to v3), then writes it back using the canonical
    ``_format_config_yaml`` formatter.

    Creates a ``.bak`` backup before writing changes.

    Args:
        config_path: Optional explicit path to the config file.
    """
    import shutil

    from .._vendor import yaml

    from ..config.io import _format_config_yaml, load_config

    paths = [config_path] if config_path else PATHS_TO_TRY
    found_path = None
    for p in paths:
        if p and os.path.exists(p):
            found_path = p
            break

    if not found_path:
        log_error("No configuration file found to migrate.", context="cli")
        sys.exit(1)

    print(f"Migrating config: {found_path}")

    # Read original content
    with open(found_path, encoding="utf-8") as f:
        original_content = f.read()

    original_data = yaml.load(original_content) or {}

    # Load through standard pipeline (applies _migrate_config + from_dict)
    config, _ = load_config(found_path, env_override=False, verbose=False)
    if config is None:
        print(f"Error: Failed to load config from {found_path}", file=sys.stderr)
        sys.exit(1)

    # Produce canonical output
    persistent = config.to_persistent_dict()
    migrated_yaml = _format_config_yaml(persistent)

    # Check if anything actually changed
    if migrated_yaml.strip() == original_content.strip():
        print("Config is already in canonical v3 format. Nothing to do.")
        return

    # Create backup
    backup_path = found_path + ".bak"
    shutil.copy2(found_path, backup_path)
    print(f"Backup saved: {backup_path}")

    # Write migrated config
    with open(found_path, "w", encoding="utf-8") as f:
        f.write(migrated_yaml)

    # Report changes
    changes: list[str] = []
    old_ver = original_data.get("config_version", "") or "(none)"
    new_ver = persistent.get("config_version", "3")
    if old_ver != new_ver:
        changes.append(f"config_version: {old_ver} -> {new_ver}")

    for key in sorted(set(original_data) - set(persistent)):
        changes.append(f"removed: {key}")

    for key in sorted(set(persistent) - set(original_data)):
        changes.append(f"added: {key}: {persistent[key]}")

    print("=" * 60)
    print("Migration complete:")
    for change in changes:
        print(f"  - {change}")
    print("=" * 60)


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
            print("Configuration validation successful.")
        except Exception as e:
            print(f"Error: Configuration validation failed: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.config_action == "show":
        try:
            validate_config(config_path, show_config=True)
        except Exception as e:
            print(f"Error: Failed to load configuration: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.config_action == "migrate":
        _migrate_config(config_path)
    elif args.config_action == "init":
        _handle_init(config_path, force=args.force)
    elif args.config_action == "list":
        _list_configs()
    elif args.config_action == "env":
        _handle_env(getattr(args, "environment", None), config_path)


def _list_configs():
    """List all config files found in the standard search paths."""
    import glob

    from ..config.io import CONFIG_GLOB_PATTERNS, CONFIG_SEARCH_DIRS, load_config

    _, active_path = load_config(None, env_override=False, verbose=False)

    seen: set[str] = set()
    found: list[tuple[str, bool]] = []
    for search_dir in CONFIG_SEARCH_DIRS:
        expanded_dir = os.path.expanduser(search_dir)
        for pattern in CONFIG_GLOB_PATTERNS:
            for match in sorted(glob.glob(os.path.join(expanded_dir, pattern))):
                resolved = os.path.realpath(match)
                if resolved in seen:
                    continue
                seen.add(resolved)
                active = bool(
                    active_path and os.path.realpath(str(active_path)) == resolved
                )
                found.append((match, active))

    if not found:
        print("No config file found. Run 'argo-proxy config init' to create one.")
        return

    # Build table
    path_header = "Path"
    status_header = "Status"
    max_path = max(len(path_header), *(len(p) for p, _ in found))
    max_status = max(len(status_header), len("active"))

    print(f"  {path_header:<{max_path}}  {status_header:<{max_status}}")
    print(f"  {'-' * max_path}  {'-' * max_status}")
    for path, active in found:
        status = "active" if active else ""
        print(f"  {path:<{max_path}}  {status}")


def _handle_init(config_path: str | None = None, force: bool = False):
    """Create a new config interactively, optionally overwriting an existing one.

    Args:
        config_path: Optional path to save the config file.
        force: If True, skip overwrite confirmation for existing files.
    """
    from ..config.interactive import _get_yes_no_input, create_config

    # Check if target already exists
    target = config_path
    if target is None:
        home_dir = os.getenv("HOME") or os.path.expanduser("~")
        target = os.path.join(home_dir, ".config", "argoproxy", "config.yaml")

    if os.path.exists(target) and not force:
        print(f"Config already exists: {target}")
        overwrite = _get_yes_no_input(
            "Overwrite with a new interactive session? [y/N]: ",
            default_choice="n",
        )
        if not overwrite:
            print("Aborted.")
            return

    create_config(config_path=config_path)


def _handle_env(env_name: str | None = None, config_path: str | None = None):
    """Show or switch the upstream ARGO environment.

    Args:
        env_name: Target environment (prod/dev/test), or None to show current.
        config_path: Optional explicit path to the config file.
    """
    from ..config.io import load_config, save_config
    from ..config.model import ArgoConfig

    envs = ArgoConfig.ENVIRONMENTS

    config, actual_path = load_config(config_path, env_override=False, verbose=False)
    if config is None or actual_path is None:
        print(
            "Error: No configuration file found. Run 'argo-proxy config init' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    current_url = config.argo_base_url
    current_env = next((k for k, v in envs.items() if v == current_url), None)

    if env_name is None:
        # Show current environment
        label = current_env if current_env else "custom"
        print(f"Current environment: {label}")
        print(f"  argo_base_url: {current_url}")
        print()
        print("Available environments:")
        for name, url in envs.items():
            marker = " (active)" if name == current_env else ""
            print(f"  {name:<6s} {url}{marker}")
        return

    target_url = envs[env_name]
    if target_url == current_url:
        print(f"Already on '{env_name}' environment. Nothing to do.")
        return

    config._argo_base_url = target_url
    # Clear derived native URLs so they re-derive from new base
    config._native_openai_base_url = ""
    config._native_anthropic_base_url = ""

    save_config(config, actual_path)
    print(f"Switched to '{env_name}' environment.")
    print(f"  argo_base_url: {target_url}")


# ---------------------------------------------------------------------------
# Logs handler
# ---------------------------------------------------------------------------


# Known diagnostic log categories: (dir_name, file_glob_patterns)
_DIAGNOSTIC_LOG_TYPES: dict[str, tuple[str, list[str]]] = {
    "leaked-tool": (
        "leaked_tool_calls",
        ["leaked_tool_*.json", "leaked_tool_*.json.gz"],
    ),
    "stream-retry": ("stream_retry_dumps", ["retry_*.json", "retry_*.json.gz"]),
    "error-dump": ("error_dumps", ["error_*.json", "error_*.json.gz"]),
}


def _collect_diagnostic_logs(
    config_path: str | None = None, log_type: str = "all"
) -> None:
    """Collect diagnostic logs into a tar.gz archive.

    Args:
        config_path: Optional explicit path to the config file.
        log_type: Type of logs to collect. One of the keys in
            ``_DIAGNOSTIC_LOG_TYPES`` or ``"all"``.
    """
    import tarfile
    from datetime import datetime

    from ..config import load_config

    _, actual_config_path = load_config(config_path, verbose=False)
    base_dir = actual_config_path.parent if actual_config_path else Path.cwd()

    # Determine which log types to collect
    if log_type == "all":
        types_to_collect = list(_DIAGNOSTIC_LOG_TYPES.keys())
    else:
        types_to_collect = [log_type]

    # Gather files across all requested types
    all_files: list[tuple[Path, str]] = []  # (file_path, arcname)
    for type_key in types_to_collect:
        dir_name, patterns = _DIAGNOSTIC_LOG_TYPES[type_key]
        log_dir = base_dir / dir_name
        if not log_dir.exists():
            continue
        for pattern in patterns:
            for f in log_dir.glob(pattern):
                # Use subdir/filename as arcname to preserve category
                all_files.append((f, f"{dir_name}/{f.name}"))

    if not all_files:
        label = log_type if log_type != "all" else "diagnostic"
        print(f"No {label} logs found.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"diagnostic_logs_{log_type}_{timestamp}.tar.gz"
    archive_path = Path.cwd() / archive_name

    print(f"Collecting {len(all_files)} log files...")
    print(f"Creating archive: {archive_path}")

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            for file_path, arcname in all_files:
                tar.add(file_path, arcname=arcname)

        archive_size = archive_path.stat().st_size
        print("=" * 80)
        print("Archive created successfully!")
        print(f"   Location: {archive_path}")
        print(f"   Size: {archive_size / 1024 / 1024:.2f} MB")
        print(f"   Files: {len(all_files)} logs")
        print("=" * 80)
        print()
        print("Please send this archive to:")
        print("  - Matthew Dearing (Argo API maintainer): mdearing@anl.gov")
        print("  - Peng Ding (argo-proxy maintainer): dingpeng@uchicago.edu")
        print("=" * 80)

    except Exception as e:
        print(f"Error: Failed to create archive: {e}", file=sys.stderr)
        sys.exit(1)


def handle_logs(args: argparse.Namespace):
    """Handle the ``logs`` subcommand."""
    if not args.logs_action:
        from .parser import create_parser

        create_parser().parse_args(["logs", "--help"])
        return

    config_path = getattr(args, "config", None)

    if args.logs_action == "collect":
        _collect_diagnostic_logs(config_path, log_type=getattr(args, "type", "all"))


# ---------------------------------------------------------------------------
# Update handler
# ---------------------------------------------------------------------------


def _get_pypi_versions(pkg: str = "argo-proxy") -> dict[str, str | None]:
    """Query PyPI for the latest stable and pre-release versions.

    Args:
        pkg: Package name to query on PyPI.

    Returns:
        Dict with keys ``stable`` and ``pre``, values are version strings
        or None.
    """
    import asyncio

    from ..endpoints.extras import get_pypi_versions

    return asyncio.run(get_pypi_versions(pkg))


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
    """Check for available updates and display results in table format."""
    from .display import (
        _CRITICAL_DEPS,
        _DEP_CHANGELOG_URLS,
        _get_installed_version,
    )

    # Collect version info for all packages
    packages: list[dict] = []

    # argo-proxy itself
    argo_versions = _get_pypi_versions()
    packages.append(
        {
            "name": "argo-proxy",
            "installed": __version__,
            "stable": argo_versions.get("stable"),
            "pre": argo_versions.get("pre"),
        }
    )

    # Critical dependencies
    for pkg in _CRITICAL_DEPS:
        installed = _get_installed_version(pkg)
        if installed is None:
            continue
        versions = _get_pypi_versions(pkg)
        packages.append(
            {
                "name": pkg,
                "installed": installed,
                "stable": versions.get("stable"),
                "pre": versions.get("pre"),
            }
        )

    # Determine status and column widths
    col_pkg = max(len("Package"), *(len(p["name"]) for p in packages))
    col_inst = max(len("Installed"), *(len(p["installed"]) for p in packages))
    col_stable = max(len("Stable"), *(len(p["stable"] or "\u2014") for p in packages))
    col_pre = max(len("Pre"), *(len(p["pre"] or "\u2014") for p in packages))

    # Header
    header = (
        f"{'Package'.ljust(col_pkg)}  "
        f"{'Installed'.ljust(col_inst)}  "
        f"{'Stable'.ljust(col_stable)}  "
        f"{'Pre'.ljust(col_pre)}  "
        f"Status"
    )
    print(header)
    print("\u2500" * len(header))

    # Rows
    upgradable: list[dict] = []
    for pkg in packages:
        cur = version_parse(pkg["installed"])
        stable = pkg["stable"]
        pre = pkg["pre"]

        has_stable_update = False
        has_pre_update = False
        if stable:
            try:
                has_stable_update = version_parse(stable) > cur
            except Exception:
                pass
        if pre:
            try:
                has_pre_update = version_parse(pre) > cur
            except Exception:
                pass

        if has_stable_update or has_pre_update:
            status = "\u2b06 update available"
            pkg["has_stable_update"] = has_stable_update
            pkg["has_pre_update"] = has_pre_update
            upgradable.append(pkg)
        else:
            status = "\u2713 up to date"

        stable_display = stable or "\u2014"
        pre_display = pre or "\u2014"
        row = (
            f"{pkg['name'].ljust(col_pkg)}  "
            f"{pkg['installed'].ljust(col_inst)}  "
            f"{stable_display.ljust(col_stable)}  "
            f"{pre_display.ljust(col_pre)}  "
            f"{status}"
        )
        print(row)

    # Upgrade commands
    if upgradable:
        print()
        pip_cmd = " ".join(_detect_pip_command())
        for pkg in upgradable:
            print(f"\u2b06 {pkg['name']}:")
            if pkg["name"] == "argo-proxy":
                if pkg.get("has_stable_update"):
                    print("    stable:  argo-proxy update install")
                    print(f"      or:    {pip_cmd} install --upgrade argo-proxy")
                if pkg.get("has_pre_update"):
                    print("    pre:     argo-proxy update install --pre")
                    print(f"      or:    {pip_cmd} install --upgrade --pre argo-proxy")
                print(f"    Changelog: {CHANGELOG_URL}")
            else:
                print(f"    {pip_cmd} install --upgrade {pkg['name']}")
                changelog = _DEP_CHANGELOG_URLS.get(pkg["name"])
                if changelog:
                    print(f"    Changelog: {changelog}")
    else:
        print()
        print("All packages are up to date.")
        print(f"  Changelog: {CHANGELOG_URL}")


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
        print(f"Error: Unable to fetch {label} version from PyPI.", file=sys.stderr)
        sys.exit(1)

    try:
        if version_parse(target) <= version_parse(current):
            print(f"Already at v{current}, {label} is v{target}. Nothing to do.")
            return
    except Exception:
        pass

    pip_cmd = _detect_pip_command()
    cmd = [*pip_cmd, "install", "--upgrade"]
    if pre:
        cmd.append("--pre")
    cmd.append("argo-proxy")

    print(f"Upgrading argo-proxy: v{current} \u2192 v{target} ({label})")
    print(f"Running: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("Error: Update failed. See output above for details.", file=sys.stderr)
        sys.exit(1)

    print("Update complete. Restart argo-proxy to use the new version.")


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
