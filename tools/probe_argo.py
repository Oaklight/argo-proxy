"""ARGO per-model capability probe.

This script POSTs a matrix of (model, endpoint, variant) requests against the
ARGO native endpoints and records the upstream response so that we can:

1. Verify the per-model constraints documented in ``argo-api-doc.pdf``.
2. Produce a reproducible evidence file backing the capability table that
   will live in ``llm-rosetta`` shims.

It is intentionally stdlib-only so it can be dropped onto any host that has
direct ARGO network access (e.g. lambda5) without needing the argo-proxy
virtual environment.

Usage::

    python tools/probe_argo.py --username <ANL_USER> \
        --env prod \
        --out-dir tools/argo_probe_out

Outputs (under ``--out-dir``)::

    argo_probe_raw.jsonl       # one line per (model, variant) call
    argo_capability_matrix.md  # human-readable summary table

The script never sends real prompt text beyond a single ``"ping"`` user
message, and it caps response body capture at 600 characters per call.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Iterable

# ----------------------------------------------------------------------------
# Endpoint base URLs
# ----------------------------------------------------------------------------

ENV_BASES: dict[str, str] = {
    "prod": "https://apps.inside.anl.gov/argoapi",
    "dev": "https://apps-dev.inside.anl.gov/argoapi",
    "test": "https://apps-test.inside.anl.gov/argoapi",
}

# ARGO native endpoints (relative to base)
ANTHROPIC_PATH = "/v1/messages"
OPENAI_CHAT_PATH = "/v1/chat/completions"

# Maximum captured response body length per call
BODY_CAPTURE_LIMIT = 600

# ----------------------------------------------------------------------------
# Model registry — keep aligned with argo-api-doc.pdf (2026-05-20)
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelSpec:
    """Describes a single ARGO model under probe."""

    internal_id: str
    family: str  # "anthropic" | "openai" | "google"
    deprecated: bool = False


CURRENT_MODELS: list[ModelSpec] = [
    # Anthropic family (POST /v1/messages)
    ModelSpec("claudeopus47", "anthropic"),
    ModelSpec("claudeopus46", "anthropic"),
    ModelSpec("claudeopus45", "anthropic"),
    ModelSpec("claudeopus41", "anthropic"),
    ModelSpec("claudesonnet46", "anthropic"),
    ModelSpec("claudesonnet45", "anthropic"),
    ModelSpec("claudehaiku45", "anthropic"),
    # OpenAI family (POST /v1/chat/completions)
    ModelSpec("gpt4o", "openai"),
    ModelSpec("gpto3mini", "openai"),
    ModelSpec("gpto3", "openai"),
    ModelSpec("gpto4mini", "openai"),
    ModelSpec("gpt41", "openai"),
    ModelSpec("gpt41mini", "openai"),
    ModelSpec("gpt5", "openai"),
    ModelSpec("gpt5mini", "openai"),
    ModelSpec("gpt55", "openai"),
    # Google family (POST /v1/chat/completions, OpenAI-compatible shape)
    ModelSpec("gemini25pro", "google"),
    ModelSpec("gemini25flash", "google"),
]

DEPRECATED_MODELS: list[ModelSpec] = [
    ModelSpec("claudesonnet4", "anthropic", deprecated=True),
    ModelSpec("claudesonnet37", "anthropic", deprecated=True),
    ModelSpec("claudesonnet35v2", "anthropic", deprecated=True),
    ModelSpec("claudehaiku35", "anthropic", deprecated=True),
    ModelSpec("gpt4olatest", "openai", deprecated=True),
    ModelSpec("gpto1", "openai", deprecated=True),
    ModelSpec("gpto1mini", "openai", deprecated=True),
    ModelSpec("gpt4turbo", "openai", deprecated=True),
    ModelSpec("gpt4", "openai", deprecated=True),
    ModelSpec("gpt4large", "openai", deprecated=True),
    ModelSpec("gpt35", "openai", deprecated=True),
    ModelSpec("gpt35large", "openai", deprecated=True),
]


# ----------------------------------------------------------------------------
# Variants
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Variant:
    """A single probe variant: a label + a body mutator."""

    label: str
    description: str
    # Function that returns extra fields to merge into the base body.
    extra: dict[str, Any] = field(default_factory=dict)
    # If set, REMOVE these keys from the base body before sending.
    drop: tuple[str, ...] = ()


def anthropic_variants() -> list[Variant]:
    """Variants exercised against /v1/messages."""

    return [
        Variant("baseline", "minimal valid body with max_tokens=64"),
        Variant(
            "thinking_enabled",
            "thinking={type: enabled, budget_tokens: 1024}",
            extra={"thinking": {"type": "enabled", "budget_tokens": 1024}},
        ),
        Variant(
            "thinking_adaptive_nobudget",
            "thinking={type: adaptive} (no budget)",
            extra={"thinking": {"type": "adaptive"}},
        ),
        Variant(
            "thinking_adaptive_withbudget",
            "thinking={type: adaptive, budget_tokens: 1024}",
            extra={"thinking": {"type": "adaptive", "budget_tokens": 1024}},
        ),
        Variant(
            "thinking_disabled",
            "thinking={type: disabled}",
            extra={"thinking": {"type": "disabled"}},
        ),
        # opus47 surfaces `output_config.effort` via 400 error messages;
        # probe each plausible effort value to map the legal enum.
        Variant(
            "output_config_effort_low",
            "output_config={effort: low}",
            extra={"output_config": {"effort": "low"}},
        ),
        Variant(
            "output_config_effort_medium",
            "output_config={effort: medium}",
            extra={"output_config": {"effort": "medium"}},
        ),
        Variant(
            "output_config_effort_high",
            "output_config={effort: high}",
            extra={"output_config": {"effort": "high"}},
        ),
        Variant(
            "output_config_effort_none",
            "output_config={effort: none}",
            extra={"output_config": {"effort": "none"}},
        ),
        Variant(
            "output_config_effort_minimal",
            "output_config={effort: minimal}",
            extra={"output_config": {"effort": "minimal"}},
        ),
        Variant(
            "output_config_effort_with_adaptive",
            "thinking=adaptive + output_config.effort=high",
            extra={
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": "high"},
            },
        ),
        Variant(
            "temperature_only",
            "temperature=0.5 (no top_p)",
            extra={"temperature": 0.5},
        ),
        Variant(
            "top_p_only",
            "top_p=0.9 (no temperature)",
            extra={"top_p": 0.9},
        ),
        Variant(
            "temperature_and_top_p",
            "both temperature=0.5 and top_p=0.9",
            extra={"temperature": 0.5, "top_p": 0.9},
        ),
        Variant(
            "no_max_tokens",
            "drop max_tokens entirely",
            drop=("max_tokens",),
        ),
    ]


def openai_variants() -> list[Variant]:
    """Variants exercised against /v1/chat/completions."""

    return [
        Variant("baseline_max_tokens", "max_tokens=64 (legacy field)"),
        Variant(
            "max_completion_tokens_only",
            "max_completion_tokens=64, no max_tokens",
            extra={"max_completion_tokens": 64},
            drop=("max_tokens",),
        ),
        Variant(
            "both_token_limits",
            "both max_tokens=64 and max_completion_tokens=64",
            extra={"max_completion_tokens": 64},
        ),
        Variant(
            "temperature_zero",
            "temperature=0",
            extra={"temperature": 0.0},
        ),
        Variant(
            "temperature_half",
            "temperature=0.5",
            extra={"temperature": 0.5},
        ),
        Variant(
            "temperature_one",
            "temperature=1",
            extra={"temperature": 1.0},
        ),
        Variant(
            "temperature_two",
            "temperature=2 (out-of-range probe)",
            extra={"temperature": 2.0},
        ),
        Variant(
            "top_p_only",
            "top_p=0.9, no temperature",
            extra={"top_p": 0.9},
        ),
        Variant(
            "no_token_limit",
            "drop both max_tokens and max_completion_tokens",
            drop=("max_tokens",),
        ),
    ]


# ----------------------------------------------------------------------------
# Body builders
# ----------------------------------------------------------------------------


def build_anthropic_base_body(model: str, user: str) -> dict[str, Any]:
    """Build the minimal anthropic-native body."""

    return {
        "model": model,
        "user": user,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "ping"}],
    }


def build_openai_base_body(model: str, user: str) -> dict[str, Any]:
    """Build the minimal openai-compatible body."""

    return {
        "model": model,
        "user": user,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "ping"}],
    }


def apply_variant(base: dict[str, Any], variant: Variant) -> dict[str, Any]:
    """Return ``base`` with ``variant.drop`` removed and ``variant.extra`` merged."""

    body = {k: v for k, v in base.items() if k not in variant.drop}
    for k, v in variant.extra.items():
        body[k] = v
    return body


# ----------------------------------------------------------------------------
# HTTP client (stdlib)
# ----------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """One probe execution outcome."""

    model: str
    family: str
    endpoint: str
    variant: str
    description: str
    status: int | None
    error: str | None
    elapsed_ms: int
    body_snippet: str
    request_body: dict[str, Any]


def post_json(
    url: str,
    body: dict[str, Any],
    bearer: str,
    timeout: float,
    insecure: bool,
) -> tuple[int | None, str | None, str]:
    """POST a JSON body and return (status, error_message, body_text_truncated)."""

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {bearer}",
        },
    )

    ctx = None
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            return resp.status, None, text[:BODY_CAPTURE_LIMIT]
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return exc.code, exc.reason, text[:BODY_CAPTURE_LIMIT]
    except urllib.error.URLError as exc:
        return None, f"URLError: {exc.reason}", ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}", ""


# ----------------------------------------------------------------------------
# Probe runner
# ----------------------------------------------------------------------------


def probe_model(
    spec: ModelSpec,
    base_url: str,
    username: str,
    timeout: float,
    insecure: bool,
    delay_s: float,
) -> Iterable[ProbeResult]:
    """Yield results for every variant of one model."""

    if spec.family == "anthropic":
        url = base_url + ANTHROPIC_PATH
        base_body = build_anthropic_base_body(spec.internal_id, username)
        variants = anthropic_variants()
    else:
        url = base_url + OPENAI_CHAT_PATH
        base_body = build_openai_base_body(spec.internal_id, username)
        variants = openai_variants()

    for variant in variants:
        body = apply_variant(base_body, variant)
        t0 = time.monotonic()
        status, error, snippet = post_json(
            url, body, bearer=username, timeout=timeout, insecure=insecure
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        yield ProbeResult(
            model=spec.internal_id,
            family=spec.family,
            endpoint=url,
            variant=variant.label,
            description=variant.description,
            status=status,
            error=error,
            elapsed_ms=elapsed_ms,
            body_snippet=snippet,
            request_body=body,
        )
        if delay_s > 0:
            time.sleep(delay_s)


# ----------------------------------------------------------------------------
# Output writers
# ----------------------------------------------------------------------------


def write_jsonl(results: list[ProbeResult], path: Path) -> None:
    """Write all results as one JSON object per line."""

    with path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(
                json.dumps(
                    {
                        "model": r.model,
                        "family": r.family,
                        "endpoint": r.endpoint,
                        "variant": r.variant,
                        "description": r.description,
                        "status": r.status,
                        "error": r.error,
                        "elapsed_ms": r.elapsed_ms,
                        "body_snippet": r.body_snippet,
                        "request_body": r.request_body,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def classify_status(r: ProbeResult) -> str:
    """One-character summary for the markdown matrix."""

    if r.status is None:
        return "X"  # network error
    if 200 <= r.status < 300:
        return "OK"
    if r.status == 400:
        return "400"
    if r.status == 401:
        return "401"
    if r.status == 403:
        return "403"
    if r.status == 404:
        return "404"
    if 500 <= r.status < 600:
        return f"{r.status}"
    return str(r.status)


def write_matrix_markdown(results: list[ProbeResult], path: Path) -> None:
    """Write a human-friendly per-model variant matrix."""

    # Group by model preserving order.
    by_model: dict[str, list[ProbeResult]] = {}
    for r in results:
        by_model.setdefault(r.model, []).append(r)

    lines: list[str] = []
    lines.append("# ARGO capability matrix")
    lines.append("")
    lines.append(
        "Auto-generated by `tools/probe_argo.py`. Each cell is the HTTP status "
        "of one probe variant. `OK` = 2xx, otherwise the numeric status, or "
        "`X` for a transport-level failure."
    )
    lines.append("")
    lines.append(
        "See `argo_probe_raw.jsonl` next to this file for the full request "
        "body and truncated response body of every cell."
    )
    lines.append("")

    for model, rows in by_model.items():
        family = rows[0].family
        lines.append(f"## {model} ({family})")
        lines.append("")
        lines.append("| Variant | Status | Time (ms) | Description |")
        lines.append("|---|---|---|---|")
        for r in rows:
            lines.append(
                f"| `{r.variant}` | {classify_status(r)} | {r.elapsed_ms} | "
                f"{r.description} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Probe ARGO native endpoints for per-model parameter quirks. "
            "Writes a JSONL evidence file and a markdown capability matrix."
        )
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("ARGO_USER"),
        help=(
            "ANL domain username (used both as Bearer token and `user` field). "
            "Defaults to $ARGO_USER."
        ),
    )
    parser.add_argument(
        "--env",
        choices=sorted(ENV_BASES),
        default="prod",
        help="ARGO environment to target (default: prod).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the ARGO base URL entirely (takes precedence over --env).",
    )
    parser.add_argument(
        "--out-dir",
        default="tools/argo_probe_out",
        help="Directory to write outputs into (will be created).",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help=(
            "Restrict to these internal_ids. Default: every current model. "
            "Use --include-deprecated to enable deprecated ones too."
        ),
    )
    parser.add_argument(
        "--include-deprecated",
        action="store_true",
        help="Also probe deprecated models from DEPRECATED_MODELS.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Sleep between requests in seconds (default: 0.5).",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS verification (only use for staging/test envs).",
    )
    return parser.parse_args(argv)


def select_models(
    args: argparse.Namespace,
) -> list[ModelSpec]:
    """Filter the model list per CLI args."""

    pool = list(CURRENT_MODELS)
    if args.include_deprecated:
        pool.extend(DEPRECATED_MODELS)
    if args.models:
        wanted = set(args.models)
        pool = [m for m in pool if m.internal_id in wanted]
        missing = wanted - {m.internal_id for m in pool}
        if missing:
            print(
                f"warning: unknown model ids ignored: {sorted(missing)}",
                file=sys.stderr,
            )
    return pool


def main(argv: list[str] | None = None) -> int:
    """Script entry point."""

    args = parse_args(argv)

    if not args.username:
        print(
            "error: --username (or ARGO_USER env var) is required",
            file=sys.stderr,
        )
        return 2

    base_url = (args.base_url or ENV_BASES[args.env]).rstrip("/")
    models = select_models(args)
    if not models:
        print("error: no models selected", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "argo_probe_raw.jsonl"
    matrix_path = out_dir / "argo_capability_matrix.md"

    print(
        f"probing {len(models)} model(s) against {base_url} as user={args.username}",
        file=sys.stderr,
    )

    results: list[ProbeResult] = []
    for spec in models:
        print(f"  -> {spec.internal_id} ({spec.family})", file=sys.stderr)
        for r in probe_model(
            spec,
            base_url=base_url,
            username=args.username,
            timeout=args.timeout,
            insecure=args.insecure,
            delay_s=args.delay,
        ):
            status_repr = r.status if r.status is not None else r.error
            print(
                f"      {r.variant:35s} -> {status_repr}",
                file=sys.stderr,
            )
            results.append(r)

    write_jsonl(results, jsonl_path)
    write_matrix_markdown(results, matrix_path)

    print(
        f"\nwrote {len(results)} results to:\n  {jsonl_path}\n  {matrix_path}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
