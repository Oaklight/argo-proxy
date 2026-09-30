#!/usr/bin/env python3
"""Probe which ARGO models serve the native Responses API.

Goes straight at the ARGO upstream over urllib — no argo-proxy in the
path — and asks one question per model: does POST {base}/v1/responses
work?

For every model that does NOT work, a control request is sent to
/v1/chat/completions so we can tell "Responses unsupported for this
model" apart from "this slug is wrong / model is gone".

Usage:
    python tools/probe_responses.py                 # all current models
    python tools/probe_responses.py --models gpt5 gpt41
    python tools/probe_responses.py --include-deprecated
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_argo import (  # noqa: E402
    CURRENT_MODELS,
    DEPRECATED_MODELS,
    ENV_BASES,
    ModelSpec,
    post_json,
)

RESPONSES_PATH = "/v1/responses"
CHAT_PATH = "/v1/chat/completions"
MESSAGES_PATH = "/v1/messages"

# Some models 500 on a very small budget (gemini 500s at 16, 200s at 64),
# so the control request uses a budget known to be safe from the Phase 0a run.
CONTROL_MAX_TOKENS = 64

CONFIG_CANDIDATES = (
    "./config.yaml",
    os.path.expanduser("~/.config/argoproxy/config.yaml"),
    os.path.expanduser("~/.argoproxy/config.yaml"),
)


def config_defaults() -> tuple[str | None, str | None]:
    """Read (user, argo_base_url) from argo-proxy's own config, if present."""
    try:
        import yaml
    except ImportError:
        return None, None
    for path in CONFIG_CANDIDATES:
        if os.path.exists(path):
            try:
                with open(path) as fh:
                    data = yaml.safe_load(fh) or {}
                return data.get("user"), data.get("argo_base_url")
            except Exception:
                continue
    return None, None


@dataclass
class Row:
    model: str
    family: str
    responses_status: int | None
    responses_error: str | None
    responses_body: str
    chat_status: int | None = None
    control_path: str = ""
    verdict: str = ""


def responses_body(model: str, user: str) -> dict[str, Any]:
    """Minimal Responses API request — smallest legal output budget."""
    return {
        "model": model,
        "user": user,
        "input": "ping",
        "max_output_tokens": 16,
    }


def control_request(spec: ModelSpec, user: str) -> tuple[str, dict[str, Any]]:
    """Control call proving the model itself is alive on its own endpoint.

    Anthropic models are served from /v1/messages, everything else from
    the OpenAI-compatible /v1/chat/completions.
    """
    path = MESSAGES_PATH if spec.family == "anthropic" else CHAT_PATH
    return path, {
        "model": spec.internal_id,
        "user": user,
        "max_tokens": CONTROL_MAX_TOKENS,
        "messages": [{"role": "user", "content": "ping"}],
    }


def classify(row: Row) -> str:
    """Turn (responses_status, chat_status) into a verdict."""
    rs = row.responses_status
    if rs == 200:
        return "NATIVE"
    if rs in (404, 405):
        return "NO ENDPOINT"
    if row.chat_status == 200:
        # Model is alive on its own endpoint, but not on /v1/responses
        return f"NOT ON RESPONSES ({rs})"
    if row.chat_status is not None and row.chat_status != 200:
        return f"MODEL BROKEN (control {row.chat_status})"
    return f"UNKNOWN ({rs})"


def probe(
    specs: list[ModelSpec],
    base_url: str,
    user: str,
    timeout: float,
    insecure: bool,
    delay_s: float,
) -> list[Row]:
    rows: list[Row] = []
    for spec in specs:
        m = spec.internal_id
        status, error, snippet = post_json(
            base_url + RESPONSES_PATH,
            responses_body(m, user),
            bearer=user,
            timeout=timeout,
            insecure=insecure,
        )
        row = Row(m, spec.family, status, error, snippet)

        if status != 200:
            c_path, c_body = control_request(spec, user)
            c_status, _, _ = post_json(
                base_url + c_path,
                c_body,
                bearer=user,
                timeout=timeout,
                insecure=insecure,
            )
            row.chat_status = c_status
            row.control_path = c_path

        row.verdict = classify(row)
        rows.append(row)
        print(f"  {m:<14} {row.verdict}", flush=True)
        if delay_s > 0:
            time.sleep(delay_s)
    return rows


def report(rows: list[Row], base_url: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    native = [r for r in rows if r.verdict == "NATIVE"]

    lines = [
        "# ARGO native Responses API — model support probe",
        "",
        f"Endpoint: `POST {base_url}{RESPONSES_PATH}`  ",
        f"Result: **{len(native)} of {len(rows)} models** serve Responses natively.",
        "",
        "| model | family | /v1/responses | control endpoint | verdict |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        chat = (
            f"{r.chat_status} (`{r.control_path}`)"
            if r.chat_status is not None
            else "— (not needed)"
        )
        lines.append(
            f"| `{r.model}` | {r.family} | {r.responses_status} | {chat} | {r.verdict} |"
        )

    failures = [r for r in rows if r.verdict != "NATIVE" and r.responses_body]
    if failures:
        lines += ["", "## Upstream error bodies", ""]
        for r in failures:
            lines.append(f"**`{r.model}`** ({r.responses_status})")
            lines.append("")
            lines.append("```")
            lines.append(r.responses_body.strip()[:500] or "(empty)")
            lines.append("```")
            lines.append("")

    md = out_dir / "responses_support.md"
    md.write_text("\n".join(lines) + "\n")

    jsonl = out_dir / "responses_support.jsonl"
    with jsonl.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r.__dict__) + "\n")

    print(f"\nWrote {md}\n      {jsonl}")


def main(argv: list[str] | None = None) -> int:
    cfg_user, cfg_base = config_defaults()

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--username", default=os.environ.get("ARGO_USER") or cfg_user)
    p.add_argument("--env", choices=sorted(ENV_BASES), default="prod")
    p.add_argument("--base-url", default=cfg_base)
    p.add_argument("--models", nargs="*", default=None)
    p.add_argument("--include-deprecated", action="store_true")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--delay", type=float, default=0.0)
    p.add_argument("--insecure", action="store_true")
    p.add_argument("--out-dir", default="tools/argo_probe_out")
    args = p.parse_args(argv)

    if not args.username:
        p.error("no username: pass --username, set $ARGO_USER, or configure argo-proxy")

    base_url = (args.base_url or ENV_BASES[args.env]).rstrip("/")

    pool = list(CURRENT_MODELS)
    if args.include_deprecated:
        pool += list(DEPRECATED_MODELS)
    if args.models:
        wanted = set(args.models)
        pool = [s for s in pool if s.internal_id in wanted]
        missing = wanted - {s.internal_id for s in pool}
        for m in sorted(missing):
            pool.append(ModelSpec(m, "unknown"))

    print(f"Probing {base_url}{RESPONSES_PATH} — {len(pool)} models\n")
    rows = probe(pool, base_url, args.username, args.timeout, args.insecure, args.delay)
    report(rows, base_url, Path(args.out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
