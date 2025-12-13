import asyncio
import os
import signal
import sys

from aiohttp import web
from loguru import logger

from .__init__ import __version__
from .config import ArgoConfig, load_config
from .endpoints import chat, completions, embed, extras, native_openai, responses
from .endpoints.extras import get_latest_pypi_version
from .models import ModelRegistry
from .performance import (
    OptimizedHTTPSession,
    get_performance_config,
    optimize_event_loop,
)


async def prepare_app(app):
    """Load configuration without validation for worker processes"""
    config_path = os.getenv("CONFIG_PATH")
    app["config"], _ = load_config(config_path, verbose=False)
    app["model_registry"] = ModelRegistry(config=app["config"])
    await app["model_registry"].initialize()

    # Display model information with styling
    model_count = len(app["model_registry"].available_models)
    logger.info("=" * 60)
    logger.warning(f"🤖 MODEL REGISTRY: [{model_count} MODELS AVAILABLE]")
    logger.info("   └─ Model availability refreshed successfully")
    logger.info("=" * 60)

    # Apply event loop optimizations
    await optimize_event_loop()

    # Get performance configuration
    perf_config = get_performance_config()
    logger.info(f"Performance config: {perf_config}")

    # Create optimized HTTP session
    http_session_manager = OptimizedHTTPSession(
        user_agent=f"argo-proxy/{__version__}", **perf_config
    )

    app["http_session_manager"] = http_session_manager
    app["http_session"] = await http_session_manager.create_session()

    logger.info("Optimized HTTP connection pool initialized")


async def cleanup_app(app):
    """Clean up resources when app shuts down"""
    if "http_session_manager" in app:
        await app["http_session_manager"].close()
        logger.info("HTTP session manager closed")

    # Cancel all pending tasks (best effort)
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        logger.info("Cancelling pending tasks...")
        [task.cancel() for task in pending]
        await asyncio.gather(*pending, return_exceptions=True)


# ================= Argo Direct Access =================


async def proxy_argo_chat_directly(request: web.Request):
    logger.info("/v1/chat")
    return await chat.proxy_request(request, convert_to_openai=False)


async def proxy_embedding_directly(request: web.Request):
    logger.info("/v1/embed")
    return await embed.proxy_request(request, convert_to_openai=False)


# ================= OpenAI Compatible =================


async def proxy_openai_chat_compatible(request: web.Request):
    logger.info("/v1/chat/completions")
    config: ArgoConfig = request.app["config"]

    # If native OpenAI mode is enabled, use passthrough
    if config.use_native_openai:
        return await native_openai.proxy_native_openai_request(
            request, "chat/completions"
        )

    return await chat.proxy_request(request)


async def proxy_openai_legacy_completions_compatible(request: web.Request):
    logger.info("/v1/completions")
    config: ArgoConfig = request.app["config"]

    # If native OpenAI mode is enabled, use passthrough
    if config.use_native_openai:
        return await native_openai.proxy_native_openai_request(request, "completions")

    return await completions.proxy_request(request)


async def proxy_openai_responses_request(request: web.Request):
    logger.info("/v1/responses")
    return await responses.proxy_request(request)


async def proxy_openai_embedding_request(request: web.Request):
    logger.info("/v1/embeddings")
    config: ArgoConfig = request.app["config"]

    # If native OpenAI mode is enabled, use passthrough
    if config.use_native_openai:
        return await native_openai.proxy_native_openai_request(request, "embeddings")

    return await embed.proxy_request(request, convert_to_openai=True)


async def get_models(request: web.Request):
    logger.info("/v1/models")
    return extras.get_models(request)


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
    logger.info("/health")
    return web.json_response({"status": "healthy"}, status=200)


async def get_version(request: web.Request):
    logger.info("/version")
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
    app = web.Application()
    app.on_startup.append(prepare_app)
    app.on_shutdown.append(cleanup_app)

    # root endpoints
    app.router.add_get("/", root_endpoint)
    app.router.add_get("/v1", v1_endpoint)

    # openai incompatible
    app.router.add_post("/v1/chat", proxy_argo_chat_directly)
    app.router.add_post("/v1/embed", proxy_embedding_directly)

    # openai compatible
    app.router.add_post("/v1/chat/completions", proxy_openai_chat_compatible)
    app.router.add_post("/v1/completions", proxy_openai_legacy_completions_compatible)
    app.router.add_post("/v1/responses", proxy_openai_responses_request)
    app.router.add_post("/v1/embeddings", proxy_openai_embedding_request)
    app.router.add_get("/v1/models", get_models)

    # extras
    app.router.add_get("/v1/docs", docs)
    app.router.add_get("/health", health_check)
    app.router.add_get("/version", get_version)

    return app


def run(*, host: str = "0.0.0.0", port: int = 8080):
    app = create_app()

    # Add this to ensure signal handlers trigger a full shutdown
    def _force_exit(*_):
        logger.info("Force exiting on signal")
        sys.exit(0)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _force_exit)

    try:
        web.run_app(app, host=host, port=port)
    except Exception as e:
        logger.error(f"An error occurred while starting the server: {e}")
        sys.exit(1)
