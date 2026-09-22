"""Tests for the argo auth hook — passthrough key enforcement."""

import pytest
from types import SimpleNamespace
from unittest.mock import patch

from argoproxy.auth import create_argo_auth_hook


def _make_request(path="/v1/chat/completions", headers=None):
    req = SimpleNamespace(
        path=path,
        headers=headers or {},
        query_params={},
    )
    return req


@pytest.mark.asyncio
async def test_passthrough_rejects_keyless_request():
    hook = create_argo_auth_hook()
    req = _make_request(headers={})
    with patch("argoproxy.auth.should_use_username_passthrough", return_value=True):
        resp = await hook(req)
    assert resp is not None
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_passthrough_accepts_keyed_request():
    hook = create_argo_auth_hook()
    req = _make_request(headers={"authorization": "Bearer testuser"})
    with patch("argoproxy.auth.should_use_username_passthrough", return_value=True):
        resp = await hook(req)
    assert resp is None


@pytest.mark.asyncio
async def test_no_passthrough_allows_keyless_request():
    hook = create_argo_auth_hook()
    req = _make_request(headers={})
    with patch("argoproxy.auth.should_use_username_passthrough", return_value=False):
        resp = await hook(req)
    assert resp is None


@pytest.mark.asyncio
async def test_public_paths_exempt():
    hook = create_argo_auth_hook()
    for path in ["/health", "/health/live", "/version"]:
        req = _make_request(path=path, headers={})
        with patch("argoproxy.auth.should_use_username_passthrough", return_value=True):
            resp = await hook(req)
        assert resp is None, f"Expected None for {path}"


@pytest.mark.asyncio
async def test_admin_paths_exempt():
    hook = create_argo_auth_hook()
    req = _make_request(path="/admin/api/metrics", headers={})
    with patch("argoproxy.auth.should_use_username_passthrough", return_value=True):
        resp = await hook(req)
    assert resp is None


@pytest.mark.asyncio
async def test_anthropic_error_format():
    hook = create_argo_auth_hook()
    req = _make_request(path="/v1/messages", headers={})
    with patch("argoproxy.auth.should_use_username_passthrough", return_value=True):
        resp = await hook(req)
    assert resp.status_code == 401
    import json

    body = json.loads(resp.body)
    assert body["type"] == "error"
    assert body["error"]["type"] == "authentication_error"
