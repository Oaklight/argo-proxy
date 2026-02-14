"""Function calling example using Anthropic SDK via argo-proxy native Anthropic mode.

Prerequisites:
    - argo-proxy running with --native-anthropic flag
    - pip install anthropic

Usage:
    python function_calling.py

Environment variables:
    BASE_URL: Proxy base URL (default: http://localhost:44497)
    MODEL: Model to use (default: argo:claude-4.5-sonnet)
    API_KEY: Your ANL username for authentication
"""

import json
import os

import anthropic

BASE_URL = os.environ.get("BASE_URL", "http://localhost:44497")
MODEL = os.environ.get("MODEL", "argo:claude-4.5-sonnet")
API_KEY = os.environ.get("API_KEY", "your-anl-username")


def get_weather(location: str, unit: str = "celsius") -> str:
    """Simulated weather function."""
    weather_data = {
        "San Francisco": {"temperature": 18, "condition": "foggy"},
        "New York": {"temperature": 25, "condition": "sunny"},
        "London": {"temperature": 15, "condition": "rainy"},
    }
    data = weather_data.get(location, {"temperature": 20, "condition": "unknown"})
    if unit == "fahrenheit":
        data["temperature"] = data["temperature"] * 9 / 5 + 32
    return json.dumps(data)


def main():
    client = anthropic.Anthropic(
        base_url=BASE_URL,
        api_key=API_KEY,
    )

    tools = [
        {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city name, e.g. San Francisco",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["location"],
            },
        }
    ]

    messages = [
        {"role": "user", "content": "What's the weather like in San Francisco?"}
    ]

    print("=== Step 1: Initial request with tools ===")
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        tools=tools,
        messages=messages,
    )
    print(f"Stop reason: {response.stop_reason}")
    print(f"Content: {response.content}")

    # Check if the model wants to use a tool
    if response.stop_reason == "tool_use":
        # Find the tool use block
        tool_use = next(block for block in response.content if block.type == "tool_use")
        print(f"\nTool called: {tool_use.name}")
        print(f"Tool input: {tool_use.input}")

        # Execute the tool
        tool_result = get_weather(**tool_use.input)
        print(f"Tool result: {tool_result}")

        # Send the tool result back
        print("\n=== Step 2: Send tool result ===")
        messages.append({"role": "assistant", "content": response.content})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": tool_result,
                    }
                ],
            }
        )

        final_response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=tools,
            messages=messages,
        )
        print(f"Final response: {final_response.content[0].text}")
    else:
        print(f"Response: {response.content[0].text}")


if __name__ == "__main__":
    main()
