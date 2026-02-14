import os

import httpx
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file if n

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")

CHAT_ENDPOINT = f"{BASE_URL}/v1/responses"


def stream_chat_test():
    print("Running Chat Test with Streaming")

    payload = {
        "model": MODEL,
        "input": [
            {
                "role": "user",
                "content": "Tell me something interesting about quantum mechanics.",
            },
        ],
        "stream": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('API_KEY', 'your-anl-username')}",
    }

    try:
        with httpx.stream(
            "POST", CHAT_ENDPOINT, json=payload, headers=headers, timeout=60.0
        ) as response:
            print("Status Code: ", response.status_code)
            print("Headers: ", response.headers)
            print("Streaming Response: ")

            for chunk in response.iter_bytes():
                if chunk:
                    print(chunk.decode(errors="replace"), end="", flush=True)
    except Exception as e:
        print("\nError:", e)


if __name__ == "__main__":
    stream_chat_test()
