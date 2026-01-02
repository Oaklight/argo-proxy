#!/usr/bin/env python3
"""
Chat Completions API Test Script using pytest

This script tests the chat completions endpoint with various configurations.
Adapted from examples/openai_client/chat_completions.py
"""

import os

import openai
import pytest
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
MODEL = os.getenv("MODEL", "argo:gpt-4o")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
API_KEY = os.getenv("API_KEY", "whatever+random")


@pytest.fixture(scope="module")
def client():
    """Create OpenAI client for testing."""
    return openai.OpenAI(
        api_key=API_KEY,
        base_url=f"{BASE_URL}/v1",
    )


class TestChatCompletions:
    """Test class for Chat Completions API."""

    def test_basic_chat(self, client):
        """Test basic chat completion without streaming."""
        messages = [
            {
                "role": "user",
                "content": "Tell me a short joke about programming.",
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=100,
            temperature=0.7,
        )

        assert response is not None
        assert response.choices is not None
        assert len(response.choices) > 0
        assert response.choices[0].message is not None
        assert response.choices[0].message.content is not None
        assert len(response.choices[0].message.content.strip()) > 0
        assert response.model is not None
        assert response.usage is not None

    def test_system_message_chat(self, client):
        """Test chat completion with system message."""
        messages = [
            {
                "role": "system",
                "content": "You are a helpful assistant that responds in a pirate accent.",
            },
            {
                "role": "user",
                "content": "What is the weather like today?",
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=150,
            temperature=0.8,
        )

        assert response is not None
        assert response.choices[0].message.content is not None
        # Check that the response might contain pirate-like language
        content = response.choices[0].message.content.lower()
        # This is a loose check since we can't guarantee pirate language
        assert len(content) > 10

    def test_streaming_chat(self, client):
        """Test streaming chat completion."""
        messages = [
            {
                "role": "user",
                "content": "Count from 1 to 5 and explain each number briefly.",
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.5,
            stream=True,
        )

        full_content = ""
        chunk_count = 0

        for chunk in response:
            chunk_count += 1
            if chunk.choices[0].delta.content is not None:
                content = chunk.choices[0].delta.content
                full_content += content

        assert chunk_count > 0
        assert len(full_content.strip()) > 0

    def test_temperature_control(self, client):
        """Test that temperature parameter affects randomness."""
        messages = [
            {
                "role": "user",
                "content": "Say hello in a creative way.",
            },
        ]

        # Test with low temperature (more deterministic)
        response_low = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=50,
            temperature=0.1,
        )

        # Test with high temperature (more random)
        response_high = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=50,
            temperature=0.9,
        )

        assert response_low.choices[0].message.content is not None
        assert response_high.choices[0].message.content is not None

        # Both should have content
        assert len(response_low.choices[0].message.content.strip()) > 0
        assert len(response_high.choices[0].message.content.strip()) > 0

    def test_max_tokens_limit(self, client):
        """Test that max_tokens parameter limits response length."""
        messages = [
            {
                "role": "user",
                "content": "Write a very long story about a dragon.",
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=20,  # Very small limit
            temperature=0.7,
        )

        assert response is not None
        assert response.choices[0].message.content is not None
        assert response.usage.completion_tokens <= 20

    def test_conversation_context(self, client):
        """Test multi-turn conversation."""
        messages = [
            {
                "role": "user",
                "content": "My name is Alice.",
            },
            {
                "role": "assistant",
                "content": "Hello Alice! Nice to meet you.",
            },
            {
                "role": "user",
                "content": "What's my name?",
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=50,
            temperature=0.3,
        )

        assert response is not None
        content = response.choices[0].message.content.lower()
        # Should remember the name Alice
        assert "alice" in content

    def test_empty_message_handling(self, client):
        """Test handling of edge cases."""
        messages = [
            {
                "role": "user",
                "content": "",  # Empty content
            },
        ]

        # This might fail or return a minimal response
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=50,
            )
            # If it succeeds, check basic structure
            assert response is not None
        except Exception as e:
            # Empty messages might be rejected, which is acceptable
            assert "empty" in str(e).lower() or "invalid" in str(e).lower()

    def test_role_validation(self, client):
        """Test that proper roles are required."""
        # Test with valid roles
        messages = [
            {
                "role": "user",
                "content": "Hello",
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=50,
        )

        assert response is not None
        assert response.choices[0].message.role == "assistant"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
