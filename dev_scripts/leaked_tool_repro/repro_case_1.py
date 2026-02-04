#!/usr/bin/env python3
"""
Reproduction script for leaked tool call case 1.

Source: reference/bugs_report/leaked_tool_logs/leaked_tool_20260128_171422_165810.json
Timestamp: 2026-01-28T17:14:22.166209
Model: claudeopus45

This script sends the exact same request body that was logged when the leaked
tool call was detected. The goal is to reproduce the issue where Claude returns
tool calls embedded in text content instead of the tool_calls array.

NOTE: This script tests directly against the ARGO Gateway API to reproduce
the upstream issue. The problem is in the gateway, not in argo-proxy.
"""

import json
import os
import sys
from pathlib import Path

import httpx

# Configuration - Direct ARGO Gateway API endpoint
ARGO_API_URL = os.getenv(
    "ARGO_API_URL", "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
)

# Load the original request from the log file (in the same directory)
LOG_FILE = Path(__file__).parent / "leaked_tool_20260128_171422_165810.json"


def load_request_body() -> dict:
    """Load the request body from the log file."""
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_data = json.load(f)
    return log_data["request"]


def send_request(url: str, request_body: dict) -> dict:
    """Send the request and return the response."""
    print(f"\n{'=' * 60}")
    print(f"Sending request to: {url}")
    print(f"Model: {request_body.get('model')}")
    print(f"Stream: {request_body.get('stream')}")
    print(f"Tools count: {len(request_body.get('tools', []))}")
    print(f"Messages count: {len(request_body.get('messages', []))}")
    print(f"{'=' * 60}\n")

    # Use follow_redirects=True to handle 307 redirects
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.post(
            url,
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
    print("Testing directly against ARGO Gateway API")
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

    # Test direct to ARGO Gateway API
    print("\n" + "-" * 60)
    print("Direct to ARGO Gateway API")
    print("-" * 60)

    try:
        response = send_request(ARGO_API_URL, request_body)
        print_raw_response(response)
    except httpx.HTTPStatusError as e:
        print(f"\n✗ HTTP error: {e.response.status_code}")
        print(f"Response: {e.response.text[:500]}")
    except httpx.RequestError as e:
        print(f"\n✗ Request error: {e}")
        print("Make sure you have network access to the ARGO API")


if __name__ == "__main__":
    main()
