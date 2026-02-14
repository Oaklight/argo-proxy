import os

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:o1-mini")

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat"

# system_prompt = (
#     "You are a super smart and helpful AI. You always answer truthfully and provide "
#     "the answer directly if you can. If you can't answer because you don't know the "
#     "answer you say I don't know or you provide help in rephrasing the question. "
#     "You do not give meta answers."
# )
user_message = (
    "You are a super smart and helpful AI. You always answer truthfully and provide "
    "the answer directly if you can. If you can't answer because you don't know the "
    "answer you say I don't know or you provide help in rephrasing the question. "
    "You do not give meta answers."
    "Please generate four hypotheses on the origins of life that could be explored with a "
    "self-driving laboratory. For each example please list the key equipment and instruments "
    "that would be needed and the experimental protocols that would need to be automated to "
    "test the hypotheses."
)

print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
payload = {
    "model": MODEL,
    # "system": system_prompt,
    "prompt": [user_message],
    "stream": True,
}
headers = {
    "Content-Type": "application/json",
}

with httpx.stream(
    "POST", CHAT_ENDPOINT, json=payload, headers=headers, timeout=60.0
) as response:
    print("Status Code: ", response.status_code)
    print("Headers: ", response.headers)
    print("Streaming Response: ")

    # Read the resonse chunks as they arrive
    for chunk in response.iter_bytes():
        if chunk:
            print(chunk.decode(errors="replace"), end="", flush=True)
