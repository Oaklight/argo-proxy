import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")
API_KEY = os.getenv("API_KEY", "whatever+random")
STREAM = os.getenv("STREAM", "false").lower() == "true"

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions"

print("Running Math Function Calling Example (Raw Request)")

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful math assistant."},
        {"role": "user", "content": "What is 12 plus 30?"},
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
        }
    ],
    "tool_choice": "auto",
    "max_tokens": 256,
    "stream": STREAM,
}
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}

# Send the POST request
response = requests.post(CHAT_ENDPOINT, headers=headers, json=payload)

try:
    response.raise_for_status()
    print("Response Status Code:", response.status_code)

    if STREAM:
        # Handle streaming response
        print("Streaming Response:")
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data_part = line[6:]  # Remove 'data: ' prefix
                    if data_part.strip() == "[DONE]":
                        break
                    try:
                        print(json.dumps(json.loads(data_part), indent=2))
                    except json.JSONDecodeError:
                        print(f"Non-JSON data: {data_part}")
    else:
        # Handle non-streaming response
        print("Response Body:", json.dumps(response.json(), indent=4))

except requests.exceptions.HTTPError as err:
    print("HTTP Error:", err)
    print("Response Body:", response.text)
except Exception as err:
    print("Error:", err)
    print("Response Body:", response.text)
