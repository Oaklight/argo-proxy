import os

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("MODEL", "argo:gpt-4o")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
API_KEY = os.getenv("API_KEY", "your-anl-username")
STREAM = os.getenv("STREAM", "false").lower() == "true"

client = openai.OpenAI(
    api_key=API_KEY,
    base_url=f"{BASE_URL}/v1",
)


def stream_function_calling_add_test():
    print("Running Math Function Calling Example with Streaming")

    messages = [
        {"role": "system", "content": "You are a helpful math assistant."},
        {
            "role": "user",
            "content": "What is 15 plus 27?",
        },
    ]

    tools = [
        {
            "type": "function",
            "name": "add",
            "description": "Add two numbers together.",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["a", "b"],
            },
            "strict": False,
        }
    ]

    try:
        response = client.responses.create(
            model=MODEL,
            instructions="Show your reasoning step by step.",
            input=messages,
            tools=tools,
            tool_choice={"type": "function", "name": "add"},
            stream=STREAM,
        )
        print("Streaming Response:")
        # check if response is iterable
        if STREAM:
            for event in response:
                print(event)
        else:
            print(response)
    except Exception as e:
        print("\nError:", e)


if __name__ == "__main__":
    stream_function_calling_add_test()
