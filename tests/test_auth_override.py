"""Tests for _build_auth_override in the main proxy path."""

from types import SimpleNamespace

from argoproxy.app import _build_auth_override


class TestBuildAuthOverride:
    def test_openai_style_provider(self):
        provider = SimpleNamespace(
            _auth_header_fn=lambda k: {"Authorization": f"Bearer {k}"}
        )
        result = _build_auth_override(provider, "brettin")
        assert result == {"Authorization": "Bearer brettin"}

    def test_anthropic_style_provider(self):
        provider = SimpleNamespace(
            _auth_header_fn=lambda k: {
                "x-api-key": k,
                "anthropic-version": "2023-06-01",
            }
        )
        result = _build_auth_override(provider, "brettin")
        assert result == {"x-api-key": "brettin", "anthropic-version": "2023-06-01"}

    def test_fallback_on_missing_auth_fn(self):
        provider = SimpleNamespace()  # no _auth_header_fn
        result = _build_auth_override(provider, "brettin")
        assert result == {"Authorization": "Bearer brettin"}

    def test_preserves_username_exactly(self):
        provider = SimpleNamespace(
            _auth_header_fn=lambda k: {"Authorization": f"Bearer {k}"}
        )
        result = _build_auth_override(provider, "user-with-dashes_and_123")
        assert result["Authorization"] == "Bearer user-with-dashes_and_123"
