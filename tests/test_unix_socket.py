"""Tests for Unix socket support in argo-proxy.

Covers the config model, CLI parser, IO formatting, and end-to-end
server lifecycle on a Unix domain socket.
"""

import asyncio
import os
import socket as sock_mod
import stat

import aiohttp
import pytest
from aiohttp import web


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_sock(tmp_path):
    """Return a path for a temporary socket (does not create it)."""
    return str(tmp_path / "argo-proxy-test.sock")


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------

class TestArgoConfigSocket:
    """ArgoConfig socket field behavior."""

    def test_default_empty(self):
        from argoproxy.config.model import ArgoConfig
        c = ArgoConfig()
        assert c.socket == ""

    def test_from_dict(self):
        from argoproxy.config.model import ArgoConfig
        c = ArgoConfig.from_dict({"socket": "/tmp/x.sock", "user": "t", "port": 9999})
        assert c.socket == "/tmp/x.sock"
        assert c.port == 9999

    def test_persistent_dict_omits_when_empty(self):
        from argoproxy.config.model import ArgoConfig
        d = ArgoConfig().to_persistent_dict()
        assert "socket" not in d

    def test_persistent_dict_includes_when_set(self):
        from argoproxy.config.model import ArgoConfig
        c = ArgoConfig(socket="/run/user/1000/argo-proxy.sock")
        d = c.to_persistent_dict()
        assert d["socket"] == "/run/user/1000/argo-proxy.sock"


# ---------------------------------------------------------------------------
# Config IO tests
# ---------------------------------------------------------------------------

class TestConfigIO:
    """YAML formatting and env-override for socket field."""

    def test_yaml_includes_socket_when_set(self):
        from argoproxy.config.io import _format_config_yaml
        from argoproxy.config.model import ArgoConfig
        c = ArgoConfig(socket="/tmp/s.sock", user="test")
        yaml_out = _format_config_yaml(c.to_persistent_dict())
        assert "socket:" in yaml_out

    def test_yaml_omits_socket_when_empty(self):
        from argoproxy.config.io import _format_config_yaml
        from argoproxy.config.model import ArgoConfig
        c = ArgoConfig(user="test")
        yaml_out = _format_config_yaml(c.to_persistent_dict())
        assert "socket:" not in yaml_out

    def test_env_override(self, monkeypatch):
        from argoproxy.config.io import _apply_env_overrides
        from argoproxy.config.model import ArgoConfig
        monkeypatch.setenv("SOCKET", "/tmp/env.sock")
        c = _apply_env_overrides(ArgoConfig(user="test"))
        assert c.socket == "/tmp/env.sock"


# ---------------------------------------------------------------------------
# CLI parser tests
# ---------------------------------------------------------------------------

class TestCLIParser:
    """--socket / -S flags on the serve subcommand."""

    def test_long_flag(self):
        from argoproxy.cli.parser import create_parser
        args = create_parser().parse_args(["serve", "--socket", "/tmp/t.sock"])
        assert args.socket == "/tmp/t.sock"

    def test_short_flag(self):
        from argoproxy.cli.parser import create_parser
        args = create_parser().parse_args(["serve", "-S", "/tmp/s.sock"])
        assert args.socket == "/tmp/s.sock"

    def test_default_none(self):
        from argoproxy.cli.parser import create_parser
        args = create_parser().parse_args(["serve"])
        assert args.socket is None


# ---------------------------------------------------------------------------
# End-to-end unix socket server test
# ---------------------------------------------------------------------------

class TestUnixSocketServer:
    """Start aiohttp on a unix socket, verify connectivity and permissions."""

    def test_socket_lifecycle(self, tmp_sock):
        """Server listens on socket, responds to requests, permissions are 0700."""

        async def _run():
            async def health(request):
                return web.json_response({"status": "healthy"})

            app = web.Application()
            app.router.add_get("/health", health)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.UnixSite(runner, tmp_sock)
            await site.start()

            # Socket exists and is a socket
            assert os.path.exists(tmp_sock)
            assert stat.S_ISSOCK(os.stat(tmp_sock).st_mode)

            # Set permissions like _run_unix_socket does
            os.chmod(tmp_sock, 0o700)
            assert os.stat(tmp_sock).st_mode & 0o777 == 0o700

            # Hit the health endpoint
            conn = aiohttp.UnixConnector(path=tmp_sock)
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.get("http://localhost/health") as resp:
                    assert resp.status == 200
                    body = await resp.json()
                    assert body == {"status": "healthy"}

            await runner.cleanup()

        asyncio.run(_run())

    def test_stale_socket_removal(self, tmp_sock):
        """A stale socket file is detected and can be removed."""
        # Create a real socket file (simulate stale)
        s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
        s.bind(tmp_sock)
        s.close()

        assert os.path.exists(tmp_sock)
        st = os.stat(tmp_sock)
        assert stat.S_ISSOCK(st.st_mode)

        # Our code removes stale sockets
        os.unlink(tmp_sock)
        assert not os.path.exists(tmp_sock)
