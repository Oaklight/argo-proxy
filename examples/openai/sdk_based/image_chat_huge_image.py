import os

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "argo:gpt-4o")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44501")
API_KEY = os.getenv("API_KEY", "your-anl-username")
STREAM = os.getenv("STREAM", "false").lower() == "true"

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=f"{BASE_URL}/v1",
)

print("Running Chat Test with Direct Image URLs")


def image_chat_test_with_urls():
    huge_image = "https://svs.gsfc.nasa.gov/vis/a030000/a030800/a030877/frames/5760x3240_16x9_01p/BlackMarble_2016_928m_canada_s_labeled.png"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe these images in detail."},
                {"type": "image_url", "image_url": {"url": huge_image}},
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
    image_chat_test_with_urls()
