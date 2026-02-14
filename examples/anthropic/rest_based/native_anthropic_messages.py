"""Raw HTTP request to native Anthropic /v1/messages endpoint (non-streaming).

This example demonstrates sending requests directly to the argo-proxy's
native Anthropic passthrough endpoint using httpx, without the Anthropic SDK.

Prerequisites:
    - argo-proxy running with --native-anthropic flag
    - pip install httpx

Usage:
    python native_anthropic_messages.py

Environment variables:
    BASE_URL: Proxy base URL (default: http://localhost:44497)
    MODEL: Model to use (default: argo:claude-4.5-sonnet)
"""

import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44497")
MODEL = os.getenv("MODEL", "argo:claude-4.5-sonnet")
API_KEY = os.environ.get("API_KEY", "your-anl-username")

MESSAGES_ENDPOINT = f"{BASE_URL}/v1/messages"

print("Running Native Anthropic Messages Test (non-streaming)")

payload = {
    "model": MODEL,
    "max_tokens": 100,
    "messages": [
        {"role": "user", "content": "Hello, say hi back in one sentence."},
    ],
}
headers = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
}

response = httpx.post(MESSAGES_ENDPOINT, json=payload, headers=headers, timeout=60.0)

try:
    response.raise_for_status()
    print("Response Status Code:", response.status_code)
    print(response.text)
    print("Response Body:", json.dumps(response.json(), indent=4))
except httpx.HTTPStatusError as err:
    print("HTTP Error:", err)
    print("Response Body:", response.text)
