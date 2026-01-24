import os

import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = os.getenv("BASE_URL", "https://api.openai.com")
MODEL = os.getenv("MODEL", "gpt-4o")
API_KEY = os.getenv("API_KEY", "sk-your-openai-api-key")

# BASE_URL = "https://api.openai.com"  # Update if your server is running on a different host/port
# MODEL = "gpt-3.5-turbo-instruct"
# API_KEY = "sk-your-openai-api-key"

CHAT_ENDPOINT = f"{BASE_URL}/v1/completions"

print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
payload = {
    "model": MODEL,
    "prompt": ["Tell me something interesting about quantum mechanics."],
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
