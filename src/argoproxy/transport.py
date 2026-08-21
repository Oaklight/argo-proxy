"""ARGO-specific transport wrapper.

Wraps the gateway's :class:`HttpTransport` to add:

* **ARGO auth warning detection** on every upstream response (both
  streaming and non-streaming).
* **anthropic_stream_mode** logic (force / retry / passthrough) that
  upgrades non-streaming Anthropic requests to streaming when the
  upstream rejects them.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from llm_rosetta.gateway.transport._base import (
    UpstreamResponse,
    UpstreamStream,
)
from llm_rosetta.gateway.transport.http import HttpTransport
from llm_rosetta.gateway.transport.provider_info import ProviderInfo

_ARGO_AUTH_WARNING_RE = re.compile(r"AUTHENTICATION NOTICE FROM ARGO", re.IGNORECASE)


def _contains_warning(text: str) -> bool:
    return bool(_ARGO_AUTH_WARNING_RE.search(text))


logger = logging.getLogger("argo-proxy")


class ArgoAuthWarning(Exception):
    """Raised when an ARGO authentication warning is detected in a response."""


def _is_stream_required_error(status_code: int, error_text: str) -> bool:
    """Detect Anthropic's 'streaming is required' bounce-back (HTTP 500)."""
    if status_code != 500:
        return False
    return "streaming is required" in error_text.lower()


def _check_response_for_warning(response: UpstreamResponse) -> None:
    """Raise :class:`ArgoAuthWarning` if the response body contains the warning."""
    if response.body:
        text = json.dumps(response.body)
        if _contains_warning(text):
            raise ArgoAuthWarning()
    elif response.raw_content:
        text = response.raw_content.decode("utf-8", errors="replace")
        if _contains_warning(text):
            raise ArgoAuthWarning()


class ArgoUpstreamStream(UpstreamStream):
    """Wraps an :class:`UpstreamStream` to detect ARGO auth warnings in chunks."""

    def __init__(self, inner: UpstreamStream) -> None:
        self._inner = inner
        self.status_code = inner.status_code

    async def read_error(self) -> str:
        text = await self._inner.read_error()
        if _contains_warning(text):
            raise ArgoAuthWarning()
        return text

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self._iter_with_check()

    async def _iter_with_check(self) -> AsyncIterator[dict[str, Any]]:
        async for chunk in self._inner:
            raw = json.dumps(chunk)
            if _contains_warning(raw):
                raise ArgoAuthWarning()
            yield chunk

    async def close(self) -> None:
        await self._inner.close()


class ArgoTransport:
    """Wraps :class:`HttpTransport` with ARGO-specific behavior.

    Implements the :class:`UpstreamTransport` protocol so it can be
    injected into the gateway app as ``app.transport``.
    """

    def __init__(
        self,
        inner: HttpTransport,
        *,
        anthropic_stream_mode: str = "force",
    ) -> None:
        self._inner = inner
        self._anthropic_stream_mode = anthropic_stream_mode

    async def send(
        self,
        provider_info: ProviderInfo,
        url: str,
        body: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> UpstreamResponse:
        response = await self._inner.send(
            provider_info,
            url,
            body,
            extra_headers=extra_headers,
        )
        _check_response_for_warning(response)
        return response

    async def send_streaming(
        self,
        provider_info: ProviderInfo,
        url: str,
        body: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> UpstreamStream:
        stream = await self._inner.send_streaming(
            provider_info,
            url,
            body,
            extra_headers=extra_headers,
        )
        return ArgoUpstreamStream(stream)

    def raw_client(self, proxy_url: str | None = None) -> Any:
        """Return a raw :class:`AsyncClient` from the inner transport's pool.

        Intended for dev-proxy passthrough where the full transport
        pipeline (URL templating, provider-info auth, etc.) is not needed.
        """
        return self._inner._pool.get(proxy_url)

    async def close(self) -> None:
        await self._inner.close()

    # -- Anthropic stream-mode retry (used by custom proxy handler) ---------

    async def send_with_anthropic_retry(
        self,
        provider_info: ProviderInfo,
        url: str,
        body: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> UpstreamResponse | UpstreamStream:
        """Send a request respecting ``anthropic_stream_mode``.

        * ``"force"``:  always stream (caller should use send_streaming).
        * ``"passthrough"``: honour the client's request as-is.
        * ``"retry"``: try non-streaming first; on Anthropic's
          "streaming is required" 500, retry as streaming.

        Returns either an :class:`UpstreamResponse` (non-streaming) or
        an :class:`UpstreamStream` (streaming).
        """
        mode = self._anthropic_stream_mode

        if mode == "force":
            return await self.send_streaming(
                provider_info,
                url,
                body,
                extra_headers=extra_headers,
            )

        # "passthrough" or "retry" — try non-streaming first
        response = await self._inner.send(
            provider_info,
            url,
            body,
            extra_headers=extra_headers,
        )

        if mode != "retry":
            _check_response_for_warning(response)
            return response

        # retry mode: check if we got the "streaming required" bounce
        if response.status_code == 500:
            error_text = response.error_text
            if _is_stream_required_error(500, error_text):
                logger.info(
                    "Anthropic returned 'streaming required', "
                    "retrying with forced streaming (retry mode)"
                )
                return await self.send_streaming(
                    provider_info,
                    url,
                    body,
                    extra_headers=extra_headers,
                )

        _check_response_for_warning(response)
        return response
