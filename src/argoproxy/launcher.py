"""Start the gateway against the Argo shims, with the tunnel already up.

This is the replacement for the original ``run_app.sh``: read the config,
make sure ``apps.inside.anl.gov`` is reachable, then hand over to
``llm-rosetta-gateway``.  The difference is that the proxy itself is not this
package any more — the gateway is — so this module renders a gateway config
from the Argo one and ``exec``s the gateway CLI.

Three rules shape it:

**It never prompts.**  The SSH master needs Duo MFA, and a launcher that can
block on a prompt is a launcher that hangs under systemd.  An absent master
is a failure that names the command to run, not something to wait on.  Only
``start`` is ever run: ``auth`` is the prompt, and it adds the forward itself.

**It writes the proxy where it belongs.**  The tunnel is per provider: the
gateway has a global ``--proxy`` / ``server.proxy``, and using either would
route every provider through the Argo tunnel.  The rendered config carries
``proxy`` on the Argo providers only.

**It imports nothing from llm-rosetta.**  The pieces it needs — a YAML
reader, the tunnel CLI, the gateway CLI — are a subprocess and a vendored
parser away, so the launcher keeps working while the rest of the package is
still being migrated.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from collections.abc import Sequence

__all__ = [
    "LauncherError",
    "LauncherSettings",
    "main",
    "render_gateway_config",
    "tunnel_state",
]

#: The console scripts this launcher drives.  Both may be overridden through
#: the environment, for a checkout that has not been installed yet.
DEFAULT_TUNNEL_COMMAND = "argo-tunnel"
DEFAULT_GATEWAY_COMMAND = "llm-rosetta-gateway"

#: The shim name each client format is served by.  A gateway provider declares
#: exactly one format; a client speaking another is converted through IR.  All
#: three Argo lanes exist because Argo's reasoning and tool handling differ per
#: dialect, and ``prefer_same_format`` then keeps a client on its own dialect.
PROVIDER_FORMATS: dict[str, str] = {
    "argo-chat": "argo--chat_completions",
    "argo-messages": "argo--messages",
    "argo-responses": "argo--open_responses",
}

#: The tunnel states in which a request can be served.
_USABLE_TUNNEL_STATES = frozenset({"forwarding"})


class LauncherError(Exception):
    """The launcher cannot start the gateway, and says what to do about it.

    Attributes:
        hint: A command the operator can run, or ``None``.
    """

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class Runner(Protocol):
    """Runs a command and returns ``(returncode, stdout, stderr)``."""

    def __call__(self, argv: Sequence[str]) -> tuple[int, str, str]:
        """Execute *argv* without a terminal attached."""


def run_command(argv: Sequence[str]) -> tuple[int, str, str]:
    """Execute *argv* with stdin closed.

    A launcher must not sit on a prompt, so stdin is ``DEVNULL``: a command
    that wants input fails rather than waiting for it.
    """
    try:
        done = subprocess.run(
            list(argv),
            check=False,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        return 127, "", f"not found: {exc}"
    return done.returncode, done.stdout or "", done.stderr or ""


def _tool(name: str, env_var: str) -> str:
    """The command to run for a tool, preferring an environment override.

    Args:
        name: The console script name.
        env_var: The variable that overrides it.

    Returns:
        The command string.

    Raises:
        LauncherError: Neither the override nor the console script exists.
    """
    override = os.environ.get(env_var, "").strip()
    if override:
        return override
    if shutil.which(name) is None:
        raise LauncherError(
            f"{name} is not on PATH",
            hint=(
                "pip install llm-rosetta-gateway llm-rosetta-shim-argo "
                "(argo-tunnel ships with the shim package)"
            ),
        )
    return name


@dataclass
class LauncherSettings:
    """Everything the rendered gateway config depends on.

    Attributes:
        host: Address the gateway binds.
        port: Port the gateway binds.
        user: The ANL account name, which is also the upstream credential.
        base_url: The Argo API base, without a trailing slash.
        models_url: Where the model list is read from.
        proxy_url: The SOCKS URL, or ``None`` when the host is already inside
            the network.
        data_dir: Where the gateway keeps its database, or ``None`` for its
            own default.
        shims_path: A local shim directory to add, for a host that cannot
            reach the preset archive.
        prefer_same_format: Keep a client on its own dialect when it can.
        config_path: Where the rendered config is written.
    """

    host: str = "0.0.0.0"
    port: int = 44497
    user: str = ""
    base_url: str = "https://apps.inside.anl.gov/argoapi"
    models_url: str = ""
    proxy_url: str | None = None
    data_dir: str | None = None
    shims_path: str | None = None
    prefer_same_format: bool = True
    config_path: str = ""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_argo_config(path: str | None) -> dict[str, Any]:
    """Read the Argo YAML config, or return an empty mapping.

    Args:
        path: An explicit path, or ``None`` to try the same locations the
            package has always tried.

    Returns:
        The parsed document.  A missing file is not an error: every setting
        has a flag and a default.

    Raises:
        LauncherError: A file exists but cannot be parsed.
    """
    from ._vendor import yaml

    candidates = [path] if path else ["config.yaml", "config.test.yaml"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            try:
                data = yaml.load(Path(candidate).read_text())
            except Exception as exc:  # noqa: BLE001 - any parse failure is fatal
                raise LauncherError(f"cannot parse {candidate}: {exc}") from exc
            return data if isinstance(data, dict) else {}
    return {}


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def settings_from(
    argo: dict[str, Any], args: argparse.Namespace, *, proxy_url: str | None
) -> LauncherSettings:
    """Merge the Argo YAML, the environment and the command line.

    Precedence is command line → environment → YAML → default, which is the
    order an operator expects when they override one value on one run.

    Args:
        argo: The parsed Argo config.
        args: The parsed command line.
        proxy_url: The tunnel URL, or ``None`` when no tunnel is used.

    Returns:
        The effective settings.

    Raises:
        LauncherError: The account name is missing, or the port is not a port.
    """
    env = os.environ

    def pick(flag: Any, env_name: str, yaml_key: str, default: Any) -> Any:
        if flag is not None:
            return flag
        if value := env.get(env_name, "").strip():
            return value
        if (value := argo.get(yaml_key)) not in (None, ""):
            return value
        return default

    host = str(pick(args.host, "HOST", "host", "0.0.0.0"))
    raw_port = pick(args.port, "PORT", "port", 44497)
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise LauncherError(f"port is not a number: {raw_port!r}") from exc

    user = str(pick(args.user, "ARGO_USER", "user", "")).strip()
    if not user:
        raise LauncherError(
            "no Argo account name",
            hint="set 'user' in config.yaml, or pass --user",
        )

    base_url = str(
        pick(
            args.base_url,
            "ARGO_BASE_URL",
            "argo_base_url",
            "https://apps.inside.anl.gov/argoapi",
        )
    ).rstrip("/")

    models_url = str(
        args.models_url
        or env.get("ARGO_MODELS_URL", "").strip()
        or f"{base_url}/v1/models"
    )

    data_dir = pick(args.data_dir, "DATA_DIR", "data_dir", None)

    return LauncherSettings(
        host=host,
        port=port,
        user=user,
        base_url=base_url,
        models_url=models_url,
        proxy_url=proxy_url,
        data_dir=str(data_dir) if data_dir else None,
        shims_path=args.shims_path,
        prefer_same_format=not args.no_prefer_same_format,
        config_path=args.gateway_config or "",
    )


# ---------------------------------------------------------------------------
# Model table
# ---------------------------------------------------------------------------


def fetch_models(
    settings: LauncherSettings, *, timeout: float = 20.0
) -> tuple[list[str], dict[str, str]]:
    """Read the upstream model list through the tunnel.

    Args:
        settings: The effective settings; ``models_url`` and ``proxy_url``
            decide where and how.
        timeout: Seconds for the whole request.

    Returns:
        ``(display_names, upstream_map)``, where the map holds only the names
        whose upstream id differs from the display name.

    Raises:
        LauncherError: The list could not be read.  Callers fall back to the
            configured defaults rather than starting with an empty table.
    """
    try:
        from llm_rosetta_gateway._vendor.httpclient import get
    except Exception as exc:  # noqa: BLE001 - an import failure is a fetch failure
        raise LauncherError(f"cannot reach the upstream model list: {exc}") from exc

    headers = {
        "Authorization": f"Bearer {settings.user}",
        "Accept": "application/json",
    }
    try:
        response = get(
            settings.models_url,
            headers=headers,
            timeout=timeout,
            proxy=settings.proxy_url,
        )
    except Exception as exc:  # noqa: BLE001 - a transport failure is a fetch failure
        raise LauncherError(f"cannot reach {settings.models_url}: {exc}") from exc

    status = getattr(response, "status_code", 0)
    if status != 200:
        raise LauncherError(
            f"{settings.models_url} answered HTTP {status}; "
            "the account may not be registered in Argo"
        )
    body = response.json()
    entries = body.get("data", body) if isinstance(body, dict) else body
    if not isinstance(entries, list):
        raise LauncherError(f"{settings.models_url} returned an unexpected shape")

    names, upstream = _model_list_transform()(entries)
    if not names:
        raise LauncherError(f"{settings.models_url} listed no models")
    return names, upstream


def _model_list_transform() -> Any:
    """The model-id rule, preferring the shim package's own implementation.

    Argo's ``/models`` names a human-readable ``id`` and a compact
    ``internal_id``; the display name is a slug of the former and the route
    carries the latter.  That rule belongs to the shim package, and this uses
    it when it is importable — but the launcher must keep working while the
    shim package is not installed (it needs a newer core than the current pin
    allows), so :func:`_slug_entries` mirrors it and a test asserts the two
    agree whenever both are available.
    """
    try:
        from llm_rosetta_shim_argo.providers.argo.model_utils import (
            model_list_transform,
        )
    except Exception:  # noqa: BLE001 - any import failure means "not installed"
        return _slug_entries
    return model_list_transform


def _slug_entries(raw_entries: list[dict]) -> tuple[list[str], dict[str, str]]:
    """Slug Argo's model entries.  Mirrors the shim package's transform."""
    import re

    names: list[str] = []
    upstream: dict[str, str] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        raw_id = entry.get("id", "")
        if not raw_id:
            continue
        internal_id = entry.get("internal_id")
        if internal_id:
            slug = re.sub(r"[^a-z0-9.]+", "-", str(raw_id).lower()).strip("-.")
            if not slug:
                continue
            display = f"argo:{slug}"
            upstream[display] = str(internal_id)
        else:
            display = str(raw_id)
        names.append(display)
    return names, upstream


def routes_for(
    names: Sequence[str], upstream: dict[str, str], settings: LauncherSettings
) -> dict[str, Any]:
    """Build the model table: every name routable to every Argo lane.

    Declaring all three lanes per model is what lets ``prefer_same_format`` do
    its job — a client that speaks Anthropic stays on the Anthropic shim when
    one of the candidates can serve it.

    Args:
        names: Display names, as the client will ask for them.
        upstream: Display name → upstream id, for the names that differ.
        settings: Supplies the provider names.

    Returns:
        The ``models`` mapping for the gateway config.
    """
    providers = list(PROVIDER_FORMATS)
    table: dict[str, Any] = {}
    for name in names:
        entry: dict[str, Any] = {
            "providers": [
                {"name": p, "upstream_model": upstream.get(name, name)}
                for p in providers
            ],
            "capabilities": ["text", "tools", "reasoning"],
        }
        table[name] = entry
    return table


# ---------------------------------------------------------------------------
# Config rendering
# ---------------------------------------------------------------------------


def render_gateway_config(
    settings: LauncherSettings,
    names: Sequence[str],
    upstream: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Render the gateway JSONC config for the Argo deployment.

    Args:
        settings: The effective settings.
        names: Model display names.
        upstream: Display name → upstream id.

    Returns:
        The config document, ready to be written as JSONC.
    """
    providers: dict[str, Any] = {}
    for provider_name, shim in PROVIDER_FORMATS.items():
        entry: dict[str, Any] = {
            "type": shim,
            "api_key": settings.user,
        }
        # The tunnel is one provider's route to the internet: putting it on
        # ``server.proxy`` would send every other provider there too.
        if settings.proxy_url:
            entry["proxy"] = settings.proxy_url
        providers[provider_name] = entry

    document: dict[str, Any] = {
        # The gateway stamps its own version on a document it migrates; this
        # one is generated against the current schema on every launch, so it
        # declares nothing and lets the loader decide.
        "providers": providers,
        "models": routes_for(names, upstream or {}, settings),
        "server": {
            "host": settings.host,
            "port": settings.port,
            # The Argo upstream validates the account itself, so the gateway
            # does not gate on its own key list.  A deployment that wants the
            # gate adds keys to its database and turns this off.
            "open_on_no_keys": True,
            "prefer_same_format": settings.prefer_same_format,
        },
        "shims": {"presets": ["argo"]},
    }
    if settings.shims_path:
        document["shims"] = {"paths": [settings.shims_path]}
    if settings.data_dir:
        document["server"]["data_dir"] = settings.data_dir
    return document


def write_gateway_config(document: dict[str, Any], path: str | Path) -> Path:
    """Write the rendered config as JSON, creating its directory.

    JSON rather than JSONC: this file is generated on every launch, so it
    carries no comments a human would want to keep, and ``json`` cannot
    produce a document the gateway's parser rejects.

    Args:
        document: The config to write.
        path: Destination.

    Returns:
        The path written.
    """
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(document, indent=2) + "\n")
    return destination


# ---------------------------------------------------------------------------
# Tunnel
# ---------------------------------------------------------------------------


def tunnel_state(tunnel_command: str, run: Runner = run_command) -> dict[str, Any]:
    """Ask the tunnel CLI for its state.

    Args:
        tunnel_command: The console script to call.
        run: How to run it.

    Returns:
        The parsed status object, or ``{"state": "absent"}`` when the CLI
        itself cannot run — a missing tunnel binary is an absent tunnel.
    """
    code, out, _err = run([tunnel_command, "status", "--json"])
    if code not in (0, 1):  # 1 is "not forwarding", which is still an answer
        return {"state": "absent"}
    try:
        payload = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"state": "absent"}
    return payload if isinstance(payload, dict) else {"state": "absent"}


def ensure_tunnel(
    tunnel_command: str,
    *,
    run: Runner = run_command,
    start: bool = True,
) -> str | None:
    """Bring the tunnel to ``forwarding``, or explain why it cannot be.

    ``start`` is the only repair this function performs.  ``auth`` is never
    run: it is the MFA prompt, and a launcher that can block on it is a
    launcher that hangs.

    Args:
        tunnel_command: The console script to call.
        run: How to run it.
        start: Whether to try starting a forward on an authenticated master.

    Returns:
        The proxy URL to put in the config, or ``None`` when no tunnel is
        needed or none is available.

    Raises:
        LauncherError: The tunnel is absent or wedged and cannot be repaired
            without a human.
    """
    state = tunnel_state(tunnel_command, run)
    current = state.get("state", "absent")
    if current in _USABLE_TUNNEL_STATES:
        return str(state.get("proxy_url") or "")
    if start and current == "idle":
        code, _out, err = run([tunnel_command, "start"])
        if code == 0:
            state = tunnel_state(tunnel_command, run)
            if state.get("state") in _USABLE_TUNNEL_STATES:
                return str(state.get("proxy_url") or "")
        else:
            err = err.strip() or "ssh failed"
            raise LauncherError(f"the tunnel did not start: {err}") from None
    if current == "wedged":
        # Something other than this tool's forward holds the port; ``auth``
        # refuses that state too, and says which process to stop.
        raise LauncherError(
            "the SSH master does not answer, or the SOCKS port is held by "
            "another process",
            hint=f"{tunnel_command} status --json, then {tunnel_command} auth",
        )
    raise LauncherError(
        "no authenticated SSH master",
        hint=f"{tunnel_command} auth",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argo-proxy-launch",
        description=(
            "Render a gateway config for Argo and start llm-rosetta-gateway "
            "behind the Argo SSH tunnel."
        ),
    )
    parser.add_argument("config", nargs="?", default=None, help="path to config.yaml")
    parser.add_argument("--host", default=None, help="bind address")
    parser.add_argument("--port", type=int, default=None, help="bind port")
    parser.add_argument("--user", default=None, help="ANL account name")
    parser.add_argument("--base-url", default=None, help="Argo API base URL")
    parser.add_argument("--models-url", default=None, help="model listing URL")
    parser.add_argument("--data-dir", default=None, help="gateway data directory")
    parser.add_argument(
        "--gateway-config",
        default=None,
        help="where to write the rendered config (default: beside the data dir)",
    )
    parser.add_argument(
        "--shims-path",
        default=None,
        help="load the Argo shims from a local directory instead of the preset",
    )
    parser.add_argument(
        "--no-tunnel",
        action="store_true",
        help="the host is already inside the network; do not use a tunnel",
    )
    parser.add_argument(
        "--no-prefer-same-format",
        action="store_true",
        help="let the gateway convert rather than prefer the client's own dialect",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="print the rendered config and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="do everything but exec the gateway",
    )
    return parser


def _default_config_path(settings: LauncherSettings) -> str:
    """Where the rendered config goes when no path is given."""
    if settings.data_dir:
        return str(Path(settings.data_dir).expanduser() / "gateway.json")
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return str(base / "argo-proxy" / "gateway.json")


def main(argv: Sequence[str] | None = None) -> int:
    """Render the config, ensure the tunnel, and exec the gateway.

    Args:
        argv: Arguments without the program name.

    Returns:
        A process exit code.  A successful run does not return: the gateway
        CLI replaces the process, so signals reach it directly.
    """
    args = _build_parser().parse_args(argv)

    try:
        tunnel_command = (
            "" if args.no_tunnel else _tool(DEFAULT_TUNNEL_COMMAND, "ARGO_PROXY_TUNNEL")
        )
        gateway_command = _tool(DEFAULT_GATEWAY_COMMAND, "ARGO_PROXY_GATEWAY")

        proxy_url = None if args.no_tunnel else ensure_tunnel(tunnel_command)
        argo = load_argo_config(args.config)
        settings = settings_from(argo, args, proxy_url=proxy_url)

        try:
            names, upstream = fetch_models(settings)
        except LauncherError as exc:
            fallback = str(argo.get("default_chat_model") or "argo:gpt-5.4-nano")
            print(f"warning: {exc}; routing only {fallback!r}", file=sys.stderr)
            names, upstream = [fallback], {}

        document = render_gateway_config(settings, names, upstream)
        destination = write_gateway_config(
            document, settings.config_path or _default_config_path(settings)
        )
    except LauncherError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if exc.hint:
            print(f"hint: {exc.hint}", file=sys.stderr)
        return 1

    print(
        f"argo-proxy: {len(names)} models, "
        f"{'tunnel ' + str(proxy_url) if proxy_url else 'direct'}, "
        f"config {destination}",
        file=sys.stderr,
    )
    if args.print_config:
        print(json.dumps(document, indent=2))
        return 0

    gateway_argv = [
        gateway_command,
        "--config",
        str(destination),
        "--host",
        settings.host,
        "--port",
        str(settings.port),
    ]
    if args.dry_run:
        print(" ".join(gateway_argv))
        return 0

    # ``exec`` rather than ``subprocess``: the gateway must own the process so
    # that a stop signal, or a unit-file restart, reaches it and not a parent
    # that would leave it running.
    os.execvp(gateway_argv[0], gateway_argv)
    return 0  # pragma: no cover - execvp does not return


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
