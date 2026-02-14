import os

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "argo:text-embedding-3-small")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
API_KEY = os.getenv("API_KEY", "your-anl-username")

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=f"{BASE_URL}/v1",
)


def embed_test():
    print("Running Embed Test with OpenAI Embeddings")

    input_texts = ["What is your name", "What is your favorite color?"]

    response = client.embeddings.create(model=MODEL, input=input_texts)
    print("Embedding Response:")
    print(response)


if __name__ == "__main__":
    embed_test()
