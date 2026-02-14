"""Test native Anthropic passthrough mode with Anthropic SDK."""

import os

import anthropic

API_KEY = os.environ.get("API_KEY", "your-anl-username")

client = anthropic.Anthropic(
    base_url="http://localhost:44497",
    api_key=API_KEY,
)

# Test 1: Basic message
print("=== Test 1: Basic message ===")
message = client.messages.create(
    model="argo:claude-4.5-sonnet",
    max_tokens=100,
    messages=[{"role": "user", "content": "Hello, say hi back in one sentence."}],
)
print(f"Response: {message.content[0].text}")
print(f"Model: {message.model}")
print(f"Stop reason: {message.stop_reason}")
print()

# Test 2: Streaming
print("=== Test 2: Streaming ===")
with client.messages.stream(
    model="argo:claude-4.5-sonnet",
    max_tokens=100,
    messages=[{"role": "user", "content": "Count from 1 to 5."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
