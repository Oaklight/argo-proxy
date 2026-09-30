"""Tests for _apply_identity — body `user` handling on the proxy path."""

from argoproxy.app import _apply_identity


class TestApplyIdentity:
    def test_sets_user_when_absent(self):
        body = {"model": "gpt5", "input": "hi"}
        _apply_identity(body, "brettin", "openai")
        assert body["user"] == "brettin"

    def test_overwrites_client_supplied_user(self):
        """Defaulting would leave the spoofed value."""
        body = {"model": "gpt5", "user": "someone-else"}
        _apply_identity(body, "brettin", "openai")
        assert body["user"] == "brettin"

    def test_overwrites_on_the_responses_route(self):
        body = {"model": "gpt5", "user": "someone-else", "input": []}
        _apply_identity(body, "brettin", "openai_responses")
        assert body["user"] == "brettin"

    def test_anthropic_target_gets_metadata_not_user(self):
        body = {"model": "claudeopus4.6", "messages": []}
        _apply_identity(body, "brettin", "anthropic")
        assert body["metadata"]["user_id"] == "brettin"
        assert "user" not in body

    def test_anthropic_target_overwrites_client_user_id(self):
        body = {"model": "claudeopus4.6", "metadata": {"user_id": "someone-else"}}
        _apply_identity(body, "brettin", "anthropic")
        assert body["metadata"]["user_id"] == "brettin"

    def test_anthropic_target_tolerates_non_dict_metadata(self):
        body = {"model": "claudeopus4.6", "metadata": "nonsense"}
        _apply_identity(body, "brettin", "anthropic")
        assert body["metadata"] == "nonsense"

    def test_leaves_other_fields_alone(self):
        body = {"model": "gpt5", "input": "hi", "temperature": 0.5}
        _apply_identity(body, "brettin", "openai")
        assert body["model"] == "gpt5"
        assert body["input"] == "hi"
        assert body["temperature"] == 0.5
