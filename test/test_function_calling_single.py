#!/usr/bin/env python3
"""
Single Function Calling Test Script using pytest

This script tests function calling with a single function using chat completions API.
Adapted from examples/openai_client/function_calling_chat.py
"""

import json
import os
from typing import Any, Callable, Dict

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


# Function implementations for testing
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together."""
    return a + b


def get_weather(location: str, unit: str = "celsius") -> Dict[str, Any]:
    """Get weather information for a location."""
    # Mock weather data
    weather_data = {
        "location": location,
        "temperature": 22 if unit == "celsius" else 72,
        "unit": unit,
        "condition": "sunny",
        "humidity": 65,
        "wind_speed": 10,
    }
    return weather_data


def calculate_area(shape: str, **kwargs) -> float:
    """Calculate area of different shapes."""
    if shape.lower() == "rectangle":
        return kwargs.get("width", 0) * kwargs.get("height", 0)
    elif shape.lower() == "circle":
        import math

        return math.pi * (kwargs.get("radius", 0) ** 2)
    elif shape.lower() == "triangle":
        return 0.5 * kwargs.get("base", 0) * kwargs.get("height", 0)
    else:
        raise ValueError(f"Unsupported shape: {shape}")


# Function registry for execution
FUNCTION_REGISTRY: Dict[str, Callable] = {
    "add_numbers": add_numbers,
    "get_weather": get_weather,
    "calculate_area": calculate_area,
}


def execute_function_call(function_name: str, arguments: Dict[str, Any]) -> Any:
    """Execute a function call with given arguments."""
    if function_name not in FUNCTION_REGISTRY:
        raise ValueError(f"Unknown function: {function_name}")

    func = FUNCTION_REGISTRY[function_name]
    try:
        result = func(**arguments)
        return result
    except Exception as e:
        return f"Error executing {function_name}: {str(e)}"


class TestSingleFunctionCalling:
    """Test class for Single Function Calling."""

    def test_simple_math_function(self, client):
        """Test function calling with a simple math function."""
        messages = [
            {
                "role": "user",
                "content": "What is 15 plus 27? Please use the add_numbers function.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None
        assert len(message.tool_calls) > 0

        tool_call = message.tool_calls[0]
        assert tool_call.function.name == "add_numbers"

        arguments = json.loads(tool_call.function.arguments)
        assert "a" in arguments
        assert "b" in arguments

        # Execute the function
        result = execute_function_call(tool_call.function.name, arguments)
        assert result == 42  # 15 + 27

    def test_weather_function(self, client):
        """Test function calling with weather information."""
        messages = [
            {
                "role": "user",
                "content": "What's the weather like in Tokyo? Please get the weather information.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather information for a specific location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city or location to get weather for",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "description": "Temperature unit",
                                "default": "celsius",
                            },
                        },
                        "required": ["location"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None

        tool_call = message.tool_calls[0]
        assert tool_call.function.name == "get_weather"

        arguments = json.loads(tool_call.function.arguments)
        assert "location" in arguments
        assert "tokyo" in arguments["location"].lower()

        result = execute_function_call(tool_call.function.name, arguments)
        assert isinstance(result, dict)
        assert "location" in result
        assert "temperature" in result

    def test_area_calculation_function(self, client):
        """Test function calling with area calculation."""
        messages = [
            {
                "role": "user",
                "content": "Calculate the area of a rectangle with width 5 and height 8.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_area",
                    "description": "Calculate the area of different geometric shapes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "shape": {
                                "type": "string",
                                "enum": ["rectangle", "circle", "triangle"],
                                "description": "The shape to calculate area for",
                            },
                            "width": {
                                "type": "number",
                                "description": "Width of rectangle",
                            },
                            "height": {
                                "type": "number",
                                "description": "Height of rectangle or triangle",
                            },
                            "radius": {
                                "type": "number",
                                "description": "Radius of circle",
                            },
                            "base": {
                                "type": "number",
                                "description": "Base of triangle",
                            },
                        },
                        "required": ["shape"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None

        tool_call = message.tool_calls[0]
        assert tool_call.function.name == "calculate_area"

        arguments = json.loads(tool_call.function.arguments)
        assert arguments["shape"].lower() == "rectangle"
        assert arguments["width"] == 5
        assert arguments["height"] == 8

        result = execute_function_call(tool_call.function.name, arguments)
        assert result == 40  # 5 * 8

    def test_forced_function_call(self, client):
        """Test forcing a specific function call."""
        messages = [
            {
                "role": "user",
                "content": "I want to add some numbers.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice={"type": "function", "function": {"name": "add_numbers"}},
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None

        tool_call = message.tool_calls[0]
        assert tool_call.function.name == "add_numbers"

        arguments = json.loads(tool_call.function.arguments)
        assert "a" in arguments
        assert "b" in arguments

        # The model should have provided reasonable values
        result = execute_function_call(tool_call.function.name, arguments)
        assert isinstance(result, (int, float))

    def test_streaming_function_call(self, client):
        """Test function calling with streaming."""
        messages = [
            {
                "role": "user",
                "content": "Add 123 and 456 using the add function.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            stream=True,
        )

        # Collect streaming response
        function_calls = []
        content_parts = []

        for chunk in response:
            if chunk.choices[0].delta.tool_calls:
                for tool_call in chunk.choices[0].delta.tool_calls:
                    # Handle streaming tool calls
                    if len(function_calls) <= tool_call.index:
                        function_calls.extend(
                            [{}] * (tool_call.index + 1 - len(function_calls))
                        )

                    if tool_call.function.name:
                        function_calls[tool_call.index]["name"] = (
                            tool_call.function.name
                        )
                    if tool_call.function.arguments:
                        if "arguments" not in function_calls[tool_call.index]:
                            function_calls[tool_call.index]["arguments"] = ""
                        function_calls[tool_call.index]["arguments"] += (
                            tool_call.function.arguments
                        )

            if chunk.choices[0].delta.content:
                content_parts.append(chunk.choices[0].delta.content)

        assert len(function_calls) > 0
        func_call = function_calls[0]
        assert func_call["name"] == "add_numbers"

        arguments = json.loads(func_call["arguments"])
        result = execute_function_call(func_call["name"], arguments)
        assert result == 579  # 123 + 456

    def test_function_call_with_conversation_context(self, client):
        """Test function calling with conversation context."""
        messages = [
            {
                "role": "user",
                "content": "What is 15 plus 27?",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

        # First call
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        assert message.tool_calls is not None

        tool_call = message.tool_calls[0]
        arguments = json.loads(tool_call.function.arguments)
        result = execute_function_call(tool_call.function.name, arguments)

        # Continue conversation
        messages.append(message)
        messages.append(
            {
                "role": "tool",
                "content": str(result),
                "tool_call_id": tool_call.id,
            }
        )

        final_response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
        )

        assert final_response is not None
        final_content = final_response.choices[0].message.content
        assert final_content is not None
        assert str(result) in final_content or "42" in final_content

    def test_function_parameter_validation(self, client):
        """Test function parameter validation."""
        messages = [
            {
                "role": "user",
                "content": "Calculate the area of a circle with radius 5.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_area",
                    "description": "Calculate the area of different geometric shapes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "shape": {
                                "type": "string",
                                "enum": ["rectangle", "circle", "triangle"],
                                "description": "The shape to calculate area for",
                            },
                            "radius": {
                                "type": "number",
                                "description": "Radius of circle",
                            },
                        },
                        "required": ["shape"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        assert message.tool_calls is not None

        tool_call = message.tool_calls[0]
        arguments = json.loads(tool_call.function.arguments)

        assert arguments["shape"].lower() == "circle"
        assert arguments["radius"] == 5

        result = execute_function_call(tool_call.function.name, arguments)
        expected = 3.14159 * 25  # π * r²
        assert abs(result - expected) < 0.1

    def test_function_call_error_handling(self, client):
        """Test error handling in function calls."""
        messages = [
            {
                "role": "user",
                "content": "Calculate the area of an invalid shape.",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate_area",
                    "description": "Calculate the area of different geometric shapes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "shape": {
                                "type": "string",
                                "description": "The shape to calculate area for",
                            },
                        },
                        "required": ["shape"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            arguments = json.loads(tool_call.function.arguments)

            # This should handle the error gracefully
            result = execute_function_call(tool_call.function.name, arguments)
            if isinstance(result, str) and "Error" in result:
                # Error was handled properly
                assert "Unsupported shape" in result or "Error executing" in result

    def test_no_function_call_when_not_needed(self, client):
        """Test that functions are not called when not needed."""
        messages = [
            {
                "role": "user",
                "content": "Hello, how are you today?",
            }
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "add_numbers",
                    "description": "Add two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        # Should not call the function for a greeting
        assert message.tool_calls is None or len(message.tool_calls) == 0
        assert message.content is not None
        assert len(message.content.strip()) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
