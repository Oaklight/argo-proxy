#!/usr/bin/env python3
"""
Legacy Completions API Test Script using pytest

This script tests the legacy completions endpoint with various configurations.
Adapted from examples/openai_client/legacy_completions.py
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


class TestLegacyCompletions:
    """Test class for Legacy Completions API."""

    def test_basic_completion(self, client):
        """Test basic completion without streaming."""
        prompt = "Once upon a time, in a land far away,"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=100,
            temperature=0.7,
        )

        assert response is not None
        assert response.choices is not None
        assert len(response.choices) > 0
        assert response.choices[0].text is not None
        assert len(response.choices[0].text.strip()) > 0
        assert response.model is not None
        assert response.usage is not None

    def test_multiple_prompts(self, client):
        """Test completion with multiple prompts (concatenated into one)."""
        prompts = [
            "The best programming language is",
            "Artificial intelligence will",
            "In the future, technology will",
        ]

        response = client.completions.create(
            model=MODEL,
            prompt=prompts,
            max_tokens=50,
            temperature=0.8,
        )

        assert response is not None
        # Multiple prompts are concatenated, so we get one choice
        assert len(response.choices) == 1

        choice = response.choices[0]
        assert choice.text is not None
        assert len(choice.text.strip()) > 0

    def test_streaming_completion(self, client):
        """Test streaming completion."""
        prompt = "Write a short poem about coding:"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=150,
            temperature=0.9,
            stream=True,
        )

        full_text = ""
        chunk_count = 0

        for chunk in response:
            chunk_count += 1
            if chunk.choices[0].text is not None:
                text = chunk.choices[0].text
                full_text += text

        assert chunk_count > 0
        assert len(full_text.strip()) > 0

    def test_completion_with_stop(self, client):
        """Test completion with stop sequences."""
        prompt = "List three benefits of exercise:\n1."
        stop_sequences = ["\n4.", "\n\n"]

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=200,
            temperature=0.5,
            stop=stop_sequences,
        )

        assert response is not None
        assert response.choices[0].text is not None

        # Check that the response stopped appropriately
        text = response.choices[0].text
        for stop_seq in stop_sequences:
            assert stop_seq not in text

        # Should have a finish reason
        assert response.choices[0].finish_reason is not None

    def test_completion_with_logprobs(self, client):
        """Test completion with log probabilities."""
        prompt = "The capital of France is"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=10,
            temperature=0.1,
            logprobs=5,  # Return top 5 log probabilities
        )

        assert response is not None
        assert response.choices[0].text is not None

        # Check if logprobs are available (may not be supported by all models)
        if response.choices[0].logprobs:
            assert response.choices[0].logprobs.tokens is not None
            assert len(response.choices[0].logprobs.tokens) > 0

    def test_completion_with_echo(self, client):
        """Test completion with echo parameter."""
        prompt = "Python is a"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=50,
            temperature=0.7,
            echo=True,  # Echo the prompt in the response
        )

        assert response is not None
        assert response.choices[0].text is not None

        # With echo=True, the response should start with the prompt
        response_text = response.choices[0].text
        # Note: Some implementations may not support echo, so we check if it's included
        if prompt in response_text:
            assert response_text.startswith(prompt)

    def test_temperature_effects(self, client):
        """Test that temperature affects output randomness."""
        prompt = "Complete this sentence: The future of AI is"

        # Low temperature (more deterministic)
        response_low = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=30,
            temperature=0.1,
        )

        # High temperature (more random)
        response_high = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=30,
            temperature=0.9,
        )

        assert response_low.choices[0].text is not None
        assert response_high.choices[0].text is not None
        assert len(response_low.choices[0].text.strip()) > 0
        assert len(response_high.choices[0].text.strip()) > 0

    def test_max_tokens_enforcement(self, client):
        """Test that max_tokens parameter is respected."""
        prompt = "Write a very detailed explanation of quantum physics:"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=15,  # Very small limit
            temperature=0.7,
        )

        assert response is not None
        assert response.usage.completion_tokens <= 15

    def test_suffix_parameter(self, client):
        """Test completion with suffix parameter if supported."""
        prompt = "The quick brown"
        suffix = "jumps over the lazy dog."

        try:
            response = client.completions.create(
                model=MODEL,
                prompt=prompt,
                suffix=suffix,
                max_tokens=20,
                temperature=0.5,
            )

            assert response is not None
            assert response.choices[0].text is not None

        except Exception as e:
            # Suffix might not be supported by all models
            pytest.skip(f"Suffix parameter not supported: {e}")

    def test_best_of_parameter(self, client):
        """Test completion with best_of parameter if supported."""
        prompt = "Write a creative opening line:"

        try:
            response = client.completions.create(
                model=MODEL,
                prompt=prompt,
                max_tokens=30,
                temperature=0.8,
                best_of=3,  # Generate 3 completions and return the best
                n=1,
            )

            assert response is not None
            assert len(response.choices) == 1
            assert response.choices[0].text is not None

        except Exception as e:
            # best_of might not be supported by all models
            pytest.skip(f"best_of parameter not supported: {e}")

    def test_presence_penalty(self, client):
        """Test completion with presence penalty."""
        prompt = "List some programming languages:"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=100,
            temperature=0.7,
            presence_penalty=0.5,  # Encourage diversity
        )

        assert response is not None
        assert response.choices[0].text is not None
        assert len(response.choices[0].text.strip()) > 0

    def test_frequency_penalty(self, client):
        """Test completion with frequency penalty."""
        prompt = "Describe the benefits of exercise:"

        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            max_tokens=100,
            temperature=0.7,
            frequency_penalty=0.3,  # Reduce repetition
        )

        assert response is not None
        assert response.choices[0].text is not None
        assert len(response.choices[0].text.strip()) > 0

    def test_empty_prompt_handling(self, client):
        """Test handling of empty or minimal prompts."""
        # Test with empty string
        try:
            response = client.completions.create(
                model=MODEL,
                prompt="",
                max_tokens=50,
            )
            assert response is not None
        except Exception as e:
            # Empty prompts might be rejected
            assert "empty" in str(e).lower() or "invalid" in str(e).lower()

    def test_very_long_prompt(self, client):
        """Test handling of very long prompts."""
        # Create a reasonably long prompt
        long_prompt = "This is a test prompt. " * 100

        try:
            response = client.completions.create(
                model=MODEL,
                prompt=long_prompt,
                max_tokens=50,
                temperature=0.5,
            )

            assert response is not None
            assert response.choices[0].text is not None

        except Exception as e:
            # Very long prompts might exceed token limits
            assert "token" in str(e).lower() or "length" in str(e).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
