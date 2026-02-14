"""Raw HTTP request to native Anthropic /v1/messages endpoint (streaming).

This example demonstrates sending streaming requests directly to the argo-proxy's
native Anthropic passthrough endpoint using httpx, without the Anthropic SDK.

Prerequisites:
    - argo-proxy running with --native-anthropic flag
    - pip install httpx

Usage:
    python native_anthropic_messages_stream.py

Environment variables:
    BASE_URL: Proxy base URL (default: http://localhost:44497)
    MODEL: Model to use (default: argo:claude-4.5-sonnet)
"""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44497")
MODEL = os.getenv("MODEL", "argo:claude-4.5-sonnet")
API_KEY = os.environ.get("API_KEY", "your-anl-username")

MESSAGES_ENDPOINT = f"{BASE_URL}/v1/messages"

print("Running Native Anthropic Messages Test (streaming)")

payload = {
    "model": MODEL,
    "max_tokens": 100,
    "stream": True,
    "messages": [
        {"role": "user", "content": "Count from 1 to 5."},
    ],
}
headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
}

with httpx.stream(
    "POST", MESSAGES_ENDPOINT, json=payload, headers=headers, timeout=60.0
) as response:
    print("Status Code:", response.status_code)
    print("Headers:", response.headers)
    print("Streaming Response:")

    for chunk in response.iter_bytes():
        if chunk:
            print(chunk.decode(errors="replace"), end="", flush=True)

print()
