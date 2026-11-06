"""Unit tests for the route handlers in :mod:`argoproxy.app`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from argoproxy.app import (
    handle_anthropic_messages,
    handle_openai_chat,
    handle_openai_responses,
)


class FakeRequest:
    """Minimal stand-in for the httpserver request object."""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "source_provider"),
    [
        (handle_openai_chat, "openai_chat"),
        # Base format, not the legacy ``openai_responses`` shim spelling.
        (handle_openai_responses, "open_responses"),
        (handle_anthropic_messages, "anthropic"),
    ],
)
async def test_handler_forwards_source_provider(handler, source_provider):
    with patch("argoproxy.app._argo_proxy_handler", new=AsyncMock()) as mock_handler:
        await handler(FakeRequest())

    assert mock_handler.call_args.kwargs["source_provider"] == source_provider
