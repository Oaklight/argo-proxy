import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")

RESPONSES_ENDPOINT = f"{BASE_URL}/v1/responses"


def make_response_request():
    print("Running Single Response Request")

    payload = {
        "model": MODEL,
        "input": [
            {
                "role": "user",
                "content": "Tell me something interesting about quantum mechanics.",
            },
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('API_KEY', 'your-anl-username')}",
    }

    try:
        response = httpx.post(
            RESPONSES_ENDPOINT, json=payload, headers=headers, timeout=60.0
        )
        print("Status Code:", response.status_code)
        print("Response JSON:", response.json())
    except Exception as e:
        print("\nError:", e)


if __name__ == "__main__":
    make_response_request()
