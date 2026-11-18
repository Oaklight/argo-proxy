"""The launcher: what it refuses, what it writes, and what it must never do.

The three properties under test are the ones a shell script cannot guarantee:
no code path runs ``auth`` (so nothing here can block on an MFA prompt), the
tunnel URL lands on the Argo providers instead of the global ``server.proxy``,
and reading the model list is optional — a tunnel that answers refuses nothing
else, and a failed fetch degrades to the configured default instead of an
empty table.
"""

from __future__ import annotations

import json
from typing import Any
from collections.abc import Sequence

import pytest

from argoproxy import launcher
from argoproxy.launcher import (
    PROVIDER_FORMATS,
    LauncherError,
    LauncherSettings,
    ensure_tunnel,
    fetch_models,
    load_argo_config,
    main,
    render_gateway_config,
    routes_for,
    settings_from,
    tunnel_state,
    write_gateway_config,
)


class FakeRunner:
    """Answers each call from a script, recording the argv it was given."""

    def __init__(self, results: Sequence[tuple[int, str, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._results = list(results or [])

    def __call__(self, argv: Sequence[str]) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        return self._results.pop(0) if self._results else (0, "", "")


def _status(
    state: str, proxy: str = "socks5://127.0.0.1:10801"
) -> tuple[int, str, str]:
    payload = json.dumps({"state": state, "proxy_url": proxy})
    return (0 if state == "forwarding" else 1), payload, ""


def _args(**overrides: Any):
    parser = launcher._build_parser()
    argv: list[str] = []
    for key, value in overrides.items():
        if value is True:
            argv.append(f"--{key.replace('_', '-')}")
        else:
            argv += [f"--{key.replace('_', '-')}", str(value)]
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Tunnel
# ---------------------------------------------------------------------------


def test_a_forwarding_tunnel_is_used_as_is():
    runner = FakeRunner([_status("forwarding")])
    assert ensure_tunnel("t", run=runner) == "socks5://127.0.0.1:10801"
    assert runner.calls == [["t", "status", "--json"]]


def test_an_idle_tunnel_is_started_and_re_probed():
    runner = FakeRunner([_status("idle"), (0, "", ""), _status("forwarding")])
    assert ensure_tunnel("t", run=runner) == "socks5://127.0.0.1:10801"
    assert runner.calls[1] == ["t", "start"]


def test_an_absent_master_names_auth_and_never_runs_it():
    runner = FakeRunner([_status("absent")])
    with pytest.raises(LauncherError) as caught:
        ensure_tunnel("t", run=runner)
    assert "t auth" in (caught.value.hint or "")
    # The only command run was the probe: a launcher may not prompt.
    assert runner.calls == [["t", "status", "--json"]]


def test_a_wedged_master_is_read_before_anything_is_run():
    """``wedged`` means the socket answers to nobody, or another process holds
    the port.  Either way the launcher cannot repair it and must not guess:
    the hint sends the operator to ``status``, which names the process."""
    runner = FakeRunner([_status("wedged")])
    with pytest.raises(LauncherError) as caught:
        ensure_tunnel("t", run=runner)
    assert "status" in (caught.value.hint or "")
    assert runner.calls == [["t", "status", "--json"]]


def test_the_launcher_drives_the_argo_tunnel_script():
    assert launcher.DEFAULT_TUNNEL_COMMAND == "argo-tunnel"


def test_a_tunnel_cli_that_cannot_run_reads_as_absent():
    assert tunnel_state("t", FakeRunner([(127, "", "not found")]))["state"] == "absent"


def test_unparseable_status_output_reads_as_absent():
    assert tunnel_state("t", FakeRunner([(0, "not json", "")]))["state"] == "absent"


# ---------------------------------------------------------------------------
# main(): what it refuses before it execs
# ---------------------------------------------------------------------------


def test_main_refuses_before_rendering_when_the_master_is_absent(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("ARGO_PROXY_GATEWAY", "gateway")
    monkeypatch.setenv("ARGO_PROXY_TUNNEL", "tunnel")
    monkeypatch.setattr(
        launcher,
        "ensure_tunnel",
        lambda *_a, **_k: (_ for _ in ()).throw(
            LauncherError("no master", hint="tunnel auth")
        ),
    )
    assert main(["--gateway-config", str(tmp_path / "g.json")]) == 1
    assert "tunnel auth" in capsys.readouterr().err
    assert not (tmp_path / "g.json").exists()


def test_main_renders_and_reports_in_a_dry_run(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ARGO_PROXY_GATEWAY", "gateway")
    monkeypatch.setenv("ARGO_PROXY_TUNNEL", "tunnel")
    monkeypatch.setattr(
        launcher, "ensure_tunnel", lambda *_a, **_k: "socks5://127.0.0.1:10801"
    )
    monkeypatch.setattr(
        launcher, "fetch_models", lambda settings, **_k: (["argo:gpt-5-nano"], {})
    )
    target = tmp_path / "g.json"

    assert (
        main(["--user", "someone", "--gateway-config", str(target), "--dry-run"]) == 0
    )
    written = json.loads(target.read_text())
    assert written["providers"]["argo-chat"]["proxy"] == "socks5://127.0.0.1:10801"
    assert "argo:gpt-5-nano" in written["models"]
    assert "--config" in capsys.readouterr().out


def test_a_failed_model_fetch_falls_back_to_one_default_model(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setenv("ARGO_PROXY_GATEWAY", "gateway")
    monkeypatch.setitem(__import__("os").environ, "ARGO_PROXY_TUNNEL", "tunnel")
    monkeypatch.setattr(
        launcher, "ensure_tunnel", lambda *_a, **_k: "socks5://127.0.0.1:10801"
    )

    def refuse(settings, **_k):
        raise LauncherError("upstream said 503")

    monkeypatch.setattr(launcher, "fetch_models", refuse)
    target = tmp_path / "g.json"
    assert (
        main(["--user", "someone", "--gateway-config", str(target), "--dry-run"]) == 0
    )
    written = json.loads(target.read_text())
    assert list(written["models"]) == ["argo:gpt-5.4-nano"]
    assert "upstream said 503" in capsys.readouterr().err


def test_no_tunnel_skips_the_tunnel_cli_entirely(monkeypatch, tmp_path):
    monkeypatch.setenv("ARGO_PROXY_GATEWAY", "gateway")
    monkeypatch.setenv("ARGO_PROXY_TUNNEL", "should-not-run")
    monkeypatch.setattr(
        launcher,
        "fetch_models",
        lambda settings, **_k: (_ for _ in ()).throw(LauncherError("offline")),
    )
    target = tmp_path / "g.json"
    assert (
        main(
            [
                "--user",
                "someone",
                "--no-tunnel",
                "--gateway-config",
                str(target),
                "--dry-run",
            ]
        )
        == 0
    )
    written = json.loads(target.read_text())
    assert all("proxy" not in p for p in written["providers"].values())


# ---------------------------------------------------------------------------
# Config rendering
# ---------------------------------------------------------------------------


def test_every_argo_lane_is_declared_per_model():
    table = routes_for(
        ["argo:claude-opus-5"], {"argo:claude-opus-5": "claudeopus5"}, None
    )
    names = [p["name"] for p in table["argo:claude-opus-5"]["providers"]]
    assert names == list(PROVIDER_FORMATS)
    assert (
        table["argo:claude-opus-5"]["providers"][0]["upstream_model"] == "claudeopus5"
    )


def test_a_model_without_a_mapping_is_its_own_upstream():
    table = routes_for(["plain"], {}, None)
    assert table["plain"]["providers"][0]["upstream_model"] == "plain"


def test_the_proxy_is_per_provider_not_global():
    settings = LauncherSettings(user="u", proxy_url="socks5://127.0.0.1:10801")
    document = render_gateway_config(settings, ["m"])
    assert "proxy" not in document["server"]
    for provider in document["providers"].values():
        assert provider["proxy"] == "socks5://127.0.0.1:10801"


def test_no_tunnel_means_no_proxy_anywhere():
    document = render_gateway_config(LauncherSettings(user="u", proxy_url=None), ["m"])
    assert "proxy" not in document["server"]
    assert all("proxy" not in p for p in document["providers"].values())


def test_the_shim_preset_is_declared_unless_a_path_overrides_it():
    preset = render_gateway_config(LauncherSettings(user="u"), ["m"])
    assert preset["shims"] == {"presets": ["argo"]}
    local = render_gateway_config(
        LauncherSettings(user="u", shims_path="/opt/shims"), ["m"]
    )
    assert local["shims"] == {"paths": ["/opt/shims"]}


def test_the_rendered_document_loads_as_json(tmp_path):
    path = write_gateway_config({"a": 1}, tmp_path / "nested" / "g.json")
    assert json.loads(path.read_text()) == {"a": 1}


# ---------------------------------------------------------------------------
# Config precedence
# ---------------------------------------------------------------------------


def test_the_command_line_beats_the_environment_beats_the_file(monkeypatch):
    monkeypatch.setenv("PORT", "1111")
    argo = {"port": 2222, "user": "from-file"}
    settings = settings_from(argo, _args(port=3333), proxy_url=None)
    assert settings.port == 3333
    assert settings_from(argo, _args(), proxy_url=None).port == 1111
    monkeypatch.delenv("PORT")
    assert settings_from(argo, _args(), proxy_url=None).port == 2222


def test_a_missing_account_is_refused_with_a_hint(monkeypatch):
    monkeypatch.delenv("ARGO_USER", raising=False)
    with pytest.raises(LauncherError) as caught:
        settings_from({}, _args(), proxy_url=None)
    assert "--user" in (caught.value.hint or "")


def test_a_bad_port_is_refused():
    with pytest.raises(LauncherError):
        settings_from({"user": "u", "port": "abc"}, _args(), proxy_url=None)


def test_a_missing_config_file_is_not_an_error(tmp_path):
    assert load_argo_config(str(tmp_path / "nope.yaml")) == {}


def test_an_unreadable_config_file_is_refused(tmp_path):
    """A file that is not UTF-8 is the case the vendored parser cannot absorb:
    it is lenient about YAML syntax, strict about decoding."""
    bad = tmp_path / "config.yaml"
    bad.write_bytes(b"\xff\xfe\x00not utf-8")
    with pytest.raises(LauncherError) as caught:
        load_argo_config(str(bad))
    assert "cannot parse" in str(caught.value)


def test_an_empty_file_is_an_empty_config(tmp_path):
    empty = tmp_path / "config.yaml"
    empty.write_text("")
    assert load_argo_config(str(empty)) == {}


def test_a_yaml_sequence_is_not_a_config(tmp_path):
    seq = tmp_path / "config.yaml"
    seq.write_text("- a\n- b\n")
    assert load_argo_config(str(seq)) == {}


# ---------------------------------------------------------------------------
# Model fetch
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        return self._body


def test_the_slug_rule_matches_the_shim_package_when_it_is_installed():
    """The launcher mirrors the shim's transform; a divergence would route to
    an id the upstream does not know."""
    shim_utils = pytest.importorskip("llm_rosetta_shim_argo.providers.argo.model_utils")
    entries = [
        {"id": "Claude Opus 5", "internal_id": "claudeopus5"},
        {"id": "GPT-5 Nano", "internal_id": "gpt5nano"},
        {"id": "already-argo:slug"},
        {"id": "", "internal_id": "ignored"},
        {"id": "UPPER.Case Name", "internal_id": "uc"},
    ]
    assert launcher._slug_entries(entries) == shim_utils.model_list_transform(entries)


def test_the_launcher_still_reads_models_without_the_shim_package(monkeypatch):
    """The shim package needs a newer core than the current pin allows, so the
    launcher must not depend on it."""
    monkeypatch.setattr(
        launcher, "_model_list_transform", lambda: launcher._slug_entries
    )
    monkeypatch.setattr(
        "llm_rosetta_gateway._vendor.httpclient.get",
        lambda url, **kw: _FakeResponse(
            200, {"data": [{"id": "Claude Opus 5", "internal_id": "claudeopus5"}]}
        ),
    )
    names, upstream = fetch_models(
        LauncherSettings(user="u", models_url="https://x/models")
    )
    assert names == ["argo:claude-opus-5"]
    assert upstream == {"argo:claude-opus-5": "claudeopus5"}


def test_the_model_list_is_read_through_the_tunnel(monkeypatch):
    seen: dict[str, Any] = {}

    def fake_get(url, **kwargs):
        seen.update(url=url, **kwargs)
        return _FakeResponse(
            200,
            {"data": [{"id": "Claude Opus 5", "internal_id": "claudeopus5"}]},
        )

    monkeypatch.setattr(
        "llm_rosetta_gateway._vendor.httpclient.get", fake_get, raising=True
    )
    settings = LauncherSettings(
        user="u",
        models_url="https://apps.inside.anl.gov/argoapi/v1/models",
        proxy_url="socks5://127.0.0.1:10801",
    )
    names, upstream = fetch_models(settings)
    assert names == ["argo:claude-opus-5"]
    assert upstream == {"argo:claude-opus-5": "claudeopus5"}
    assert seen["proxy"] == "socks5://127.0.0.1:10801"
    assert seen["headers"]["Authorization"] == "Bearer u"


def test_a_refused_credential_is_an_error(monkeypatch):
    monkeypatch.setattr(
        "llm_rosetta_gateway._vendor.httpclient.get",
        lambda url, **kw: _FakeResponse(403, {}),
    )
    with pytest.raises(LauncherError) as caught:
        fetch_models(LauncherSettings(user="u", models_url="https://x/models"))
    assert "403" in str(caught.value)


def test_an_empty_list_is_an_error_rather_than_an_empty_router(monkeypatch):
    monkeypatch.setattr(
        "llm_rosetta_gateway._vendor.httpclient.get",
        lambda url, **kw: _FakeResponse(200, {"data": []}),
    )
    with pytest.raises(LauncherError) as caught:
        fetch_models(LauncherSettings(user="u", models_url="https://x/models"))
    assert "no models" in str(caught.value)


def test_a_transport_failure_names_the_url(monkeypatch):
    def boom(url, **kw):
        raise OSError("connection refused")

    monkeypatch.setattr("llm_rosetta_gateway._vendor.httpclient.get", boom)
    with pytest.raises(LauncherError) as caught:
        fetch_models(LauncherSettings(user="u", models_url="https://x/models"))
    assert "https://x/models" in str(caught.value)
