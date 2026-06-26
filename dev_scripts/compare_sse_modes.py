#!/usr/bin/env python3
"""Capture SSE events from argo-proxy for passthrough vs force-conversion comparison.

Sends an Anthropic Messages API streaming request and captures all SSE events
as JSON Lines, suitable for diffing between modes.

Usage:
    python dev_scripts/compare_sse_modes.py
    python dev_scripts/compare_sse_modes.py --output /tmp/passthrough.jsonl
    python dev_scripts/compare_sse_modes.py --base-url http://127.0.0.1:44510

Full comparison workflow:
    # Terminal 1: mock upstream
    python dev_scripts/mock_anthropic_sse.py

    # Terminal 2: argo-proxy (passthrough)
    argo-proxy serve config.test.yaml

    # Terminal 3: capture
    python dev_scripts/compare_sse_modes.py -o /tmp/passthrough.jsonl

    # Restart argo-proxy with --force-conversion, then:
    python dev_scripts/compare_sse_modes.py -o /tmp/force_conversion.jsonl

    # Compare
    diff /tmp/passthrough.jsonl /tmp/force_conversion.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:44510"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
API_KEY = "test-key"


def capture_sse_events(base_url: str, model: str) -> list[dict]:
    """Send a streaming request and capture all SSE events."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": model,
        "max_tokens": 100,
        "stream": True,
        "messages": [{"role": "user", "content": "Say hello"}],
    }

    events: list[dict] = []
    current_event_type: str | None = None

    with httpx.stream(
        "POST",
        f"{base_url}/v1/messages",
        headers=headers,
        json=body,
        timeout=30.0,
    ) as resp:
        if resp.status_code != 200:
            print(f"Error: HTTP {resp.status_code}", file=sys.stderr)
            print(resp.read().decode(), file=sys.stderr)
            sys.exit(1)

        for line in resp.iter_lines():
            if not line:
                continue

            if line.startswith("event: "):
                current_event_type = line[7:].strip()
            elif line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = data_str

                events.append(
                    {
                        "event": current_event_type,
                        "type": data.get("type") if isinstance(data, dict) else None,
                        "data": data,
                    }
                )
                current_event_type = None

    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture SSE events from argo-proxy")
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL, help="argo-proxy base URL"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument(
        "-o", "--output", default=None, help="Output file (default: stdout)"
    )
    args = parser.parse_args()

    events = capture_sse_events(args.base_url, args.model)

    output = sys.stdout
    if args.output:
        output = open(args.output, "w", encoding="utf-8")

    try:
        for event in events:
            output.write(json.dumps(event, ensure_ascii=False) + "\n")
    finally:
        if output is not sys.stdout:
            output.close()

    # Summary to stderr
    print(f"\nCaptured {len(events)} SSE events", file=sys.stderr)
    for i, e in enumerate(events):
        print(f"  [{i}] event={e['event']!r}  type={e['type']!r}", file=sys.stderr)


if __name__ == "__main__":
    main()
