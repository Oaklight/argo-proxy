import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from dev_scripts directory
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configuration
BASE_URL = os.getenv("BASE_URL", "https://api.openai.com")
MODEL = os.getenv("MODEL", "gpt-4o")
API_KEY = os.getenv("API_KEY", "sk-your-openai-api-key")
TOOL_CALL = os.getenv("TOOL_CALL", "false").lower() == "true"

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions"


# Test Case: Successful Chat Request with Messages
if TOOL_CALL:
    print("Running Chat Test with Tool Calls")
else:
    print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
if TOOL_CALL:
    # Tool call test payload
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": "Could you check the current stock price of Apple for me?",
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "add",
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
                    "name": "get_stock_price",
                    "description": "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "The stock ticker symbol, e.g. AAPL for Apple Inc.",
                            }
                        },
                        "required": ["ticker"],
                    },
                },
            },
        ],
        "tool_choice": "auto",
        "user": "test_user",
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
    }
else:
    # Regular chat test payload
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                # "content": "Tell me something interesting about quantum mechanics.",
                "content": [
                    {
                        "type": "text",
                        "text": "Tell me something interesting about quantum mechanics.",
                    }
                ],
            },
        ],
        "user": "test_user",  # This will be overridden by the proxy_request function
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
        "max_tokens": 5,
    }
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

with httpx.stream(
    "POST", CHAT_ENDPOINT, json=payload, headers=headers, timeout=60.0
) as response:
    print("Status Code: ", response.status_code)
    print("Headers: ", response.headers)
    print("Streaming Response: ")

    # Read the resonse chunks as they arrive
    for chunk in response.iter_bytes():
        if chunk:
            print(chunk.decode(errors="replace"), end="", flush=True)
