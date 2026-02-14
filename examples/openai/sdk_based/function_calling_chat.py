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


def run_function_calling_example():
    print("Running Simple Math Function Calling Example")

    messages = [
        {
            "role": "user",
            # "content": "What is 8 plus 5? Use the add function to calculate this.",
            "content": "Could you check the current stock price of Apple for me?",
        }
    ]
    tools = [
        {
            "type": "function",
            "function": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_stock_price",
                "description": "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "The stock ticker symbol, e.g. AAPL for Apple Inc.",
                        }
                    },
                    "required": ["ticker"],
                },
            },
        },
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
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
    run_function_calling_example()
