import base64
import json
import mimetypes
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44501")
MODEL = os.getenv("MODEL", "argo:gpt-4o")
STREAM = os.getenv("STREAM", "false").lower() == "true"

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions"

print("Running Chat Test with Image Messages")

# Directory containing images + image file names
dir = Path.home() / "Pictures/little_cats/"
file_1 = "448442433_1527967368068703_1725008954157370702_n.jpg"
file_2 = "431513414_425984513169245_6323352679907592165_n.jpg"
files_in_dir = [dir / file_1, dir / file_2]


def file_to_data_url(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "application/octet-stream"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def image_chat_test():
    file_url_1, file_url_2 = [file_to_data_url(file_path) for file_path in files_in_dir]
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe these images."},
                    {"type": "image_url", "image_url": {"url": f"{file_url_1}"}},
                    {"type": "image_url", "image_url": {"url": f"{file_url_2}"}},
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
    image_chat_test()
