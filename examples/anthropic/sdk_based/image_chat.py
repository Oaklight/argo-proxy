"""Image comprehension example using Anthropic SDK via argo-proxy native Anthropic mode.

Prerequisites:
    - argo-proxy running with --native-anthropic flag
    - pip install anthropic

Usage:
    python image_chat.py

Environment variables:
    BASE_URL: Proxy base URL (default: http://localhost:44497)
    MODEL: Model to use (default: argo:claude-4.5-sonnet)
    API_KEY: Your ANL username for authentication
"""

import base64
import os

import anthropic
import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:44497")
MODEL = os.environ.get("MODEL", "argo:claude-4.5-sonnet")
API_KEY = os.environ.get("API_KEY", "your-anl-username")

# A small test image URL (PNG transparency demonstration)
IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"


def test_image_url():
    """Test image comprehension with a URL (base64 encoded)."""
    print("=== Test 1: Image from URL (base64 encoded) ===")

    # Download and encode the image
    image_response = httpx.get(IMAGE_URL, timeout=30.0)
    image_data = base64.standard_b64encode(image_response.content).decode("utf-8")
    media_type = image_response.headers.get("content-type", "image/png")

    client = anthropic.Anthropic(
        base_url=BASE_URL,
        api_key=API_KEY,
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[
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
    )
    print(f"Response: {message.content[0].text}")
    print()


def test_image_url_direct():
    """Test image comprehension with a direct URL (if supported by upstream)."""
    print("=== Test 2: Image from direct URL ===")

    client = anthropic.Anthropic(
        base_url=BASE_URL,
        api_key=API_KEY,
    )

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "url",
                                "url": IMAGE_URL,
                            },
                        },
                        {
                            "type": "text",
                            "text": "What is this image? Describe it briefly.",
                        },
                    ],
                }
            ],
        )
        print(f"Response: {message.content[0].text}")
    except Exception as e:
        print(f"Direct URL not supported: {e}")
    print()


if __name__ == "__main__":
    test_image_url()
    test_image_url_direct()
