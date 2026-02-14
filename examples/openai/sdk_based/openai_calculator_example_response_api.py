import os

from dotenv import load_dotenv
from loguru import logger
from openai import OpenAI
from toolregistry import ToolRegistry
from toolregistry.hub.calculator import Calculator

# Load environment variables from .env file
load_dotenv()


model_name = os.getenv("MODEL", "argo:gpt-4.1")
stream = os.getenv("STREAM", "True").lower() == "true"

API_KEY = os.getenv("API_KEY", "your-api-key")
BASE_URL = os.getenv("BASE_URL", "http://localhost:44500")

# Initialize tool registry and register Calculator static methods
tool_registry = ToolRegistry()
tool_registry.register_from_class(Calculator, with_namespace=False)

# Set up OpenAI client
client = OpenAI(
    api_key=API_KEY,
    base_url=f"{BASE_URL}/v1",
)


def handle_tool_calls_response(response, messages):
    """Handle tool calls in a loop until no more tool calls are needed"""

    def extract_tool_calls(response):
        tool_calls = []
        for each in response.output:
            if each.type == "function_call":
                tool_calls.append(each)
        return tool_calls

    while tool_calls := extract_tool_calls(response):
        for each in response.output:
            if each.type == "function_call":
                tool_calls.append(each)
        logger.warning("Tool calls:", tool_calls)

        # Execute tool calls
        tool_responses = tool_registry.execute_tool_calls(tool_calls)

        # Construct assistant messages with results
        assistant_tool_messages = tool_registry.recover_tool_call_assistant_message(
            tool_calls, tool_responses, api_format="openai-response"
        )

        messages.extend(assistant_tool_messages)

        # Send the results back to the model
        response = client.responses.create(
            model=model_name,
            input=messages,
            tools=tool_registry.get_tools_json(api_format="openai-response"),
            tool_choice="auto",
        )
    return response


messages = [
    {
        "role": "user",
        "content": (
            "You are tasked to examine the Calculator tool. "
            "Especially its help and evaluate method. "
            "Make sure to include a variety of operations and functions. especially those not directly exposed by the Calculator. "
            "Conduct live tests and provide the results."
        ),
    }
]

if __name__ == "__main__":
    logger.warning(tool_registry.list_tools())
    # Make the chat completion request
    response = client.responses.create(
        model=model_name,
        input=messages,
        tools=tool_registry.get_tools_json(api_format="openai-response"),
        tool_choice="auto",
    )
    response = handle_tool_calls_response(response, messages)

    # Print final response
    if response.output:
        logger.info(response.output_text)
