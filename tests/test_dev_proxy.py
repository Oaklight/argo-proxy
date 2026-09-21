"""Unit tests for dev-proxy mode handlers."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from argoproxy.dev_proxy import (
    _DEV_PROVIDER_NAME,
    _detect_stream,
    _extract_api_key,
    _extract_error_detail,
    _parse_and_inject,
    handle_dev_anthropic,
    handle_dev_embeddings,
    handle_dev_google,
    handle_dev_models,
    handle_dev_openai_chat,
    handle_dev_openai_responses,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeConfig:
    user = "test-user"
    argo_base_url = "https://example.com"
    native_openai_base_url = "https://example.com/v1"
    native_anthropic_base_url = "https://example.com"


class FakeHeaders(dict):
    def get(self, key, default=""):
        return super().get(key.lower(), default)


class FakeRequest:
    """Minimal request stub for handler tests."""

    def __init__(
        self,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        self._body = body
        self.headers = FakeHeaders(headers or {})
        self.query_params: dict[str, list[str]] = {}
        self.app = MagicMock()
        self.app.argo_config = FakeConfig()

    def json(self) -> dict[str, Any]:
        if self._body is None:
            raise ValueError("Invalid JSON")
        return self._body.copy()


class FakeHttpResponse:
    """Stub for httpclient.Response."""

    def __init__(
        self,
        status_code: int = 200,
        body: dict | str | bytes = b"",
        headers: dict[str, str] | None = None,
    ):
        self.status_code = status_code
        if isinstance(body, dict):
            self.content = json.dumps(body).encode()
        elif isinstance(body, str):
            self.content = body.encode()
        else:
            self.content = body
        self.headers = headers or {"content-type": "application/json"}

    def json(self) -> Any:
        return json.loads(self.content)


# ---------------------------------------------------------------------------
# _detect_stream
# ---------------------------------------------------------------------------


class TestDetectStream:
    def test_openai_stream_true(self):
        assert _detect_stream({"stream": True}, "openai_chat") is True

    def test_openai_stream_false(self):
        assert _detect_stream({"stream": False}, "openai_chat") is False

    def test_openai_no_stream_key(self):
        assert _detect_stream({"model": "gpt-4o"}, "openai_chat") is False

    def test_google_always_false(self):
        # Google streaming is detected by URL suffix, not body
        assert _detect_stream({"stream": True}, "google") is False


# ---------------------------------------------------------------------------
# _extract_api_key
# ---------------------------------------------------------------------------


class TestExtractApiKey:
    def test_bearer_token(self):
        req = FakeRequest(headers={"authorization": "Bearer sk-test-123"})
        assert _extract_api_key(req) == "sk-test-123"

    def test_x_api_key(self):
        req = FakeRequest(headers={"x-api-key": "anthropic-key"})
        assert _extract_api_key(req) == "anthropic-key"

    def test_no_key(self):
        req = FakeRequest(headers={})
        assert _extract_api_key(req) is None

    def test_query_param(self):
        req = FakeRequest()
        req.query_params = {"key": ["query-key-123"]}
        assert _extract_api_key(req) == "query-key-123"


# ---------------------------------------------------------------------------
# _parse_and_inject
# ---------------------------------------------------------------------------


class TestParseAndInject:
    def test_valid_body_returns_effective_user(self):
        req = FakeRequest(body={"model": "gpt-4o", "messages": []})
        with patch(
            "argoproxy.dev_proxy.should_use_username_passthrough", return_value=False
        ):
            body, rid, eff_user = _parse_and_inject(req, FakeConfig())
        assert body is not None
        assert eff_user == "test-user"
        assert body["model"] == "gpt-4o"
        assert rid  # non-empty

    def test_invalid_json_returns_none(self):
        req = FakeRequest(body=None)
        with patch(
            "argoproxy.dev_proxy.should_use_username_passthrough", return_value=False
        ):
            body, rid, eff_user = _parse_and_inject(req, FakeConfig())
        assert body is None
        assert eff_user == "test-user"

    def test_passthrough_mode_uses_api_key(self):
        req = FakeRequest(
            body={"model": "gpt-4o"},
            headers={"authorization": "Bearer user-key"},
        )
        with patch(
            "argoproxy.dev_proxy.should_use_username_passthrough", return_value=True
        ):
            body, rid, eff_user = _parse_and_inject(req, FakeConfig())
        assert eff_user == "user-key"


# ---------------------------------------------------------------------------
# Handler tests — verify correct URL construction and passthrough
# ---------------------------------------------------------------------------


def _setup_transport_mock(request: FakeRequest) -> AsyncMock:
    """Wire up a mock transport on the request's app."""
    mock_client = AsyncMock()
    mock_transport = MagicMock()
    mock_transport.raw_client.return_value = mock_client
    request.app.transport = mock_transport
    return mock_client


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_openai_chat_non_streaming(mock_passthrough):
    req = FakeRequest(
        body={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    )
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"choices": [{"message": {"content": "hello"}}]}
    )

    resp = await handle_dev_openai_chat(req)
    assert resp.status_code == 200

    # Verify URL
    call_args = mock_client.post.call_args
    url = call_args[0][0]
    assert url == "https://example.com/v1/chat/completions"

    # Verify auth header uses config user
    headers = call_args[1]["headers"]
    assert headers["Authorization"] == "Bearer test-user"


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_openai_chat_invalid_json(mock_passthrough):
    req = FakeRequest(body=None)  # will raise on .json()
    _setup_transport_mock(req)

    resp = await handle_dev_openai_chat(req)
    assert resp.status_code == 400
    body = json.loads(resp.body)
    assert "Invalid JSON" in body["error"]["message"]


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_anthropic_injects_metadata(mock_passthrough):
    req = FakeRequest(
        body={
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 100,
        }
    )
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"content": [{"text": "hello"}]}
    )

    resp = await handle_dev_anthropic(req)
    assert resp.status_code == 200

    call_args = mock_client.post.call_args
    url = call_args[0][0]
    assert url == "https://example.com/v1/messages"

    body = call_args[1]["json"]
    assert body["metadata"]["user_id"] == "test-user"


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_embeddings(mock_passthrough):
    req = FakeRequest(body={"input": "test text", "model": "text-embedding-3-small"})
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"data": [{"embedding": [0.1, 0.2]}]}
    )

    resp = await handle_dev_embeddings(req)
    assert resp.status_code == 200

    url = mock_client.post.call_args[0][0]
    assert url == "https://example.com/v1/embeddings"


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_openai_responses(mock_passthrough):
    req = FakeRequest(body={"model": "gpt-4o", "input": "What is 2+2?"})
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"output": [{"content": [{"text": "4"}]}]}
    )

    resp = await handle_dev_openai_responses(req)
    assert resp.status_code == 200

    url = mock_client.post.call_args[0][0]
    assert url == "https://example.com/v1/responses"


@pytest.mark.asyncio
async def test_handle_dev_models():
    req = FakeRequest()
    mock_client = AsyncMock()
    mock_transport = MagicMock()
    mock_transport.raw_client.return_value = mock_client
    req.app.transport = mock_transport
    mock_client.get.return_value = FakeHttpResponse(200, {"data": [{"id": "gpt-4o"}]})

    resp = await handle_dev_models(req)
    assert resp.status_code == 200

    url = mock_client.get.call_args[0][0]
    assert url == "https://example.com/v1/models"


# ---------------------------------------------------------------------------
# Google handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_google_generate_content(mock_passthrough):
    req = FakeRequest(
        body={"contents": [{"parts": [{"text": "hi"}]}]},
    )
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
    )

    resp = await handle_dev_google(req, model_path="gemini-2.5-pro:generateContent")
    assert resp.status_code == 200

    url = mock_client.post.call_args[0][0]
    assert url == "https://example.com/v1beta/models/gemini-2.5-pro:generateContent"


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_google_stream_generate_content(mock_passthrough):
    req = FakeRequest(
        body={"contents": [{"parts": [{"text": "hi"}]}]},
    )
    mock_client = _setup_transport_mock(req)

    # Streaming returns an httpclient.StreamingResponse-like object
    mock_stream_resp = AsyncMock()
    mock_stream_resp.status_code = 200
    mock_stream_resp.headers = {"content-type": "text/event-stream"}

    async def fake_lines():
        yield 'data: {"candidates":[]}'
        yield ""

    mock_stream_resp.aiter_lines = fake_lines
    mock_client.post.return_value = mock_stream_resp

    resp = await handle_dev_google(
        req, model_path="gemini-2.5-pro:streamGenerateContent"
    )
    # Streaming requests return a StreamingResponse
    assert resp.status_code == 200

    url = mock_client.post.call_args[0][0]
    assert (
        url == "https://example.com/v1beta/models/gemini-2.5-pro:streamGenerateContent"
    )


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_handle_dev_google_invalid_json(mock_passthrough):
    req = FakeRequest(body=None)
    _setup_transport_mock(req)

    resp = await handle_dev_google(req, model_path="gemini-2.5-pro:generateContent")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Auth warning detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
@patch("argoproxy.dev_proxy.contains_argo_auth_warning", return_value=True)
async def test_auth_warning_returns_403(mock_warning, mock_passthrough):
    req = FakeRequest(body={"model": "gpt-4o", "messages": []})
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, "AUTHENTICATION NOTICE FROM ARGO: invalid user"
    )

    resp = await handle_dev_openai_chat(req)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Upstream error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_upstream_error_returns_502(mock_passthrough):
    req = FakeRequest(body={"model": "gpt-4o", "messages": []})
    mock_client = _setup_transport_mock(req)
    mock_client.post.side_effect = ConnectionError("upstream down")

    resp = await handle_dev_openai_chat(req)
    assert resp.status_code == 502
    body = json.loads(resp.body)
    assert body["error"]["type"] == "server_error"


# ---------------------------------------------------------------------------
# Telemetry recording in dev-proxy handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.record_telemetry")
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_openai_chat_records_telemetry(mock_passthrough, mock_telemetry):
    req = FakeRequest(
        body={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
    )
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"choices": [{"message": {"content": "hello"}}]}
    )

    resp = await handle_dev_openai_chat(req)
    assert resp.status_code == 200

    mock_telemetry.assert_called_once()
    kwargs = mock_telemetry.call_args[1]
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["source_provider"] == "openai_chat"
    assert kwargs["target_provider"] == "openai_chat"
    assert kwargs["provider_name"] == _DEV_PROVIDER_NAME
    assert kwargs["status_code"] == 200
    assert kwargs["error_detail"] is None
    assert kwargs["duration_ms"] >= 0


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.record_telemetry")
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_openai_chat_records_telemetry_on_error(mock_passthrough, mock_telemetry):
    req = FakeRequest(body={"model": "gpt-4o", "messages": []})
    mock_client = _setup_transport_mock(req)
    mock_client.post.side_effect = ConnectionError("upstream down")

    resp = await handle_dev_openai_chat(req)
    assert resp.status_code == 502

    mock_telemetry.assert_called_once()
    kwargs = mock_telemetry.call_args[1]
    assert kwargs["status_code"] == 502
    assert kwargs["error_detail"] is not None


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.record_telemetry")
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_anthropic_records_telemetry(mock_passthrough, mock_telemetry):
    req = FakeRequest(
        body={
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 100,
        }
    )
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"content": [{"text": "hello"}]}
    )

    resp = await handle_dev_anthropic(req)
    assert resp.status_code == 200

    mock_telemetry.assert_called_once()
    kwargs = mock_telemetry.call_args[1]
    assert kwargs["model"] == "claude-sonnet-4-6-20250514"
    assert kwargs["source_provider"] == "anthropic"
    assert kwargs["provider_name"] == _DEV_PROVIDER_NAME


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.record_telemetry")
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_google_records_telemetry(mock_passthrough, mock_telemetry):
    req = FakeRequest(body={"contents": [{"parts": [{"text": "hi"}]}]})
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
    )

    resp = await handle_dev_google(req, model_path="gemini-2.5-pro:generateContent")
    assert resp.status_code == 200

    mock_telemetry.assert_called_once()
    kwargs = mock_telemetry.call_args[1]
    assert kwargs["model"] == "gemini-2.5-pro"
    assert kwargs["source_provider"] == "google"
    assert kwargs["is_stream"] is False


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.record_telemetry")
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_embeddings_records_telemetry(mock_passthrough, mock_telemetry):
    req = FakeRequest(body={"input": "test text", "model": "text-embedding-3-small"})
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"data": [{"embedding": [0.1, 0.2]}]}
    )

    resp = await handle_dev_embeddings(req)
    assert resp.status_code == 200

    mock_telemetry.assert_called_once()
    kwargs = mock_telemetry.call_args[1]
    assert kwargs["model"] == "text-embedding-3-small"
    assert kwargs["source_provider"] == "openai_embeddings"
    assert kwargs["is_stream"] is False
    assert kwargs["provider_name"] == _DEV_PROVIDER_NAME


@pytest.mark.asyncio
@patch("argoproxy.dev_proxy.record_telemetry")
@patch("argoproxy.dev_proxy.should_use_username_passthrough", return_value=False)
async def test_responses_records_telemetry(mock_passthrough, mock_telemetry):
    req = FakeRequest(body={"model": "gpt-4o", "input": "What is 2+2?"})
    mock_client = _setup_transport_mock(req)
    mock_client.post.return_value = FakeHttpResponse(
        200, {"output": [{"content": [{"text": "4"}]}]}
    )

    resp = await handle_dev_openai_responses(req)
    assert resp.status_code == 200

    mock_telemetry.assert_called_once()
    kwargs = mock_telemetry.call_args[1]
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["source_provider"] == "openai_responses"
    assert kwargs["provider_name"] == _DEV_PROVIDER_NAME


# ---------------------------------------------------------------------------
# _extract_error_detail
# ---------------------------------------------------------------------------


class _FakeGatewayResponse:
    """Stub matching httpserver.Response (uses .body, not .content)."""

    def __init__(self, status_code: int, body: Any = b""):
        self.status_code = status_code
        if isinstance(body, dict):
            self.body = json.dumps(body).encode()
        elif isinstance(body, str):
            self.body = body.encode()
        else:
            self.body = body


class TestExtractErrorDetail:
    def _resp(self, status_code: int, body: Any = b"") -> _FakeGatewayResponse:
        return _FakeGatewayResponse(status_code, body)

    def test_success_returns_none(self):
        assert _extract_error_detail(self._resp(200)) is None

    def test_json_error_message(self):
        resp = self._resp(
            400, {"error": {"message": "Invalid model", "type": "invalid_request"}}
        )
        assert _extract_error_detail(resp) == "Invalid model"

    def test_json_error_type_fallback(self):
        resp = self._resp(400, {"error": {"type": "rate_limit_exceeded"}})
        assert _extract_error_detail(resp) == "rate_limit_exceeded"

    def test_json_string_error(self):
        resp = self._resp(500, {"error": "something broke"})
        assert _extract_error_detail(resp) == "something broke"

    def test_plain_text_body(self):
        resp = self._resp(502, "Bad Gateway")
        assert _extract_error_detail(resp) == "Bad Gateway"

    def test_no_body_fallback(self):
        resp = self._resp(504, b"")
        assert _extract_error_detail(resp) == "HTTP 504"
