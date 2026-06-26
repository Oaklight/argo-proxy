"""Minimal stdio MCP server that returns an image from a tool result.

Used to reproduce argo-proxy#99: input_image type rejected by Anthropic API
during cross-provider conversion.

No external dependencies - uses only stdlib. Implements MCP JSON-RPC over stdio.
"""

import base64
import json
import sys

# 1x1 red pixel PNG
_PIXEL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_B64_IMAGE = base64.b64encode(_PIXEL_PNG).decode()

SERVER_INFO = {
    "name": "image-test-server",
    "version": "0.1.0",
}

TOOLS = [
    {
        "name": "get_test_image",
        "description": "Return a tiny test image (1x1 red pixel PNG). Call this tool to get a small test image.",
        "inputSchema": {"type": "object", "properties": {}},
    }
]


def handle_request(req: dict) -> dict | None:
    """Handle a single JSON-RPC request."""
    method = req.get("method", "")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS},
        }

    if method == "tools/call":
        tool_name = req.get("params", {}).get("name", "")
        if tool_name == "get_test_image":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "image",
                            "data": _B64_IMAGE,
                            "mimeType": "image/png",
                        }
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    # Unknown method
    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def main() -> None:
    """Run MCP server over stdio using JSON-RPC."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        resp = handle_request(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
