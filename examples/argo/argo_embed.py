import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:text-embedding-3-small")

EMBED_ENDPOINT = f"{BASE_URL}/v1/embed"


def embed_test():
    print("Running Embed Test with Messages")

    payload = {
        "model": MODEL,
        "input": ["What is your name", "What is your favorite color?"],
    }
    headers = {"Content-Type": "application/json"}

    response = requests.post(EMBED_ENDPOINT, headers=headers, json=payload)

    try:
        response.raise_for_status()
        print("Response Status Code:", response.status_code)
        print("Response Body:", json.dumps(response.json(), indent=4))
    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)
        print("Response Body:", response.text)
        exit(1)


if __name__ == "__main__":
    embed_test()
