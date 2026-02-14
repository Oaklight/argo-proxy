#!/usr/bin/env python3
"""
Test script for native OpenAI endpoint passthrough mode.

This script demonstrates how to use the native OpenAI endpoint passthrough feature.
When --native-openai flag is enabled, requests are directly forwarded to the native
OpenAI endpoint without any transformation.

Usage:
    1. Start the proxy with native OpenAI mode:
       argo-proxy --native-openai

    2. Run this test script:
       python examples/openai_client/native_openai_test.py
"""

import os

from openai import OpenAI

API_KEY = os.environ.get("API_KEY", "your-anl-username")

# Configure the client to use the local proxy
client = OpenAI(
    api_key=API_KEY,
    base_url="http://localhost:44497/v1",
)


def test_chat_completion():
    """Test chat completion endpoint in native OpenAI mode."""
    print("Testing chat completion endpoint...")

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Say 'Hello from native OpenAI endpoint!'"}
        ],
        max_tokens=50,
    )

    print(f"Response: {response.choices[0].message.content}")
    print(f"Model: {response.model}")
    print(f"Usage: {response.usage}")
    print()


def test_chat_completion_streaming():
    """Test streaming chat completion endpoint in native OpenAI mode."""
    print("Testing streaming chat completion endpoint...")

    stream = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Count from 1 to 5"}],
        max_tokens=50,
        stream=True,
    )

    print("Streaming response: ", end="", flush=True)
    for chunk in stream:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="", flush=True)
    print("\n")


def test_embeddings():
    """Test embeddings endpoint in native OpenAI mode."""
    print("Testing embeddings endpoint...")

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input="Hello, world!",
    )

    print(f"Embedding dimension: {len(response.data[0].embedding)}")
    print(f"Model: {response.model}")
    print(f"Usage: {response.usage}")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Native OpenAI Endpoint Passthrough Test")
    print("=" * 60)
    print()

    try:
        test_chat_completion()
        test_chat_completion_streaming()
        test_embeddings()

        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("1. The proxy is running with --native-openai flag")
        print("2. You have access to the native OpenAI endpoint")
        print("3. The endpoint URL is correctly configured")
