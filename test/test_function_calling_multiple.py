#!/usr/bin/env python3
"""
Multiple Function Calling Test Script using pytest

This script tests function calling with multiple functions using chat completions API.
Tests scenarios where multiple functions are available and may be called in sequence.
"""

import json
import os
import time
from typing import Any, Callable, Dict, List

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


def multiply_numbers(a: float, b: float) -> float:
    """Multiply two numbers together."""
    return a * b


def get_stock_price(ticker: str) -> Dict[str, Any]:
    """Get stock price information for a ticker symbol."""
    # Mock stock data
    mock_prices = {
        "AAPL": 150.25,
        "GOOGL": 2800.50,
        "MSFT": 300.75,
        "TSLA": 250.00,
        "AMZN": 3200.00,
    }

    price = mock_prices.get(ticker.upper(), 100.00)
    return {
        "ticker": ticker.upper(),
        "price": price,
        "currency": "USD",
        "timestamp": time.time(),
        "change": round((price * 0.02) - (price * 0.01), 2),  # Mock change
    }


def get_weather(location: str, unit: str = "celsius") -> Dict[str, Any]:
    """Get weather information for a location."""
    # Mock weather data
    weather_conditions = ["sunny", "cloudy", "rainy", "snowy"]
    import random

    base_temp = 20 if unit == "celsius" else 68
    temp_variation = random.randint(-10, 15)

    return {
        "location": location,
        "temperature": base_temp + temp_variation,
        "unit": unit,
        "condition": random.choice(weather_conditions),
        "humidity": random.randint(30, 90),
        "wind_speed": random.randint(5, 25),
    }


def search_web(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search the web for information."""
    # Mock search results
    mock_results = [
        {
            "title": f"Result about {query} - Article 1",
            "url": f"https://example.com/article1?q={query.replace(' ', '+')}",
            "snippet": f"This is a comprehensive article about {query} with detailed information.",
        },
        {
            "title": f"{query} - Wikipedia",
            "url": f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
            "snippet": f"Wikipedia article providing an overview of {query}.",
        },
        {
            "title": f"Latest news about {query}",
            "url": f"https://news.example.com/{query.replace(' ', '-')}",
            "snippet": f"Recent developments and news related to {query}.",
        },
    ]

    return mock_results[:max_results]


def calculate_tip(bill_amount: float, tip_percentage: float = 15.0) -> Dict[str, float]:
    """Calculate tip and total amount for a bill."""
    tip_amount = bill_amount * (tip_percentage / 100)
    total_amount = bill_amount + tip_amount

    return {
        "bill_amount": bill_amount,
        "tip_percentage": tip_percentage,
        "tip_amount": round(tip_amount, 2),
        "total_amount": round(total_amount, 2),
    }


def convert_currency(
    amount: float, from_currency: str, to_currency: str
) -> Dict[str, Any]:
    """Convert currency from one type to another."""
    # Mock exchange rates
    exchange_rates = {
        ("USD", "EUR"): 0.85,
        ("USD", "GBP"): 0.73,
        ("USD", "JPY"): 110.0,
        ("EUR", "USD"): 1.18,
        ("GBP", "USD"): 1.37,
        ("JPY", "USD"): 0.009,
    }

    rate = exchange_rates.get((from_currency.upper(), to_currency.upper()), 1.0)
    converted_amount = amount * rate

    return {
        "original_amount": amount,
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "exchange_rate": rate,
        "converted_amount": round(converted_amount, 2),
    }


# Function registry for execution
FUNCTION_REGISTRY: Dict[str, Callable] = {
    "add_numbers": add_numbers,
    "multiply_numbers": multiply_numbers,
    "get_stock_price": get_stock_price,
    "get_weather": get_weather,
    "search_web": search_web,
    "calculate_tip": calculate_tip,
    "convert_currency": convert_currency,
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


@pytest.fixture
def all_tools():
    """Get all available tools for function calling."""
    return [
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
        },
        {
            "type": "function",
            "function": {
                "name": "multiply_numbers",
                "description": "Multiply two numbers together.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_stock_price",
                "description": "Get current stock price for a ticker symbol.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g., AAPL, GOOGL)",
                        },
                    },
                    "required": ["ticker"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather information for a location.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City or location name",
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
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web for information on a topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_tip",
                "description": "Calculate tip and total amount for a restaurant bill.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "bill_amount": {
                            "type": "number",
                            "description": "The bill amount before tip",
                        },
                        "tip_percentage": {
                            "type": "number",
                            "description": "Tip percentage (default 15%)",
                            "default": 15.0,
                        },
                    },
                    "required": ["bill_amount"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "convert_currency",
                "description": "Convert amount from one currency to another.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "number",
                            "description": "Amount to convert",
                        },
                        "from_currency": {
                            "type": "string",
                            "description": "Source currency code (e.g., USD, EUR)",
                        },
                        "to_currency": {
                            "type": "string",
                            "description": "Target currency code (e.g., USD, EUR)",
                        },
                    },
                    "required": ["amount", "from_currency", "to_currency"],
                },
            },
        },
    ]


class TestMultipleFunctionCalling:
    """Test class for Multiple Function Calling."""

    def test_multiple_function_selection(self, client, all_tools):
        """Test that the model can select appropriate functions from multiple options."""
        messages = [
            {
                "role": "user",
                "content": "I need to know the weather in New York and the current stock price of Apple (AAPL).",
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=all_tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None
        assert len(message.tool_calls) > 0

        # Should call both weather and stock functions
        function_names = [tc.function.name for tc in message.tool_calls]
        assert "get_weather" in function_names
        assert "get_stock_price" in function_names

        # Execute all function calls
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)
            result = execute_function_call(tool_call.function.name, arguments)
            assert result is not None

    def test_sequential_function_calls(self, client):
        """Test that multiple math functions can be called in a single request."""
        messages = [
            {
                "role": "user",
                "content": "I need to do some calculations: first add 15 and 25, and also multiply 8 by 7.",
            }
        ]

        # Only include math functions for this test
        math_tools = [
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
            },
            {
                "type": "function",
                "function": {
                    "name": "multiply_numbers",
                    "description": "Multiply two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            },
        ]

        # Single call that should trigger both functions
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=math_tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message

        # Check if we got function calls
        if message.tool_calls:
            print(message.tool_calls)
            assert len(message.tool_calls) > 0

            # Execute all function calls and verify results
            function_names = [tc.function.name for tc in message.tool_calls]
            results = []

            for tool_call in message.tool_calls:
                arguments = json.loads(tool_call.function.arguments)
                result = execute_function_call(tool_call.function.name, arguments)
                results.append(result)

                # Verify specific function results
                if tool_call.function.name == "add_numbers":
                    # Should be adding 15 + 25 = 40
                    assert result == 40
                elif tool_call.function.name == "multiply_numbers":
                    # Should be multiplying 8 * 7 = 56
                    assert result == 56

            # Should have called at least one math function
            assert any(
                name in ["add_numbers", "multiply_numbers"] for name in function_names
            )
            print(f"Successfully called functions: {function_names}")
            print(f"Results: {results}")
        else:
            # If no function calls, the model might have calculated directly
            # This is acceptable behavior for some implementations
            print(f"Model provided direct calculation: {message.content}")
            assert message.content is not None
            assert len(message.content.strip()) > 0

    def test_complex_multi_function_scenario(self, client, all_tools):
        """Test a complex scenario requiring multiple different functions."""
        messages = [
            {
                "role": "user",
                "content": """I'm planning a trip to London. Can you help me with:
                1. Get the weather in London
                2. Find the current stock price of Microsoft (MSFT)
                3. Calculate a 20% tip on a $85 restaurant bill
                4. Convert $100 USD to British Pounds (GBP)""",
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=all_tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None
        assert len(message.tool_calls) > 0

        # Execute all function calls
        function_names = [tc.function.name for tc in message.tool_calls]
        expected_functions = [
            "get_weather",
            "get_stock_price",
            "calculate_tip",
            "convert_currency",
        ]

        # Should call at least 3 of the 4 expected functions
        found_functions = sum(
            1 for func in expected_functions if func in function_names
        )
        assert found_functions >= 3

        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)
            result = execute_function_call(tool_call.function.name, arguments)
            assert result is not None

    def test_function_call_with_search(self, client):
        """Test function calling that includes web search."""
        messages = [
            {
                "role": "user",
                "content": "Search for information about artificial intelligence and also get the weather in San Francisco.",
            }
        ]

        # Include search and weather functions
        search_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information on a topic.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "max_results": {
                                "type": "integer",
                                "description": "Max results",
                                "default": 5,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather information for a location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City or location name",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "default": "celsius",
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=search_tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None

        function_names = [tc.function.name for tc in message.tool_calls]
        assert "search_web" in function_names or "get_weather" in function_names

        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)
            result = execute_function_call(tool_call.function.name, arguments)

            if tool_call.function.name == "search_web":
                assert isinstance(result, list)
                assert len(result) > 0
            elif tool_call.function.name == "get_weather":
                assert isinstance(result, dict)
                assert "location" in result

    def test_streaming_multiple_functions(self, client):
        """Test streaming with multiple function calls."""
        messages = [
            {
                "role": "user",
                "content": "Add 10 and 20, then multiply the result by 5. Show me the calculations.",
            }
        ]

        math_tools = [
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
            },
            {
                "type": "function",
                "function": {
                    "name": "multiply_numbers",
                    "description": "Multiply two numbers together.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number", "description": "First number"},
                            "b": {"type": "number", "description": "Second number"},
                        },
                        "required": ["a", "b"],
                    },
                },
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=math_tools,
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

        for func_call in function_calls:
            if "name" in func_call and "arguments" in func_call:
                arguments = json.loads(func_call["arguments"])
                result = execute_function_call(func_call["name"], arguments)
                assert isinstance(result, (int, float))

    def test_function_choice_specificity(self, client, all_tools):
        """Test that the model chooses appropriate functions for specific tasks."""
        test_cases = [
            {"message": "What's 5 times 7?", "expected_function": "multiply_numbers"},
            {
                "message": "What's the weather in Tokyo?",
                "expected_function": "get_weather",
            },
            {
                "message": "What's Apple's stock price?",
                "expected_function": "get_stock_price",
            },
            {
                "message": "Calculate tip for a $50 bill",
                "expected_function": "calculate_tip",
            },
        ]

        for test_case in test_cases:
            messages = [{"role": "user", "content": test_case["message"]}]

            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=all_tools,
                tool_choice="auto",
            )

            message = response.choices[0].message
            if message.tool_calls:
                function_names = [tc.function.name for tc in message.tool_calls]
                assert test_case["expected_function"] in function_names

    def test_parallel_function_execution(self, client, all_tools):
        """Test parallel execution of multiple independent functions."""
        messages = [
            {
                "role": "user",
                "content": "Get me the weather in Paris, the stock price of Tesla, and search for information about renewable energy.",
            }
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=all_tools,
            tool_choice="auto",
        )

        assert response is not None
        message = response.choices[0].message
        assert message.tool_calls is not None
        assert len(message.tool_calls) >= 2  # Should call multiple functions

        # Execute all functions in parallel (simulate)
        results = []
        for tool_call in message.tool_calls:
            arguments = json.loads(tool_call.function.arguments)
            result = execute_function_call(tool_call.function.name, arguments)
            results.append({"function": tool_call.function.name, "result": result})

        # Verify we got results from different function types
        function_types = {r["function"] for r in results}
        assert len(function_types) >= 2

    def test_function_call_error_recovery(self, client):
        """Test error recovery when one function fails."""
        messages = [
            {
                "role": "user",
                "content": "Add 5 and 10, then get the weather for an invalid location.",
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
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather information for a location.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "Location name",
                            },
                        },
                        "required": ["location"],
                    },
                },
            },
        ]

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )

        message = response.choices[0].message
        if message.tool_calls:
            # At least one function should be called
            assert len(message.tool_calls) > 0

            # Execute functions and handle errors gracefully
            for tool_call in message.tool_calls:
                arguments = json.loads(tool_call.function.arguments)
                result = execute_function_call(tool_call.function.name, arguments)
                # Should get some result, even if it's an error message
                assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
