"""Image comprehension example using raw HTTP requests to argo-proxy native Anthropic mode.

Prerequisites:
    - argo-proxy running with --native-anthropic flag
    - pip install httpx

Usage:
    python image_chat.py

Environment variables:
    BASE_URL: Proxy base URL (default: http://localhost:44497)
    MODEL: Model to use (default: argo:claude-4.5-sonnet)
    API_KEY: Your ANL username for authentication
"""

import base64
import json
import os

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:44497")
MODEL = os.environ.get("MODEL", "argo:claude-4.5-sonnet")
API_KEY = os.environ.get("API_KEY", "your-anl-username")
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": API_KEY,
    "anthropic-version": "2023-06-01",
}

# A small test image URL (PNG transparency demonstration)
IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"


def test_image_base64():
    """Test image comprehension with base64 encoded image."""
    print("=== Test: Image from URL (base64 encoded) ===")

    # Download and encode the image
    image_response = httpx.get(IMAGE_URL, timeout=30.0)
    image_data = base64.standard_b64encode(image_response.content).decode("utf-8")
    media_type = image_response.headers.get("content-type", "image/png")

    response = httpx.post(
        f"{BASE_URL}/v1/messages",
        json={
            "model": MODEL,
            "max_tokens": 256,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": "What is this image? Describe it briefly.",
                        },
                    ],
                }
            ],
        },
        headers=HEADERS,
        timeout=60.0,
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    text_blocks = [b for b in data.get("content", []) if b["type"] == "text"]
    if text_blocks:
        print(f"Response: {text_blocks[0]['text']}")
    else:
        print(f"Response: {json.dumps(data, indent=2)}")
    print()


if __name__ == "__main__":
    test_image_base64()
