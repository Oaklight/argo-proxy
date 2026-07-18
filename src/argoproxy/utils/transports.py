"""Validation utilities using the vendored httpclient."""

import asyncio
from typing import Any

from llm_rosetta._vendor.httpclient import AsyncClient


async def validate_api_async(
    url: str,
    user: str,
    payload: dict,
    timeout: int = 2,
    attempts: int = 3,
    resolver_overrides: dict[str, str] | None = None,
) -> bool:
    """Validates API connectivity with retries."""
    payload_copy = payload.copy()
    payload_copy["user"] = user

    last_err: Exception | None = None
    for attempt in range(attempts + 1):
        client = AsyncClient(timeout=timeout)
        try:
            response = await client.post(
                url,
                json=payload_copy,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code != 200:
                raise ValueError(f"API returned status code {response.status_code}")
            return True
        except Exception as e:
            last_err = e
            if attempt < attempts:
                await asyncio.sleep(0.5)
        finally:
            await client.aclose()

    if last_err is not None:
        raise last_err
    raise ValueError("API validation failed after all attempts")


async def _fetch_validation_models(
    models_url: str,
    timeout: int = 5,
    resolver_overrides: dict[str, str] | None = None,
) -> list[str]:
    """Fetch candidate model IDs for validation."""
    client = AsyncClient(timeout=timeout)
    try:
        resp = await client.get(models_url)
        if resp.status_code != 200:
            return []
        data = resp.json()  # type: ignore[union-attr]
        models = data.get("data", [])
    except Exception:
        return []
    finally:
        await client.aclose()

    _EMBEDDING_KEYWORDS = {"embedding", "ada", "v3small", "v3large"}
    chat_models = []
    for m in models:
        iid = (m.get("internal_id") or m.get("id") or "").lower()
        display_id = (m.get("id") or "").lower()
        if any(kw in iid or kw in display_id for kw in _EMBEDDING_KEYWORDS):
            continue
        chat_models.append(m)

    def _sort_key(m: dict[str, Any]) -> int:
        iid = (m.get("internal_id") or m.get("id") or "").lower()
        if "nano" in iid:
            return 0
        if "mini" in iid:
            return 1
        return 2

    chat_models.sort(key=_sort_key)
    return [mid for m in chat_models if (mid := m.get("internal_id") or m.get("id"))]


async def validate_user_async(
    chat_url: str,
    user: str,
    timeout: int = 10,
    attempts: int = 2,
    resolver_overrides: dict[str, str] | None = None,
) -> bool:
    """Validate that *user* is registered in ARGO."""
    from .misc import contains_argo_auth_warning, extract_text_from_response

    models_url = chat_url.rsplit("/chat/completions", 1)[0] + "/models"
    candidate_models = await _fetch_validation_models(
        models_url, timeout=timeout, resolver_overrides=resolver_overrides
    )
    if not candidate_models:
        candidate_models = ["gpt41nano"]

    last_err: Exception | None = None

    for model in candidate_models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "say ok"}],
            "user": user,
            "max_tokens": 5,
        }

        for attempt in range(attempts + 1):
            client = AsyncClient(timeout=timeout)
            try:
                response = await client.post(
                    chat_url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {user}",
                    },
                )
                if response.status_code == 400:
                    body = response.json()  # type: ignore[union-attr]
                    err_code = (
                        body.get("error", {}).get("code", "")
                        if isinstance(body, dict)
                        else ""
                    )
                    if err_code == "model_not_found":
                        last_err = ValueError(f"Model '{model}' not accepted")
                        break
                if response.status_code != 200:
                    raise ValueError(f"API returned status code {response.status_code}")
                data = response.json()  # type: ignore[union-attr]
                text = extract_text_from_response(data, "openai")
                return not contains_argo_auth_warning(text)
            except Exception as e:
                last_err = e
                if attempt < attempts:
                    await asyncio.sleep(0.5)
            finally:
                await client.aclose()

    if last_err is not None:
        raise last_err
    raise ValueError("User validation failed after all attempts")


async def validate_url_get_async(
    url: str,
    timeout: int = 5,
    attempts: int = 2,
    resolver_overrides: dict[str, str] | None = None,
) -> bool:
    """Validate URL connectivity with a simple GET request."""
    last_err: Exception | None = None
    for attempt in range(attempts + 1):
        client = AsyncClient(timeout=timeout)
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise ValueError(f"GET {url} returned status {response.status_code}")
            return True
        except Exception as e:
            last_err = e
            if attempt < attempts:
                await asyncio.sleep(0.5)
        finally:
            await client.aclose()

    if last_err is not None:
        raise last_err
    raise ValueError("URL validation failed after all attempts")
