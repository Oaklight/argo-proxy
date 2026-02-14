import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")

CHAT_ENDPOINT = f"{BASE_URL}/v1/completions"

# Test Case: Successful Chat Request with Messages
print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
payload = {
    "model": MODEL,
    "prompt": ["Tell me something interesting about quantum mechanics."],
    "user": "test_user",  # This will be overridden by the proxy_request function
    # "max_tokens": 5,
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
