#!/usr/bin/env python3
"""Mock Anthropic SSE server for testing force_conversion behavior.

Returns a fixed Anthropic Messages API streaming response so that
passthrough vs force-conversion output can be compared deterministically.

Usage:
    python dev_scripts/mock_anthropic_sse.py          # default port 44500
    python dev_scripts/mock_anthropic_sse.py --port 44500
"""

from __future__ import annotations

import argparse
import asyncio
import json

from aiohttp import web

# Fixed Anthropic SSE events (realistic message_start → message_stop sequence)
MOCK_EVENTS: list[tuple[str, dict]] = [
    (
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_mock_001",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 12, "output_tokens": 1},
            },
        },
    ),
    (
        "content_block_start",
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        },
    ),
    ("ping", {"type": "ping"}),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": " "},
        },
    ),
    (
        "content_block_delta",
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "world!"},
        },
    ),
    (
        "content_block_stop",
        {"type": "content_block_stop", "index": 0},
    ),
    (
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
    ),
    (
        "message_stop",
        {"type": "message_stop"},
    ),
]


def _format_sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def handle_messages(request: web.Request) -> web.StreamResponse:
    """Handle POST /v1/messages — return fixed SSE stream."""
    body = await request.json()
    stream = body.get("stream", False)

    if not stream:
        # Non-streaming: return a simple aggregated response
        return web.json_response(
            {
                "id": "msg_mock_001",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-20250514",
                "content": [{"type": "text", "text": "Hello world!"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 5},
            }
        )

    # Streaming response
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    response.enable_chunked_encoding()
    await response.prepare(request)

    for event_type, data in MOCK_EVENTS:
        sse_text = _format_sse(event_type, data)
        await response.write(sse_text.encode("utf-8"))
        await asyncio.sleep(0.05)  # simulate realistic timing

    await response.write_eof()
    return response


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "type": "mock_anthropic_sse"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock Anthropic SSE server")
    parser.add_argument("--port", type=int, default=44500, help="Port to listen on")
    args = parser.parse_args()

    app = web.Application()
    app.router.add_post("/v1/messages", handle_messages)
    app.router.add_get("/health", handle_health)

    print(f"Mock Anthropic SSE server starting on http://127.0.0.1:{args.port}")
    print(f"  POST /v1/messages → fixed SSE stream ({len(MOCK_EVENTS)} events)")
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
