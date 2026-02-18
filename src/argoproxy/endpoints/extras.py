from typing import Optional

import aiohttp
from aiohttp import web

from ..models import ModelRegistry
from ..utils.logging import log_error, log_info


def get_models(request: web.Request):
    """
    Returns a list of available models in OpenAI-compatible format.
    """
    model_registry: ModelRegistry = request.app["model_registry"]
    return web.json_response(model_registry.as_openai_list(), status=200)


async def refresh_models(request: web.Request):
    """Reload the model list from upstream without restarting the instance.

    Returns:
        JSON response with refresh status and updated model statistics.
    """
    model_registry: ModelRegistry = request.app["model_registry"]

    old_stats = model_registry.get_model_stats()

    try:
        await model_registry.refresh_availability()
    except Exception as e:
        log_error(f"Model refresh failed: {e}", context="refresh")
        return web.json_response(
            {"status": "error", "message": f"Refresh failed: {str(e)}"},
            status=500,
        )

    new_stats = model_registry.get_model_stats()

    log_info(
        f"Model list refreshed: {old_stats['unique_models']} -> {new_stats['unique_models']} unique models, "
        f"{old_stats['total_aliases']} -> {new_stats['total_aliases']} aliases",
        context="refresh",
    )

    return web.json_response(
        {
            "status": "ok",
            "message": "Model list refreshed successfully",
            "previous": {
                "unique_models": old_stats["unique_models"],
                "total_aliases": old_stats["total_aliases"],
            },
            "current": {
                "unique_models": new_stats["unique_models"],
                "total_aliases": new_stats["total_aliases"],
                "chat_models": new_stats["unique_chat_models"],
                "embed_models": new_stats["unique_embed_models"],
            },
        },
        status=200,
    )


async def get_latest_pypi_version() -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pypi.org/pypi/argo-proxy/json",
                headers={
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },  # Add these headers
                timeout=5,
            ) as response:
                response.raise_for_status()
                data = await response.json()
                return data["info"]["version"]
    except Exception:
        return None
