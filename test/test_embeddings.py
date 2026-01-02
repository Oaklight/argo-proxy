#!/usr/bin/env python3
"""
Embeddings API Test Script using pytest

This script tests the embeddings endpoint with single and multiple inputs.
Simple validation to check if valid embeddings are returned.
"""

import os
import pytest

import openai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
MODEL = os.getenv("MODEL", "argo:text-embedding-3-small")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
API_KEY = os.getenv("API_KEY", "whatever+random")


@pytest.fixture(scope="module")
def client():
    """Create OpenAI client for testing."""
    return openai.OpenAI(
        api_key=API_KEY,
        base_url=f"{BASE_URL}/v1",
    )


class TestEmbeddingsAPI:
    """Test class for Embeddings API."""

    def test_single_text_embedding(self, client):
        """Test embedding for a single text."""
        text = "The quick brown fox jumps over the lazy dog."
        
        response = client.embeddings.create(
            model=MODEL,
            input=text,
        )
        
        # Basic response validation
        assert response is not None
        assert response.data is not None
        assert len(response.data) == 1
        
        # Embedding validation
        embedding_data = response.data[0]
        assert embedding_data.embedding is not None
        assert len(embedding_data.embedding) > 0
        assert embedding_data.index == 0
        
        # Check that embeddings are numeric
        embedding = embedding_data.embedding
        assert all(isinstance(x, (int, float)) for x in embedding)
        
        # Basic metadata validation
        assert response.model is not None
        assert response.usage is not None
        assert response.usage.total_tokens > 0

    def test_multiple_texts_embedding(self, client):
        """Test embedding for multiple texts."""
        texts = [
            "What is your name?",
            "What is your favorite color?",
            "How are you doing today?",
            "Tell me about artificial intelligence.",
        ]
        
        response = client.embeddings.create(
            model=MODEL,
            input=texts,
        )
        
        # Basic response validation
        assert response is not None
        assert response.data is not None
        assert len(response.data) == len(texts)
        
        # Validate each embedding
        for i, embedding_data in enumerate(response.data):
            assert embedding_data.embedding is not None
            assert len(embedding_data.embedding) > 0
            assert embedding_data.index == i
            
            # Check that embeddings are numeric
            embedding = embedding_data.embedding
            assert all(isinstance(x, (int, float)) for x in embedding)
        
        # All embeddings should have the same dimension
        dimensions = [len(data.embedding) for data in response.data]
        assert all(dim == dimensions[0] for dim in dimensions)
        
        # Basic metadata validation
        assert response.model is not None
        assert response.usage is not None
        assert response.usage.total_tokens > 0

    def test_empty_list_input(self, client):
        """Test handling of empty list input."""
        try:
            response = client.embeddings.create(
                model=MODEL,
                input=[],
            )
            # If it succeeds, should have empty data
            assert response.data == []
        except Exception as e:
            # Empty input might be rejected, which is acceptable
            assert "empty" in str(e).lower() or "invalid" in str(e).lower()

    def test_single_word_embedding(self, client):
        """Test embedding for a single word."""
        response = client.embeddings.create(
            model=MODEL,
            input="hello",
        )
        
        assert response is not None
        assert len(response.data) == 1
        assert response.data[0].embedding is not None
        assert len(response.data[0].embedding) > 0

    def test_mixed_length_texts(self, client):
        """Test embedding for texts of different lengths."""
        texts = [
            "Hi",
            "This is a medium length sentence.",
            "This is a much longer text that contains multiple sentences and various ideas to test how the embedding model handles different input lengths.",
        ]
        
        response = client.embeddings.create(
            model=MODEL,
            input=texts,
        )
        
        assert response is not None
        assert len(response.data) == len(texts)
        
        # All should have valid embeddings
        for embedding_data in response.data:
            assert embedding_data.embedding is not None
            assert len(embedding_data.embedding) > 0
            assert all(isinstance(x, (int, float)) for x in embedding_data.embedding)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])