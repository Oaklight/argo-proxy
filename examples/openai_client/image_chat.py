import base64
import mimetypes
import os
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "argo:gpt-4o")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44501")
API_KEY = os.getenv("API_KEY", "whatever+random")
STREAM = os.getenv("STREAM", "false").lower() == "true"

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=f"{BASE_URL}/v1",
)

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

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe these images."},
                {"type": "image_url", "image_url": {"url": f"{file_url_1}"}},
                {"type": "image_url", "image_url": {"url": f"{file_url_2}"}},
            ],
        },
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=4096,
            stream=STREAM,
        )
        print("Response Body:")
        if STREAM:
            for chunk in response:
                # Stream each chunk as it arrives
                print(chunk)
        else:
            print(response)
    except Exception as e:
        print("\nError:", e)


if __name__ == "__main__":
    image_chat_test()
