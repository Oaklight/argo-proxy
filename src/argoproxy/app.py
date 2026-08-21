"""argo-proxy application — thin wrapper around llm-rosetta gateway.

Builds an HTTP application using the gateway's vendored httpserver and
proxy pipeline while layering ARGO-specific auth, model resolution,
and streaming logic on top.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
import uuid
from typing import Any

from llm_rosetta._vendor.httpserver import (
    App,
    JSONResponse,
    Response,
    StreamingResponse,
)
from llm_rosetta.auto_detect import ProviderType
from llm_rosetta.gateway.proxy import (
    ProviderMetadataStore,
    close_resources,
    detect_stream_request,
    error_response_for_source,
    extract_model,
    handle_non_streaming,
    handle_streaming,
)
from llm_rosetta.gateway.transport.http import HttpTransport

from .__init__ import __version__
from .auth import (
    argo_auth_error_response,
    check_response_for_argo_warning,
    contains_argo_auth_warning,
    create_argo_auth_hook,
    should_use_username_passthrough,
)
from .bridge import build_gateway_config, rebuild_gateway_models
from .config import load_config
from .models import ModelRegistry
from .transport import ArgoAuthWarning, ArgoTransport
from .utils.logging import log_debug, log_error, log_info, log_warning
from .utils.misc import build_user_agent

logger = logging.getLogger("argo-proxy")

def _load_admin_custom_head() -> str:
    """Load admin panel customization from static resource files."""
    from pathlib import Path

    static_dir = Path(__file__).parent / "static"
    parts: list[str] = []
    css_path = static_dir / "admin_custom.css"
    if css_path.exists():
        parts.append(f"<style>{css_path.read_text()}</style>")
    js_path = static_dir / "admin_custom.js"
    if js_path.exists():
        parts.append(f"<script>{js_path.read_text()}</script>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# App state helpers
# ---------------------------------------------------------------------------


def _get_config(app: App) -> Any:
    return app.argo_config  # type: ignore[attr-defined]


def _get_registry(app: App) -> ModelRegistry:
    return app.model_registry  # type: ignore[attr-defined]


def _get_gateway_config(app: App) -> Any:
    return app.gateway_config  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Telemetry — record metrics + request log for the admin dashboard
# ---------------------------------------------------------------------------


def _record_telemetry(
    request: Any,
    *,
    model: str,
    source_provider: ProviderType,
    target_provider: ProviderType,
    provider_name: str,
    is_stream: bool,
    status_code: int,
    duration_ms: float,
    error_detail: str | None,
    profile: dict[str, Any] | None = None,
) -> None:
    metrics = getattr(request.app, "metrics", None)
    if is_stream and metrics:
        metrics.active_streams -= 1
    if metrics:
        metrics.record_request(
            model=model,
            source=source_provider,
            target=target_provider,
            status_code=status_code,
            duration_ms=duration_ms,
            is_stream=is_stream,
            provider_name=provider_name,
            error_detail=error_detail,
        )

    request_log = getattr(request.app, "request_log", None)
    if request_log is not None:
        from llm_rosetta.observability import RequestLogEntry

        entry = RequestLogEntry.create(
            model=model,
            source_provider=source_provider,
            target_provider=target_provider,
            target_provider_name=provider_name,
            is_stream=is_stream,
            status_code=status_code,
            duration_ms=duration_ms,
            error_detail=error_detail,
            client_ip=_extract_client_ip(request),
            profile=profile,
        )
        request_log.add(entry)


def _extract_client_ip(request: Any) -> str | None:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    addr = getattr(request, "client_addr", None)
    if addr:
        return str(addr[0])
    return None


# ---------------------------------------------------------------------------
# Proxy handler — ARGO-specific model resolution + gateway pipeline
# ---------------------------------------------------------------------------


async def _argo_proxy_handler(
    request: Any,
    source_provider: ProviderType,
    model_override: str | None = None,
    force_stream: bool = False,
) -> Response | StreamingResponse:
    """Core proxy handler with ARGO model resolution and stream-mode logic."""
    config = _get_config(request.app)
    registry = _get_registry(request.app)
    gateway_config = _get_gateway_config(request.app)

    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

    try:
        body: dict[str, Any] = request.json()
    except Exception:
        resp = error_response_for_source(source_provider, 400, "Invalid JSON body")
        resp.headers["x-request-id"] = request_id
        return resp

    model = model_override or extract_model(source_provider, body)
    if not model:
        resp = error_response_for_source(
            source_provider, 400, "Missing 'model' in request body"
        )
        resp.headers["x-request-id"] = request_id
        return resp

    if model_override and "model" not in body:
        body["model"] = model_override

    # ARGO model resolution (fuzzy matching, argo: prefix, etc.)
    as_is = source_provider == "anthropic"
    resolved = registry.resolve_model_name(model, "chat", as_is=as_is)
    target_provider, _ = registry.resolve_model_target(resolved, config)

    gateway_model = _find_gateway_model(gateway_config, model, resolved, registry)
    if not gateway_model:
        configured = ", ".join(sorted(gateway_config.models.keys()))
        resp = error_response_for_source(
            source_provider,
            404,
            f"Unknown model: '{model}'. Configured models: {configured}",
        )
        resp.headers["x-request-id"] = request_id
        return resp

    try:
        route, provider_info = gateway_config.resolve(source_provider, gateway_model)
    except KeyError:
        resp = error_response_for_source(
            source_provider, 404, f"Unknown model: '{model}'"
        )
        resp.headers["x-request-id"] = request_id
        return resp

    if route.upstream_model:
        body["model"] = route.upstream_model

    # Username passthrough
    if should_use_username_passthrough():
        api_key = _extract_api_key_from_headers(request)
        if api_key:
            body["user"] = api_key
    else:
        body["user"] = config.user

    # Anthropic metadata.user_id injection
    if target_provider == "anthropic":
        user = body.get("user", config.user)
        body.setdefault("metadata", {})
        if isinstance(body["metadata"], dict):
            body["metadata"]["user_id"] = user

    # Determine streaming with anthropic_stream_mode
    is_stream = force_stream or detect_stream_request(source_provider, body)

    if not is_stream and target_provider == "anthropic":
        mode = config.anthropic_stream_mode
        if mode == "force":
            is_stream = True

    model_label = (
        f"{model} (upstream={route.upstream_model})" if route.upstream_model else model
    )
    logger.info(
        "[%s] %s -> %s | model=%s stream=%s",
        request_id,
        source_provider,
        route.target_provider,
        model_label,
        is_stream,
    )

    store: ProviderMetadataStore = request.app.metadata_store  # type: ignore[attr-defined]
    transport: ArgoTransport = request.app.transport  # type: ignore[attr-defined]

    extra_headers: dict[str, str] = {"x-request-id": request_id}
    ua = build_user_agent(request.headers.get("user-agent"))
    if ua:
        extra_headers["User-Agent"] = ua

    if is_stream:
        metrics = getattr(request.app, "metrics", None)
        if metrics:
            metrics.active_streams += 1

    t0 = time.monotonic()
    status_code = 500
    error_detail: str | None = None
    profile: dict[str, Any] | None = None
    capture_state = getattr(request.app, "capture_state", None)
    persistence = getattr(request.app, "persistence", None)
    request_log = getattr(request.app, "request_log", None)

    try:
        if is_stream:
            pre_entry_id = uuid.uuid4().hex
            response, profile = await handle_streaming(
                route,
                provider_info,
                body,
                transport=transport,
                metadata_store=store,
                extra_headers=extra_headers,
                capture_state=capture_state,
                entry_id=pre_entry_id,
                request_log=request_log,
            )
        elif (
            not is_stream
            and target_provider == "anthropic"
            and config.anthropic_stream_mode == "retry"
        ):
            pre_entry_id = None
            response, profile = await _handle_with_retry(
                route,
                provider_info,
                body,
                transport=transport,
                metadata_store=store,
                extra_headers=extra_headers,
                capture_state=capture_state,
                persistence=persistence,
            )
        else:
            pre_entry_id = None
            response, profile = await handle_non_streaming(
                route,
                provider_info,
                body,
                transport=transport,
                metadata_store=store,
                extra_headers=extra_headers,
                capture_state=capture_state,
                persistence=persistence,
            )

        status_code = response.status_code

        # Check for ARGO auth warning in non-streaming responses
        if isinstance(response, Response) and hasattr(response, "body"):
            try:
                resp_text = response.body.decode("utf-8", errors="replace")
                if contains_argo_auth_warning(resp_text):
                    status_code = 403
                    error_detail = "ARGO authentication warning"
                    return argo_auth_error_response(source_provider)
            except Exception:
                pass

        if status_code >= 400 and hasattr(response, "body"):
            error_detail = response.body.decode("utf-8", errors="replace")

        response.headers["x-request-id"] = request_id
        return response

    except ArgoAuthWarning:
        status_code = 403
        error_detail = "ARGO authentication warning"
        return argo_auth_error_response(source_provider)
    except Exception as exc:
        error_detail = str(exc)
        logger.exception("[%s] Proxy error", request_id)
        status_code = 502
        resp = error_response_for_source(source_provider, 502, "Upstream error")
        resp.headers["x-request-id"] = request_id
        return resp
    finally:
        duration_ms = (time.monotonic() - t0) * 1000
        _record_telemetry(
            request,
            model=model,
            source_provider=source_provider,
            target_provider=route.target_provider,
            provider_name=route.provider_name,
            is_stream=is_stream,
            status_code=status_code,
            duration_ms=duration_ms,
            error_detail=error_detail,
            profile=profile,
        )


async def _handle_with_retry(
    route: Any,
    provider_info: Any,
    body: dict[str, Any],
    *,
    transport: Any,
    metadata_store: Any,
    extra_headers: dict[str, str] | None = None,
    capture_state: Any | None = None,
    persistence: Any | None = None,
) -> tuple[Response | StreamingResponse, dict[str, Any]]:
    """Try non-streaming, fall back to streaming on Anthropic bounce-back."""
    response, profile = await handle_non_streaming(
        route,
        provider_info,
        body,
        transport=transport,
        metadata_store=metadata_store,
        extra_headers=extra_headers,
        capture_state=capture_state,
        persistence=persistence,
    )

    if response.status_code != 500 or not hasattr(response, "body"):
        return response, profile

    error_text = response.body.decode("utf-8", errors="replace")
    if "streaming is required" not in error_text.lower():
        return response, profile

    log_info(
        "Anthropic returned 'streaming required', retrying with forced streaming",
        context="dispatch",
    )
    return await handle_streaming(
        route,
        provider_info,
        body,
        transport=transport,
        metadata_store=metadata_store,
        extra_headers=extra_headers,
        capture_state=capture_state,
    )


def _find_gateway_model(
    gateway_config: Any,
    client_model: str,
    resolved_model: str,
    registry: ModelRegistry,
) -> str | None:
    """Find the gateway config model key matching the client's request."""
    if client_model in gateway_config.models:
        return client_model
    if resolved_model in gateway_config.models:
        return resolved_model

    for alias, model_id in registry.available_models.items():
        if model_id == resolved_model and alias in gateway_config.models:
            return alias

    return None


def _extract_api_key_from_headers(request: Any) -> str | None:
    headers = request.headers
    for name in ("authorization", "x-api-key", "api-key", "x-goog-api-key"):
        value = headers.get(name, "")
        if value:
            if value.lower().startswith("bearer "):
                return value[7:].strip()
            return value.strip()
    params = request.query_params
    if "key" in params:
        return params["key"][0]
    return None


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


async def handle_openai_chat(request: Any) -> Response | StreamingResponse:
    log_info("/v1/chat/completions", context="app")
    return await _argo_proxy_handler(request, source_provider="openai_chat")


async def handle_openai_responses(request: Any) -> Response | StreamingResponse:
    log_info("/v1/responses", context="app")
    return await _argo_proxy_handler(request, source_provider="openai_responses")


async def handle_anthropic_messages(request: Any) -> Response | StreamingResponse:
    log_info("/v1/messages", context="app")
    return await _argo_proxy_handler(request, source_provider="anthropic")


async def handle_google_genai(
    request: Any, model_path: str = ""
) -> Response | StreamingResponse:
    log_info(f"/v1beta/models/{model_path}", context="app")

    if model_path.endswith(":streamGenerateContent"):
        model = model_path.removesuffix(":streamGenerateContent")
        return await _argo_proxy_handler(
            request,
            source_provider="google",
            model_override=model,
            force_stream=True,
        )
    elif model_path.endswith(":generateContent"):
        model = model_path.removesuffix(":generateContent")
        return await _argo_proxy_handler(
            request,
            source_provider="google",
            model_override=model,
        )
    else:
        return JSONResponse(
            {"error": {"code": 400, "message": f"Unknown method in: {model_path}"}},
            status_code=400,
        )


async def handle_embeddings(request: Any) -> Response:
    log_info("/v1/embeddings", context="app")
    config = _get_config(request.app)
    registry = _get_registry(request.app)
    gateway_config = _get_gateway_config(request.app)

    try:
        body: dict[str, Any] = request.json()
    except Exception:
        return JSONResponse(
            {
                "error": {
                    "message": "Invalid JSON body",
                    "type": "invalid_request_error",
                }
            },
            status_code=400,
        )

    model = body.get("model", "")
    resolved = registry.resolve_model_name(model, model_type="embed")
    body["model"] = resolved

    if should_use_username_passthrough():
        api_key = _extract_api_key_from_headers(request)
        if api_key:
            body["user"] = api_key
    else:
        body["user"] = config.user

    provider_info = gateway_config.providers.get("argo-openai")
    if not provider_info:
        return JSONResponse(
            {"error": {"message": "No OpenAI provider configured"}},
            status_code=500,
        )

    transport: ArgoTransport = request.app.transport  # type: ignore[attr-defined]
    url = f"{config.native_openai_base_url}/embeddings"

    try:
        response = await transport.send(
            provider_info,
            url,
            body,
            extra_headers={
                "User-Agent": build_user_agent(request.headers.get("user-agent"))
            },
        )
    except ArgoAuthWarning:
        return argo_auth_error_response("openai_chat")
    except Exception:
        logger.exception("Embeddings upstream error")
        return JSONResponse(
            {"error": {"message": "Upstream error", "type": "server_error"}},
            status_code=502,
        )

    if response.is_error:
        error_text = response.error_text
        if contains_argo_auth_warning(error_text):
            return argo_auth_error_response("openai_chat")
        return Response(
            body=response.raw_content,
            status_code=response.status_code,
            content_type="application/json",
        )

    if response.body and check_response_for_argo_warning(response.body, "openai"):
        return argo_auth_error_response("openai_chat")

    return JSONResponse(response.body, status_code=response.status_code)


async def handle_list_models(request: Any) -> Response:
    log_info("/v1/models", context="app")
    registry = _get_registry(request.app)
    return JSONResponse(registry.as_openai_list())


async def handle_refresh_models(request: Any) -> Response:
    log_info("/refresh", context="app")
    registry = _get_registry(request.app)
    gateway_config = _get_gateway_config(request.app)

    old_stats = registry.get_model_stats()
    await registry.refresh_availability()
    rebuild_gateway_models(gateway_config, registry)
    new_stats = registry.get_model_stats()

    return JSONResponse(
        {
            "status": "refreshed",
            "before": {
                "unique_models": old_stats["unique_models"],
                "total_aliases": old_stats["total_aliases"],
            },
            "after": {
                "unique_models": new_stats["unique_models"],
                "total_aliases": new_stats["total_aliases"],
            },
        }
    )


async def handle_root(request: Any) -> Response:
    return JSONResponse(
        {
            "message": (
                "Welcome to the Argo-Proxy API! "
                "Documentation is available at "
                "https://argo-proxy.readthedocs.io/en/latest/"
            )
        }
    )


async def handle_v1(request: Any) -> Response:
    html = (
        "<html><head><title>404 Not Found</title></head><body>"
        "<center><h1>404 Not Found</h1></center>"
        "<hr><center>argo-proxy</center></body></html>"
    )
    return Response(body=html.encode(), status_code=404, content_type="text/html")


async def handle_docs(request: Any) -> Response:
    html = (
        "<html><body>Documentation access: Please visit "
        '<a href="https://argo-proxy.readthedocs.io/en/latest/">'
        "https://argo-proxy.readthedocs.io/en/latest/</a>"
        " for full documentation.</body></html>"
    )
    return Response(body=html.encode(), status_code=200, content_type="text/html")


async def handle_health(request: Any) -> Response:
    return JSONResponse({"status": "healthy"})


async def handle_version(request: Any) -> Response:
    log_info("/version", context="app")
    from ._vendor.semver import version_parse
    from .endpoints.extras import get_pypi_versions

    versions = await get_pypi_versions()
    stable = versions.get("stable")
    pre = versions.get("pre")
    cur = version_parse(__version__)

    stable_upgrade = False
    pre_upgrade = False
    if stable:
        try:
            stable_upgrade = version_parse(stable) > cur
        except Exception:
            pass
    if pre:
        try:
            pre_upgrade = version_parse(pre) > cur
        except Exception:
            pass

    up_to_date = not stable_upgrade and not pre_upgrade

    update_commands: dict[str, str] = {}
    if stable_upgrade:
        update_commands["cli"] = "argo-proxy update install"
        update_commands["pip"] = "pip install --upgrade argo-proxy"
    if pre_upgrade:
        update_commands["cli_pre"] = "argo-proxy update install --pre"
        update_commands["pip_pre"] = "pip install --upgrade --pre argo-proxy"

    if stable_upgrade and pre_upgrade:
        message = f"New stable ({stable}) and pre-release ({pre}) available"
    elif stable_upgrade:
        message = f"New stable version {stable} available"
    elif pre_upgrade:
        message = f"New pre-release {pre} available"
    else:
        message = "You're using the latest version"

    import importlib.metadata

    from .cli.display import _CRITICAL_DEPS

    dependencies: dict[str, Any] = {}
    for dep_name in _CRITICAL_DEPS:
        try:
            dep_installed = importlib.metadata.version(dep_name)
        except importlib.metadata.PackageNotFoundError:
            continue
        dep_versions = await get_pypi_versions(dep_name)
        dep_stable = dep_versions.get("stable")
        dep_pre = dep_versions.get("pre")
        dep_cur = version_parse(dep_installed)

        dep_up_to_date = True
        if dep_stable:
            try:
                if version_parse(dep_stable) > dep_cur:
                    dep_up_to_date = False
            except Exception:
                pass
        if dep_up_to_date and dep_pre:
            try:
                if version_parse(dep_pre) > dep_cur:
                    dep_up_to_date = False
            except Exception:
                pass

        dependencies[dep_name] = {
            "installed": dep_installed,
            "latest_stable": dep_stable,
            "latest_pre": dep_pre,
            "up_to_date": dep_up_to_date,
            "update_command": f"pip install --upgrade {dep_name}",
        }

    return JSONResponse(
        {
            "version": __version__,
            "latest_stable": stable,
            "latest_pre": pre,
            "up_to_date": up_to_date,
            "message": message,
            "update_commands": update_commands or None,
            "dependencies": dependencies or None,
            "pypi": "https://pypi.org/project/argo-proxy/",
            "changelog": "https://argo-proxy.readthedocs.io/en/latest/changelog/",
        }
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


async def _startup(app: App) -> None:
    """Initialize ARGO config, model registry, and transport."""
    config_path_env = os.getenv("CONFIG_PATH")
    config, config_path = load_config(config_path_env, verbose=False)
    if config is None:
        log_error("Failed to load configuration", context="app")
        sys.exit(1)

    registry = ModelRegistry(config=config)
    await registry.initialize()

    stats = registry.get_model_stats()
    log_info("=" * 60, context="app")
    log_warning(
        f"MODEL REGISTRY: [{stats['unique_models']} MODELS, "
        f"{stats['total_aliases']} ALIASES]",
        context="app",
    )
    log_info(
        f"   Chat: {stats['unique_chat_models']} models "
        f"({stats['chat_aliases']} aliases)",
        context="app",
    )
    log_info(
        f"   Embed: {stats['unique_embed_models']} models "
        f"({stats['embed_aliases']} aliases)",
        context="app",
    )
    log_info("=" * 60, context="app")

    gateway_config = build_gateway_config(config, registry)

    inner_transport = HttpTransport()
    transport = ArgoTransport(
        inner_transport,
        anthropic_stream_mode=config.anthropic_stream_mode,
    )

    app.argo_config = config  # type: ignore[attr-defined]
    app.model_registry = registry  # type: ignore[attr-defined]
    app.gateway_config = gateway_config  # type: ignore[attr-defined]
    app.transport = transport  # type: ignore[attr-defined]
    app.metadata_store = ProviderMetadataStore()  # type: ignore[attr-defined]

    # Admin panel state (metrics, request log, persistence, profiling)
    from llm_rosetta.gateway.admin import setup_admin

    from .config import ArgoConfigIO

    config_io = ArgoConfigIO(config, registry)
    setup_admin(
        app,
        gateway_config,
        str(config_path) if config_path else None,
        config_io=config_io,
        disabled_tabs=["keys"],
        custom_head=_load_admin_custom_head(),
        branding={
            "title": "Argo Proxy",
            "subtitle": "gateway admin",
            "version": __version__,
            "links": [
                {
                    "label": "GitHub",
                    "url": "https://github.com/Oaklight/argo-proxy",
                    "icon": "github",
                },
                {
                    "label": "PyPI",
                    "url": "https://pypi.org/project/argo-proxy/",
                    "icon": "pypi",
                },
                {
                    "label": "Docs",
                    "url": "https://argo-proxy.readthedocs.io",
                    "icon": "docs",
                },
            ],
            "attribution": "Powered by llm-rosetta gateway",
        },
    )

    log_debug("Gateway transport initialized", context="app")


def create_app() -> App:
    """Create the argo-proxy application."""
    from .utils.misc import str_to_bool

    dev_mode = str_to_bool(os.environ.get("DEV_MODE", "false"))

    app = App(max_body_size=100 * 1024 * 1024, read_timeout=300.0)

    import secrets

    from llm_rosetta.gateway.admin.routes import register_admin_routes
    from llm_rosetta.gateway.auth import AuthState, create_auth_hook

    # Admin auth state (gateway API key auth is handled by our own hook,
    # but admin panel needs AuthState for token-based /admin/* auth)
    internal_token = f"rsk-internal-{secrets.token_hex(16)}"
    admin_password = os.environ.get("ADMIN_PASSWORD")
    auth_state = AuthState(
        None,  # no gateway-level keystore — ARGO validates upstream
        {},
        internal_token,
        admin_password=admin_password,
        open_on_no_keys=True,  # ARGO validates upstream
    )
    app.auth_state = auth_state  # type: ignore[attr-defined]
    app.internal_token = internal_token  # type: ignore[attr-defined]

    # Auth hooks: ARGO credential passthrough + admin panel auth
    app.before_request(create_argo_auth_hook())
    if admin_password:
        app.before_request(create_auth_hook(auth_state))

    # Security middleware
    from .utils.attack_logger import create_security_hook

    app.before_request(create_security_hook())

    # CORS — open for /v1/*, restricted for /admin/*
    @app.after_request
    async def add_cors_headers(request: Any, response: Any) -> Any:
        if not request.path.startswith("/admin"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    @app.route("/<path:_path>", methods=["OPTIONS"])
    async def cors_preflight(request: Any, _path: str = "") -> Response:
        resp = Response(body=b"", status_code=204)
        if not request.path.startswith("/admin"):
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "*"
            resp.headers["Access-Control-Allow-Headers"] = "*"
        return resp

    # Admin panel routes
    register_admin_routes(app)

    if dev_mode:
        log_warning(
            "Transparent proxy — all requests forwarded without conversion",
            context="app",
        )
        app.route("/health", methods=["GET"])(handle_health)
        app.route("/version", methods=["GET"])(handle_version)
        app.route("/refresh", methods=["POST"])(handle_refresh_models)
        return app

    # Info routes
    app.route("/", methods=["GET"])(handle_root)
    app.route("/v1", methods=["GET"])(handle_v1)
    app.route("/v1/docs", methods=["GET"])(handle_docs)

    # Proxy routes
    app.route("/v1/chat/completions", methods=["POST"])(handle_openai_chat)
    app.route("/v1/responses", methods=["POST"])(handle_openai_responses)
    app.route("/v1/messages", methods=["POST"])(handle_anthropic_messages)
    app.route("/v1beta/models/<path:model_path>", methods=["POST"])(handle_google_genai)
    app.route("/v1/embeddings", methods=["POST"])(handle_embeddings)

    # Model listing
    app.route("/v1/models", methods=["GET"])(handle_list_models)

    # Extras
    app.route("/refresh", methods=["POST"])(handle_refresh_models)
    app.route("/health", methods=["GET"])(handle_health)
    app.route("/version", methods=["GET"])(handle_version)

    return app


async def _run_server(app: App, *, host: str, port: int, socket: str = "") -> None:
    await _startup(app)
    app._bind_host = host  # type: ignore[attr-defined]
    app._bind_port = port  # type: ignore[attr-defined]
    try:
        await app._serve(host, port, socket=socket or None)
    finally:
        transport = getattr(app, "transport", None)
        metadata_store = getattr(app, "metadata_store", None)
        await close_resources(transport=transport, metadata_store=metadata_store)


def run(*, host: str = "0.0.0.0", port: int = 8080, socket: str = ""):
    app = create_app()

    def _force_exit(*_: Any) -> None:
        log_info("Force exiting on signal", context="app")
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _force_exit)

    try:
        asyncio.run(_run_server(app, host=host, port=port, socket=socket))
    except Exception as e:
        log_error(f"An error occurred while starting the server: {e}", context="app")
        sys.exit(1)
