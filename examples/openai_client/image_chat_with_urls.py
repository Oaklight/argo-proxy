import os

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

print("Running Chat Test with Direct Image URLs")


def image_chat_test_with_urls():
    # Using direct HTTP URLs with different supported formats - these will be automatically converted to base64 by the proxy
    # JPEG format
    image_url_1 = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
    # PNG format
    image_url_2 = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Vd-Orig.png/256px-Vd-Orig.png"
    # WebP format (if available)
    image_url_3 = "https://convertico.com/samples/webp/webp-sample.webp"
    # GIF format (if available)
    image_url_4 = "https://convertico.com/samples/gif/gif-sample.gif"

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe these images in detail."},
                {"type": "image_url", "image_url": {"url": image_url_1}},
                {"type": "image_url", "image_url": {"url": image_url_2}},
                {"type": "image_url", "image_url": {"url": image_url_3}},
                {"type": "image_url", "image_url": {"url": image_url_4}},
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
