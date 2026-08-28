"""ConfigIO adapter that bridges ArgoConfig + ModelRegistry into the gateway admin panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models.registry import ModelRegistry
    from .model import ArgoConfig


class ArgoConfigIO:
    """ConfigIO implementation that injects runtime providers/models.

    The gateway admin panel reads config via ``config_io.load_raw()`` and
    writes via ``config_io.save()``.  argo-proxy's YAML has no ``providers``
    or ``models`` sections — those are built at runtime from the ARGO
    upstream.  This adapter injects them on read and strips them on write.

    References are held (not copies), so model-registry refreshes are
    reflected immediately.

    NOTE: This class does NOT inherit from
    :class:`llm_rosetta.gateway.config.JsoncConfigIO`, so the gateway's
    automatic config migration framework is not applied.  argo-proxy
    manages its own YAML config format separately.
    """

    def __init__(self, config: ArgoConfig, registry: ModelRegistry) -> None:
        self._config = config
        self._registry = registry

    def _inject_runtime_state(self, data: dict[str, Any]) -> dict[str, Any]:
        from ..bridge import _build_models, _build_providers

        data["providers"] = _build_providers(self._config)
        data["models"] = _build_models(self._registry)
        data.setdefault("server", {}).update(
            {"host": self._config.host, "port": self._config.port}
        )
        if self._config.socket:
            data["server"]["socket"] = self._config.socket
        data.setdefault("debug", {}).update(
            {
                "verbose": self._config.verbose,
                "log_bodies": False,
                "error_dumps": self._config.dump_requests,
            }
        )
        return data

    def load_raw(self, path: str) -> dict[str, Any]:
        from .io import load_config

        raw, _ = load_config(path, as_is=True, verbose=False)
        return self._inject_runtime_state(raw or {})

    # Gateway uses load_raw for admin API reads and load for hot-reload
    # (_reload_gateway_config). In argo-proxy both behave the same.
    load = load_raw

    def save(self, path: str, data: dict[str, Any]) -> None:
        data.pop("providers", None)
        data.pop("models", None)

        # Map gateway-format nested keys back to flat ARGO keys
        if server := data.pop("server", None):
            if "host" in server:
                data["host"] = server["host"]
            if "port" in server:
                data["port"] = server["port"]
            if "socket" in server:
                data["socket"] = server["socket"]
        if debug := data.pop("debug", None):
            if "verbose" in debug:
                data["verbose"] = debug["verbose"]

        from .io import _format_config_yaml

        with open(path, "w") as f:
            f.write(_format_config_yaml(data))
