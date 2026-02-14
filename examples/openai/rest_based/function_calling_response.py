import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")
API_KEY = os.getenv("API_KEY", "your-anl-username")

RESPONSES_ENDPOINT = f"{BASE_URL}/v1/responses"


def make_response_request():
    print("Running Math Function Calling Example")

    payload = {
        "model": MODEL,
        "input": [
            {
                "role": "system",
                "content": "You are a helpful math assistant.",
            },
            {
                "role": "user",
                "content": "What is 5 plus 19?",
            },
        ],
        "tools": [
            {
                "type": "function",
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
                "strict": False,
            }
        ],
        "tool_choice": "auto",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    try:
        response = httpx.post(
            RESPONSES_ENDPOINT, json=payload, headers=headers, timeout=60.0
        )
        print("Status Code:", response.status_code)
        print("Response JSON:", json.dumps(response.json(), indent=4))
    except Exception as e:
        print("\nError:", e)


if __name__ == "__main__":
    make_response_request()
