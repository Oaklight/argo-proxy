import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat"

# Test Case: Successful Chat Request with Messages
print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
payload = {
    "model": MODEL,
    "prompt": [
        "Tell me something interesting about quantum mechanics. longer passage",
        "Wait, I changed my mind. Tell me about the history of the Internet instead.",
    ],
    "user": "test_user",  # This will be overridden by the proxy_request function
}
headers = {"Content-Type": "application/json"}

# Send the POST request
response = requests.post(CHAT_ENDPOINT, headers=headers, json=payload)

try:
    response.raise_for_status()
    print("Response Status Code:", response.status_code)
    print("Response Body:", json.dumps(response.json(), indent=4))
except requests.exceptions.HTTPError as err:
    print("HTTP Error:", err)
    print("Response Body:", response.text)
