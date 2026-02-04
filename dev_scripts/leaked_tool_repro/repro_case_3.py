#!/usr/bin/env python3
"""
Reproduction script for leaked tool call case 3.

Source: leaked_tool_20260131_114729_223329.json
Timestamp: 2026-01-31T11:47:29.223401
Model: claudeopus45

This case shows 3 tool calls leaked in sequence (all 'read' tool calls).
The response has preceding text: "Now let me look at the key files..."
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Configuration
ARGO_PROXY_URL = os.getenv("ARGO_PROXY_URL", "http://localhost:8000")
ARGO_DIRECT_URL = os.getenv(
    "ARGO_DIRECT_URL", "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
)

LOG_FILE = Path(__file__).parent / "leaked_tool_20260131_114729_223329.json"


def load_request_body() -> dict:
    """Load the request body from the log file."""
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_data = json.load(f)
    return log_data["request"]


def send_request(url: str, request_body: dict, via_proxy: bool = True) -> dict:
    """Send the request and return the response."""
    endpoint = f"{url}/v1/chat/completions" if via_proxy else url

    print(f"\n{'=' * 60}")
    print(f"Sending request to: {endpoint}")
    print(f"Model: {request_body.get('model')}")
    print(f"Stream: {request_body.get('stream')}")
    print(f"Tools count: {len(request_body.get('tools', []))}")
    print(f"Messages count: {len(request_body.get('messages', []))}")
    print(f"{'=' * 60}\n")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.post(
            endpoint,
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


def print_raw_response(response: dict) -> None:
    """Print the raw response JSON."""
    print("\n" + "=" * 60)
    print("RAW RESPONSE")
    print("=" * 60)
    print(json.dumps(response, indent=2, ensure_ascii=False))
    print("=" * 60)


def main():
    """Main entry point."""
    print("=" * 60)
    print("LEAKED TOOL CALL REPRODUCTION - CASE 3")
    print("Multiple read tool calls leaked in sequence")
    print("=" * 60)

    try:
        request_body = load_request_body()
        print(f"\n✓ Loaded request from: {LOG_FILE}")
    except FileNotFoundError:
        print(f"\n✗ Log file not found: {LOG_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n✗ Failed to parse log file: {e}")
        sys.exit(1)

    print("\n" + "-" * 60)
    print("TEST 1: Via argo-proxy")
    print("-" * 60)

    try:
        response = send_request(ARGO_PROXY_URL, request_body, via_proxy=True)
        print_raw_response(response)
    except httpx.HTTPStatusError as e:
        print(f"\n✗ HTTP error: {e.response.status_code}")
        print(f"Response: {e.response.text[:500]}")
    except httpx.RequestError as e:
        print(f"\n✗ Request error: {e}")
        print("Make sure argo-proxy is running on the configured URL")

    if os.getenv("TEST_DIRECT", "").lower() == "true":
        print("\n" + "-" * 60)
        print("TEST 2: Direct to ARGO API")
        print("-" * 60)

        try:
            response = send_request(ARGO_DIRECT_URL, request_body, via_proxy=False)
            print_raw_response(response)
        except httpx.HTTPStatusError as e:
            print(f"\n✗ HTTP error: {e.response.status_code}")
            print(f"Response: {e.response.text[:500]}")
        except httpx.RequestError as e:
            print(f"\n✗ Request error: {e}")


if __name__ == "__main__":
    main()