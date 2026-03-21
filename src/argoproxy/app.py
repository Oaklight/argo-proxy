import asyncio
import os
import signal
import sys

from aiohttp import web

from .__init__ import __version__
from .config import ArgoConfig, load_config
from .endpoints import (
    dispatch,
    extras,
    native_openai,
)
from .endpoints._legacy import (
    chat,
    completions,
    embed,
    responses,
)
from .endpoints.dev_proxy import register_dev_routes
from .endpoints.extras import get_latest_pypi_version
from .models import ModelRegistry
from .performance import (
    OptimizedHTTPSession,
    get_performance_config,
    optimize_event_loop,
)
from .utils.logging import log_debug, log_error, log_info, log_warning


async def prepare_app(app):
    """Load configuration without validation for worker processes"""
    config_path = os.getenv("CONFIG_PATH")
    app["config"], _ = load_config(config_path, verbose=False)
    app["model_registry"] = ModelRegistry(config=app["config"])
    await app["model_registry"].initialize()

    # Display model information with styling
    model_stats = app["model_registry"].get_model_stats()
    model_stats["family_counts"]
    chat_family_counts = model_stats["chat_family_counts"]
    model_stats["embed_family_counts"]
    chat_family_alias_counts = model_stats["chat_family_alias_counts"]
    model_stats["embed_family_alias_counts"]

    log_info("=" * 60, context="app")
    log_warning(
        f"🤖 MODEL REGISTRY: [{model_stats['unique_models']} MODELS, {model_stats['total_aliases']} ALIASES]",
        context="app",
    )
    log_info(
        f"   ├─ Chat models: {model_stats['unique_chat_models']} models ({model_stats['chat_aliases']} aliases)",
        context="app",
    )

    # Show chat model family breakdown with alias counts
    chat_families = []
    if chat_family_counts["openai"] > 0:
        chat_families.append(
            f"OpenAI: {chat_family_counts['openai']} models ({chat_family_alias_counts['openai']} aliases)"
        )
    if chat_family_counts["anthropic"] > 0:
        chat_families.append(
            f"Anthropic: {chat_family_counts['anthropic']} models ({chat_family_alias_counts['anthropic']} aliases)"
        )
    if chat_family_counts["google"] > 0:
        chat_families.append(
            f"Google: {chat_family_counts['google']} models ({chat_family_alias_counts['google']} aliases)"
        )
    if chat_family_counts["unknown"] > 0:
        chat_families.append(
            f"Other: {chat_family_counts['unknown']} models ({chat_family_alias_counts['unknown']} aliases)"
        )

    if chat_families:
        for i, family_info in enumerate(chat_families):
            if i == len(chat_families) - 1:
                log_info(f"   │  └─ {family_info}", context="app")
            else:
                log_info(f"   │  ├─ {family_info}", context="app")

    log_info(
        f"   ├─ Embed models: {model_stats['unique_embed_models']} models ({model_stats['embed_aliases']} aliases)",
        context="app",
    )

    log_info(
        "   ├─ Naming docs: https://argo-proxy.readthedocs.io/en/latest/usage/models/",
        context="app",
    )
    log_info("   └─ Model availability refreshed successfully", context="app")
    log_info("=" * 60, context="app")

    # Apply event loop optimizations
    await optimize_event_loop()

    # Get performance configuration
    perf_config = get_performance_config()
    log_debug(f"Performance config: {perf_config}", context="app")

    # Create optimized HTTP session
    resolve_overrides = getattr(app["config"], "resolve_overrides", None)
    http_session_manager = OptimizedHTTPSession(
        user_agent=f"argo-proxy/{__version__}",
        resolve_overrides=resolve_overrides if resolve_overrides else None,
        **perf_config,
    )

    app["http_session_manager"] = http_session_manager
    app["http_session"] = await http_session_manager.create_session()

    log_debug("HTTP connection pool initialized", context="app")


async def cleanup_app(app):
    """Clean up resources when app shuts down"""
    if "http_session_manager" in app:
        await app["http_session_manager"].close()
        log_debug("HTTP session manager closed", context="app")

    # Cancel all pending tasks (best effort)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        log_debug("Cancelling pending tasks...", context="app")
        [task.cancel() for task in pending]
        await asyncio.gather(*pending, return_exceptions=True)


# ================= Argo Direct Access =================


async def proxy_argo_chat_directly(request: web.Request):
    log_info("/v1/chat", context="app")
    return await chat.proxy_request(request, convert_to_openai=False)


async def proxy_embedding_directly(request: web.Request):
    log_info("/v1/embed", context="app")
    return await embed.proxy_request(request, convert_to_openai=False)


# ================= OpenAI Compatible =================


async def proxy_openai_chat_compatible(request: web.Request):
    log_info("/v1/chat/completions", context="app")
    config: ArgoConfig = request.app["config"]

    if config.use_legacy_argo:
        return await chat.proxy_request(request)

    return await dispatch.proxy_request(request, source_provider="openai_chat")


async def proxy_openai_legacy_completions_compatible(request: web.Request):
    log_info("/v1/completions", context="app")
    config: ArgoConfig = request.app["config"]

    # Legacy completions only available in legacy mode
    if config.use_legacy_argo:
        return await completions.proxy_request(request)

    # In universal mode, passthrough to native OpenAI
    return await native_openai.proxy_native_openai_request(request, "completions")


async def proxy_openai_responses_request(request: web.Request):
    log_info("/v1/responses", context="app")
    config: ArgoConfig = request.app["config"]

    if config.use_legacy_argo:
        return await responses.proxy_request(request)

    return await dispatch.proxy_request(request, source_provider="openai_responses")


async def proxy_openai_embedding_request(request: web.Request):
    log_info("/v1/embeddings", context="app")
    config: ArgoConfig = request.app["config"]

    # In legacy mode, use old ARGO gateway pipeline
    if config.use_legacy_argo:
        return await embed.proxy_request(request, convert_to_openai=True)

    # Universal mode: native OpenAI passthrough
    return await native_openai.proxy_native_openai_request(request, "embeddings")


async def proxy_anthropic_messages(request: web.Request):
    """Handle Anthropic /v1/messages endpoint."""
    log_info("/v1/messages", context="app")
    return await dispatch.proxy_request(request, source_provider="anthropic")


async def proxy_google_genai(request: web.Request):
    """Handle Google GenAI /v1beta/models/{model}:{method} endpoints."""
    model_path = request.match_info["model_path"]
    log_info(f"/v1beta/models/{model_path}", context="app")

    if model_path.endswith(":streamGenerateContent"):
        model = model_path.removesuffix(":streamGenerateContent")
        return await dispatch.proxy_request(
            request,
            source_provider="google",
            model_override=model,
            force_stream=True,
        )
    elif model_path.endswith(":generateContent"):
        model = model_path.removesuffix(":generateContent")
        return await dispatch.proxy_request(
            request,
            source_provider="google",
            model_override=model,
        )
    else:
        return web.json_response(
            {"error": {"code": 400, "message": f"Unknown method in: {model_path}"}},
            status=400,
        )


async def get_models(request: web.Request):
    log_info("/v1/models", context="app")
    return extras.get_models(request)


async def refresh_models(request: web.Request):
    log_info("/refresh", context="app")
    return await extras.refresh_models(request)


# ================= Extras =================


async def root_endpoint(request: web.Request):
    """Root endpoint mimicking OpenAI's welcome message"""
    return web.json_response(
        {
            "message": "Welcome to the Argo-Proxy API! Documentation is available at https://argo-proxy.readthedocs.io/en/latest/"
        }
    )


async def v1_endpoint(request: web.Request):
    """V1 endpoint mimicking OpenAI's 404 behavior"""
    html_content = """<html>
<head><title>404 Not Found</title></head>
<body>
<center><h1>404 Not Found</h1></center>
<hr><center>argo-proxy</center>
</body>
</html>"""
    return web.Response(text=html_content, status=404, content_type="text/html")


async def docs(request: web.Request):
    msg = "<html><body>Documentation access: Please visit <a href='https://argo-proxy.readthedocs.io/en/latest/'>https://argo-proxy.readthedocs.io/en/latest/</a> for full documentation.</body></html>"
    return web.Response(text=msg, status=200, content_type="text/html")


async def health_check(request: web.Request):
    log_info("/health", context="app")
    return web.json_response({"status": "healthy"}, status=200)


async def get_version(request: web.Request):
    log_info("/version", context="app")
    latest = await get_latest_pypi_version()
    update_available = latest and latest != __version__

    response = {
        "version": __version__,
        "latest": latest,
        "up_to_date": not update_available,
        "pypi": "https://pypi.org/project/argo-proxy/",
    }

    if update_available:
        response.update(
            {
                "message": f"New version {latest} available",
                "install_command": "pip install --upgrade argo-proxy",
            }
        )
    else:
        response["message"] = "You're using the latest version"

    return web.json_response(response)


def create_app():
    """Factory function to create a new application instance"""
    # Check dev mode from environment (set by CLI before app creation)
    import os

    from .config import ArgoConfig
    from .utils.misc import str_to_bool

    dev_mode = str_to_bool(os.environ.get("DEV_MODE", "false"))

    # Set client_max_size to 100MB to handle large image payloads from remote clients
    # Users may send images larger than the gateway's 20MB limit; argo-proxy will
    # compress them before forwarding. Default aiohttp limit is 1MB which is too small.
    app = web.Application(client_max_size=100 * 1024 * 1024)
    app.on_startup.append(prepare_app)
    app.on_shutdown.append(cleanup_app)

    if dev_mode:
        log_warning(
            "🔧 DEV MODE: Pure reverse proxy enabled — no format conversion",
            context="app",
        )

        # Only register health check, version, and dev proxy routes
        app.router.add_get("/health", health_check)
        app.router.add_get("/version", get_version)

        # Register dev proxy routes using a temporary config for URL resolution
        dev_config = ArgoConfig()
        register_dev_routes(app, dev_config)

        return app

    # root endpoints
    app.router.add_get("/", root_endpoint)
    app.router.add_get("/v1", v1_endpoint)

    # Legacy ARGO direct-access endpoints (only in legacy mode)
    use_legacy = str_to_bool(os.environ.get("USE_LEGACY_ARGO", "false"))
    if use_legacy:
        app.router.add_post("/v1/chat", proxy_argo_chat_directly)
        app.router.add_post("/v1/embed", proxy_embedding_directly)
        app.router.add_post(
            "/v1/completions", proxy_openai_legacy_completions_compatible
        )

    # Universal endpoints (all 4 client formats)
    app.router.add_post("/v1/chat/completions", proxy_openai_chat_compatible)
    app.router.add_post("/v1/responses", proxy_openai_responses_request)
    app.router.add_post("/v1/messages", proxy_anthropic_messages)
    app.router.add_post("/v1beta/models/{model_path}", proxy_google_genai)

    # Embeddings (passthrough)
    app.router.add_post("/v1/embeddings", proxy_openai_embedding_request)

    # Model listing
    app.router.add_get("/v1/models", get_models)

    # extras
    app.router.add_post("/refresh", refresh_models)
    app.router.add_get("/v1/docs", docs)
    app.router.add_get("/health", health_check)
    app.router.add_get("/version", get_version)

    return app


def run(*, host: str = "0.0.0.0", port: int = 8080):
    app = create_app()

    # Add this to ensure signal handlers trigger a full shutdown
    def _force_exit(*_):
        log_info("Force exiting on signal", context="app")
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _force_exit)

    try:
        web.run_app(app, host=host, port=port)
    except Exception as e:
        log_error(f"An error occurred while starting the server: {e}", context="app")
        sys.exit(1)
