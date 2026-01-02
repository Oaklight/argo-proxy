# Test sequential tool calls with Gemini API - one call at a time
import json

import httpx

url = "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"

# Single tool definition
get_weather = {
    "name": "get_weather",
    "description": "Get the weather in a given location",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city and state, e.g. Chicago, IL",
            },
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
        },
        "required": ["location"],
    },
}

tools = [get_weather]
headers = {"Content-Type": "application/json"}


def make_request(messages, description=""):
    """Helper function to make API request"""
    print(f"\n=== {description} ===")
    data = {
        "user": "pding",
        "model": "gemini25flash",
        "messages": messages,
        "stop": [],
        "temperature": 0.1,
        "top_p": 0.9,
        "tools": tools,
    }

    payload = json.dumps(data)
    response = httpx.post(url, data=payload, headers=headers)

    print("Status Code:", response.status_code)
    try:
        response_data = response.json()["response"]
        print("LLM response:", response_data)
        return response_data
    except Exception as e:
        print(f"Error parsing JSON response: {e}")
        print("Raw response text:", response.text)
        return None


# Start conversation
messages = [
    {
        "role": "user",
        "content": "What's the weather like in Chicago and Shanghai today?",
    }
]

# First request - should get multiple tool calls
response_data = make_request(messages, "Initial request for multiple locations")

if response_data and response_data.get("tool_calls"):
    tool_calls = response_data.get("tool_calls", [])
    print(f"\nFound {len(tool_calls)} tool calls")

    # Process each tool call individually
    for i, tc in enumerate(tool_calls):
        print(f"\n--- Processing tool call {i + 1}: {tc['name']} ---")

        # Add assistant message with single tool call
        assistant_message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
            ],
        }
        messages.append(assistant_message)

        # Add tool result for this specific call
        location = tc["args"].get("location", "Unknown")
        temp = 72 if "Chicago" in location else 25
        unit = "fahrenheit" if "Chicago" in location else "celsius"

        tool_result = {
            "role": "tool",
            "tool_call_id": f"call_{i}",
            "name": tc["name"],
            "content": json.dumps(
                {
                    "temperature": temp,
                    "unit": unit,
                    "description": "Sunny",
                    "location": location,
                }
            ),
        }
        messages.append(tool_result)

        print(f"Added tool call and result for {location}")
        print(f"Current conversation length: {len(messages)} messages")

    # Final request with all tool calls and results
    final_response = make_request(messages, "Final request with all tool results")

    print("\n=== Final Conversation ===")
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")[:50]
        if msg.get("tool_calls"):
            print(
                f"Message {i + 1}: {role} - {content}... [+{len(msg['tool_calls'])} tool calls]"
            )
        elif role == "tool":
            print(f"Message {i + 1}: {role} - {msg.get('name')} -> {content}...")
        else:
            print(f"Message {i + 1}: {role} - {content}...")

else:
    print("No tool calls found in initial response")
