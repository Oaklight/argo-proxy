import os

import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat"


print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
payload = {
    "model": MODEL,
    "prompt": [
        "Tell me something interesting about quantum mechanics. longer passage",
        "Wait, I changed my mind. Tell me about the history of the Internet instead.",
    ],
    "stream": True,
}
headers = {
    "Content-Type": "application/json",
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
