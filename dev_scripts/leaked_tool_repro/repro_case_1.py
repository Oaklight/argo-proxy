#!/usr/bin/env python3
"""
Reproduction script for leaked tool call case 1.

Source: reference/bugs_report/leaked_tool_logs/leaked_tool_20260128_171422_165810.json
Timestamp: 2026-01-28T17:14:22.166209
Model: claudeopus45

This script sends the exact same request body that was logged when the leaked
tool call was detected. The goal is to reproduce the issue where Claude returns
tool calls embedded in text content instead of the tool_calls array.
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Configuration
ARGO_PROXY_URL = os.getenv("ARGO_PROXY_URL", "http://localhost:8000")
# Note: The ARGO API URL should end with /chat for the chat endpoint
ARGO_DIRECT_URL = os.getenv(
    "ARGO_DIRECT_URL", "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
)

# Load the original request from the log file (in the same directory)
LOG_FILE = Path(__file__).parent / "leaked_tool_20260128_171422_165810.json"


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

    # Use follow_redirects=True to handle 307 redirects
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
    print("LEAKED TOOL CALL REPRODUCTION - CASE 1")
    print("=" * 60)

    # Load request body
    try:
        request_body = load_request_body()
        print(f"\n✓ Loaded request from: {LOG_FILE}")
    except FileNotFoundError:
        print(f"\n✗ Log file not found: {LOG_FILE}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\n✗ Failed to parse log file: {e}")
        sys.exit(1)

    # Test via argo-proxy
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

    # Optionally test direct to ARGO API
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
