import os

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "argo:gpt-4o")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
API_KEY = os.getenv("API_KEY", "your-anl-username")

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=f"{BASE_URL}/v1",
)


def chat_test():
    print("Running Chat Test with Messages")

    prompt = ["Tell me something interesting about quantum mechanics."]
    # max_tokens = 5

    try:
        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            # max_tokens=max_tokens,
        )
        print("Response:")
        print(response)
    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    chat_test()
