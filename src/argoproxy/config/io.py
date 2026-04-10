"""Configuration file I/O: load, save, migrate, and environment overrides."""

import difflib
import json
import os
from pathlib import Path
from typing import Any, Literal, Union, overload

import yaml

from ..utils.logging import log_error, log_info, log_warning
from ..utils.misc import str_to_bool
from .model import ArgoConfig, _show

PATHS_TO_TRY = [
    "./config.yaml",
    os.path.expanduser("~/.config/argoproxy/config.yaml"),
    os.path.expanduser("~/.argoproxy/config.yaml"),
]

# Directories to scan for config file variants (e.g. config.ozan.yaml, config-public.yaml)
CONFIG_SEARCH_DIRS = [
    ".",
    os.path.expanduser("~/.config/argoproxy"),
    os.path.expanduser("~/.argoproxy"),
]

CONFIG_GLOB_PATTERNS = ["config*.yaml", "config*.yml"]


def _format_config_yaml(data: dict) -> str:
    """Format config dict as grouped YAML with section comments."""
    # Define logical groups with optional section headers
    groups: list[tuple[str, list[str]]] = [
        (
            "# Core settings",
            ["config_version", "user", "host", "port", "verbose", "log_to_file"],
        ),
        (
            "# Upstream",
            [
                "argo_base_url",
                "native_openai_base_url",
                "native_anthropic_base_url",
                "use_legacy_argo",
                "anthropic_stream_mode",
            ],
        ),
        (
            "# Network & validation",
            ["connection_test_timeout", "skip_url_validation", "resolve_overrides"],
        ),
        (
            "# Image processing",
            [
                "enable_payload_control",
                "max_payload_size",
                "image_timeout",
                "concurrent_downloads",
            ],
        ),
    ]

    lines: list[str] = []
    written_keys: set[str] = set()

    for header, keys in groups:
        section_lines: list[str] = []
        for key in keys:
            if key in data:
                section_lines.append(
                    yaml.dump({key: data[key]}, default_flow_style=False).strip()
                )
                written_keys.add(key)
        if section_lines:
            if lines:
                lines.append("")  # blank line between groups
            lines.append(header)
            lines.extend(section_lines)

    # Append any remaining keys not in the groups
    remaining = {k: v for k, v in sorted(data.items()) if k not in written_keys}
    if remaining:
        if lines:
            lines.append("")
        lines.append("# Other")
        lines.append(yaml.dump(remaining, default_flow_style=False).strip())

    lines.append("")  # trailing newline
    return "\n".join(lines)


def save_config(
    config_data: ArgoConfig, config_path: Union[str, Path] | None = None
) -> str:
    """Save configuration to YAML file.

    Args:
        config_data: The ArgoConfig instance to save.
        config_path: Optional path to save the config. If not provided,
            will use default path in user's config directory.

    Returns:
        The path where the config was saved.

    Raises:
        OSError: If there are issues creating directories or writing the file.
    """
    if config_path is None:
        home_dir = os.getenv("HOME") or os.path.expanduser("~")
        config_path = os.path.join(home_dir, ".config", "argoproxy", "config.yaml")

    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, "w") as f:
        f.write(_format_config_yaml(config_data.to_persistent_dict()))

    return str(config_path)


def _apply_env_overrides(config_data: ArgoConfig) -> ArgoConfig:
    """Apply environment variable overrides to the config."""
    if env_port := os.getenv("PORT"):
        config_data.port = int(env_port)

    if env_verbose := os.getenv("VERBOSE"):
        config_data.verbose = str_to_bool(env_verbose)

    if env_real_stream := os.getenv("REAL_STREAM"):
        config_data._real_stream = str_to_bool(env_real_stream)

    if env_tool_prompt := os.getenv("TOOL_PROMPT"):
        config_data._tool_prompt = str_to_bool(env_tool_prompt)

    # Deprecated: USE_NATIVE_OPENAI and USE_NATIVE_ANTHROPIC are ignored in v3.0.0
    # (native endpoints are now always used via universal dispatch)
    if os.getenv("USE_NATIVE_OPENAI"):
        log_warning(
            "USE_NATIVE_OPENAI is deprecated in v3.0.0 and will be ignored. "
            "Native endpoints are now used by default via universal dispatch.",
            context="config",
        )
    if os.getenv("USE_NATIVE_ANTHROPIC"):
        log_warning(
            "USE_NATIVE_ANTHROPIC is deprecated in v3.0.0 and will be ignored. "
            "Native endpoints are now used by default via universal dispatch.",
            context="config",
        )
    # Deprecated: PROVIDER_TOOL_FORMAT is handled by llm-rosetta in v3.0.0
    if os.getenv("PROVIDER_TOOL_FORMAT"):
        log_warning(
            "PROVIDER_TOOL_FORMAT is deprecated in v3.0.0 and will be ignored. "
            "Format conversion is now handled by llm-rosetta.",
            context="config",
        )

    if env_use_legacy_argo := os.getenv("USE_LEGACY_ARGO"):
        config_data._use_legacy_argo = str_to_bool(env_use_legacy_argo)

    if env_enable_leaked_tool_fix := os.getenv("ENABLE_LEAKED_TOOL_FIX"):
        config_data._enable_leaked_tool_fix = str_to_bool(env_enable_leaked_tool_fix)

    if env_dev_mode := os.getenv("DEV_MODE"):
        config_data._dev_mode = str_to_bool(env_dev_mode)

    if env_argo_base_url := os.getenv("ARGO_BASE_URL"):
        config_data._argo_base_url = env_argo_base_url

    if env_skip_url_validation := os.getenv("SKIP_URL_VALIDATION"):
        config_data._skip_url_validation = str_to_bool(env_skip_url_validation)

    if env_anthropic_stream_mode := os.getenv("ANTHROPIC_STREAM_MODE"):
        mode = env_anthropic_stream_mode.lower().strip()
        valid_modes = ("force", "retry", "passthrough")
        if mode in valid_modes:
            config_data._anthropic_stream_mode = mode
        else:
            log_warning(
                f"Invalid ANTHROPIC_STREAM_MODE '{env_anthropic_stream_mode}', "
                f"expected one of {valid_modes}. Using default 'force'.",
                context="config",
            )

    if env_force_conversion := os.getenv("FORCE_CONVERSION"):
        config_data._force_conversion = str_to_bool(env_force_conversion)

    return config_data


def _infer_base_url(config_dict: dict) -> str:
    """Infer ``argo_base_url`` from individual endpoint URLs.

    Strips known path suffixes from legacy URL fields to recover the base.
    Priority: ``argo_url`` > ``argo_stream_url`` > ``argo_embedding_url``.

    Args:
        config_dict: Raw config dictionary.

    Returns:
        Inferred base URL, or empty string if none could be determined.
    """
    url_suffixes = [
        ("argo_url", "/api/v1/resource/chat/"),
        ("argo_stream_url", "/api/v1/resource/streamchat/"),
        ("argo_embedding_url", "/api/v1/resource/embed/"),
    ]
    for field, suffix in url_suffixes:
        url = config_dict.get(field, "")
        if not url:
            continue
        url = url.rstrip("/") + "/"  # normalize trailing slash
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return ""


def _migrate_config(config_dict: dict) -> dict:
    """Apply config migrations for backward compatibility.

    Normalizes v1/v2 configs to v3 in memory: infers ``argo_base_url``
    from individual URL fields when missing, bumps ``config_version``
    to ``"3"``, and removes deprecated keys.

    Args:
        config_dict: The raw config dictionary loaded from YAML.

    Returns:
        The migrated config dictionary.
    """
    version = config_dict.get("config_version", "")

    if not version:
        log_info(
            "Config file has no 'config_version' field. "
            "Run 'argo-proxy config migrate' to update the file to v3 format.",
            context="config",
        )

    # Infer argo_base_url from individual endpoint URLs if not set
    if not config_dict.get("argo_base_url"):
        inferred = _infer_base_url(config_dict)
        if inferred:
            config_dict["argo_base_url"] = inferred
            log_info(
                f"Inferred argo_base_url from endpoint URLs: {inferred}",
                context="config",
            )

    # Bump version to v3
    if not version or version < "3":
        config_dict["config_version"] = "3"

    # Remove deprecated native mode toggles
    deprecated_keys = [
        "use_native_openai",
        "use_native_anthropic",
        "provider_tool_format",
    ]
    found = [k for k in deprecated_keys if k in config_dict]
    if found:
        log_warning(
            f"Config keys {found} are deprecated in v3.0.0 and will be ignored. "
            "Native endpoints are now used by default via universal dispatch.",
            context="config",
        )
        for k in found:
            config_dict.pop(k, None)

    return config_dict


@overload
def load_config(
    optional_path: Union[str, Path] | None = None,
    *,
    env_override: bool = True,
    as_is: Literal[False] = False,
    verbose: bool = True,
) -> tuple[ArgoConfig | None, Path | None]: ...
@overload
def load_config(
    optional_path: Union[str, Path] | None = None,
    *,
    env_override: bool = True,
    as_is: Literal[True],
    verbose: bool = True,
) -> tuple[dict[str, Any] | None, Path | None]: ...


def load_config(
    optional_path: Union[str, Path] | None = None,
    *,
    env_override: bool = True,
    as_is: bool = False,
    verbose: bool = True,
) -> tuple[Union[ArgoConfig, dict[str, Any]] | None, Path | None]:
    """Load configuration from file with optional environment variable overrides.

    Returns both the loaded config and the actual path it was loaded from.
    Assumes configuration is already validated.

    Args:
        optional_path: Optional path to a specific configuration file to load.
            If not provided, will attempt to load from default locations
            defined in PATHS_TO_TRY.
        env_override: If True, environment variables will override the
            configuration file settings. Defaults to True.
        as_is: If True, will return the configuration as-is without
            applying any overrides. Defaults to False.
        verbose: If True, will print verbose output. Defaults to True.

    Returns:
        Tuple of (loaded_config, actual_path) if successful, or
        (None, None) if no valid configuration file could be loaded.
    """
    paths_to_try = [str(optional_path)] if optional_path else [] + PATHS_TO_TRY

    for path in paths_to_try:
        if path and os.path.exists(path):
            with open(path) as f:
                try:
                    config_dict = yaml.safe_load(f)
                    actual_path = Path(path).absolute()

                    if as_is:
                        return config_dict, actual_path

                    config_dict = _migrate_config(config_dict)
                    config_data = ArgoConfig.from_dict(config_dict)
                    if env_override:
                        config_data = _apply_env_overrides(config_data)

                    if verbose:
                        log_info(
                            f"Loaded configuration from {actual_path}",
                            context="config",
                        )

                    return config_data, actual_path

                except (yaml.YAMLError, AssertionError) as e:
                    log_warning(
                        f"Error loading config at {path}: {e}", context="config"
                    )
                    continue

    return None, None


def validate_config(
    optional_path: str | None = None, show_config: bool = False
) -> ArgoConfig:
    """Validate configuration with user interaction if needed."""
    from .interactive import create_config, _get_yes_no_input
    from .validation import validate_config_fields

    config_data, actual_path = load_config(optional_path)

    if not config_data:
        log_error("No valid configuration found.", context="config")
        user_decision = _get_yes_no_input(
            "Would you like to create it from config.sample.yaml? [Y/n]: "
        )
        if user_decision:
            config_data = create_config(config_path=optional_path)
            # Re-load to get the actual saved path
            _, actual_path = load_config(optional_path, verbose=False)
            show_config = True
        else:
            log_warning(
                "User aborted configuration creation. Exiting...", context="config"
            )
            exit(1)

    # Config may change here. We need to persist
    file_changed = validate_config_fields(config_data)
    if file_changed:
        config_original, _ = load_config(
            actual_path, env_override=False, as_is=True, verbose=False
        )
        if not config_original:
            raise ValueError("Failed to load original configuration for comparison.")

        # Show ndiff between original and current configuration
        original_str = json.dumps(config_original, indent=4, sort_keys=True)
        current_str = str(config_data)
        diff = difflib.unified_diff(original_str.splitlines(), current_str.splitlines())
        _show("\n" + "\n".join(diff), "Configuration diff (- original, + current):")

        user_decision = _get_yes_no_input(
            "Do you want to save the changes to the configuration file? [y/N]: ",
            default_choice="n",
        )
        if user_decision:
            save_config(config_data, actual_path)

    if show_config:
        config_data.show()

    return config_data
