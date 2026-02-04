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
    
    print(f"\n{'='*60}")
    print(f"Sending request to: {endpoint}")
    print(f"Model: {request_body.get('model')}")
    print(f"Stream: {request_body.get('stream')}")
    print(f"Tools count: {len(request_body.get('tools', []))}")
    print(f"Messages count: {len(request_body.get('messages', []))}")
    print(f"{'='*60}\n")
    
    # Use follow_redirects=True to handle 307 redirects
    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.post(
            endpoint,
            json=request_body,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return response.json()


def analyze_response(response: dict) -> None:
    """Analyze the response for leaked tool calls."""
    print("\n" + "="*60)
    print("RESPONSE ANALYSIS")
    print("="*60)
    
    # Check for choices
    choices = response.get("choices", [])
    if not choices:
        print("ERROR: No choices in response")
        return
    
    choice = choices[0]
    message = choice.get("message", {})
    
    # Get content and tool_calls
    content = message.get("content", "")
    tool_calls = message.get("tool_calls", [])
    
    print(f"\nContent length: {len(content) if content else 0}")
    print(f"Tool calls count: {len(tool_calls)}")
    
    # Check for leaked tool calls in content
    leaked_patterns = [
        "{'id': 'toolu_",
        '{"id": "toolu_',
        "{'id': 'call_",
        '{"id": "call_',
    ]
    
    leaked_found = False
    for pattern in leaked_patterns:
        if content and pattern in content:
            leaked_found = True
            print(f"\n⚠️  LEAKED TOOL CALL DETECTED!")
            print(f"Pattern found: {pattern}")
            
            # Find and print the leaked content
            start_idx = content.find(pattern)
            end_idx = min(start_idx + 500, len(content))
            print(f"\nLeaked content preview:")
            print("-" * 40)
            print(content[start_idx:end_idx])
            print("-" * 40)
            break
    
    if not leaked_found:
        print("\n✓ No leaked tool calls detected in content")
    
    # Print tool calls if present
    if tool_calls:
        print(f"\nTool calls returned properly:")
        for i, tc in enumerate(tool_calls):
            print(f"  [{i}] {tc.get('function', {}).get('name', 'unknown')}")
    
    # Print content preview
    if content:
        print(f"\nContent preview (first 200 chars):")
        print("-" * 40)
        print(content[:200])
        print("-" * 40)
    
    print("\n" + "="*60)


def main():
    """Main entry point."""
    print("="*60)
    print("LEAKED TOOL CALL REPRODUCTION - CASE 1")
    print("="*60)
    
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
    print("\n" + "-"*60)
    print("TEST 1: Via argo-proxy")
    print("-"*60)
    
    try:
        response = send_request(ARGO_PROXY_URL, request_body, via_proxy=True)
        analyze_response(response)
    except httpx.HTTPStatusError as e:
        print(f"\n✗ HTTP error: {e.response.status_code}")
        print(f"Response: {e.response.text[:500]}")
    except httpx.RequestError as e:
        print(f"\n✗ Request error: {e}")
        print("Make sure argo-proxy is running on the configured URL")
    
    # Optionally test direct to ARGO API
    if os.getenv("TEST_DIRECT", "").lower() == "true":
        print("\n" + "-"*60)
        print("TEST 2: Direct to ARGO API")
        print("-"*60)
        
        try:
            response = send_request(ARGO_DIRECT_URL, request_body, via_proxy=False)
            analyze_response(response)
        except httpx.HTTPStatusError as e:
            print(f"\n✗ HTTP error: {e.response.status_code}")
            print(f"Response: {e.response.text[:500]}")
        except httpx.RequestError as e:
            print(f"\n✗ Request error: {e}")


if __name__ == "__main__":
    main()