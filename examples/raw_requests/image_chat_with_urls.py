import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44501")
MODEL = os.getenv("MODEL", "argo:gpt-4o")
STREAM = os.getenv("STREAM", "false").lower() == "true"

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions"

print("Running Chat Test with Direct Image URLs")


def image_chat_test_with_urls():
    # Using direct HTTP URLs - these will be automatically converted to base64 by the proxy
    image_url_1 = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
    image_url_2 = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Vd-Orig.png/256px-Vd-Orig.png"

    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe these images in detail."},
                    {"type": "image_url", "image_url": {"url": image_url_1}},
                    {"type": "image_url", "image_url": {"url": image_url_2}},
                ],
            },
        ],
        "model": MODEL,
        "max_tokens": 4096,
        "stream": STREAM,
    }
    headers = {
        "Content-Type": "application/json",
    }

    # Send the POST request
    response = requests.post(
        CHAT_ENDPOINT, headers=headers, json=payload, stream=STREAM
    )

    try:
        response.raise_for_status()
        print("Response Status Code:", response.status_code)

        if STREAM:
            print("Streaming response:")
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode("utf-8")
                    if decoded_line.startswith("data: "):
                        data = decoded_line[6:]  # Remove 'data: ' prefix
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            print(chunk)
                        except json.JSONDecodeError:
                            print(f"Could not decode: {data}")
        else:
            print(response.text)
            print("Response Body:", json.dumps(response.json(), indent=4))
    except requests.exceptions.HTTPError as err:
        print("HTTP Error:", err)
        print("Response Body:", response.text)


if __name__ == "__main__":
    image_chat_test_with_urls()
