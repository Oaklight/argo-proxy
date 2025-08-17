import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
BASE_URL = os.getenv("BASE_URL")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. Chicago, IL",
                    },
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        },
    }
]

messages = [
    {
        "role": "user",
        "content": "What's the weather like in Chicago and Shanghai today?",
    }
]
response = client.chat.completions.create(
    model="gemini-2.5-flash", messages=messages, tools=tools, tool_choice="auto"
)

print(response)


mock_tool_call = {
    "role": "assistant",
    "tool_calls": [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Chicago, IL", "unit": "fahrenheit"}',
            },
        },
        {
            "id": "call_abc124",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Shanghai, China", "unit": "fahrenheit"}',
            },
        },
    ],
    "content": "",
}

# order of results must match order of tool calls, regardless whether there are tool_call_id or not
mock_tool_result = [
    {
        "role": "tool",
        "tool_call_id": "call_abc123",
        "name": "get_weather",
        "content": '{"temperature": 72, "unit": "fahrenheit", "description": "Sunny"}',
    },
    {
        "role": "tool",
        "tool_call_id": "call_abc124",
        "name": "get_weather",
        "content": '{"temperature": 100, "unit": "fahrenheit", "description": "Sunny"}',
    },
]

messages.append(mock_tool_call)
messages.append(mock_tool_result)
response = client.chat.completions.create(
    model="gemini-2.5-flash", messages=messages, tools=tools, tool_choice="auto"
)
print(response)
