# Test single tool call with Gemini API
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

# Test 1: Initial request asking for weather
print("=== Test 1: Initial tool call request ===")
messages = [
    {
        "role": "user",
        "content": "What's the weather like in Chicago today?",
    }
]

data = {
    "user": "pding",
    "model": "gemini25flash",
    "messages": messages,
    "stop": [],
    "temperature": 0.1,
    "top_p": 0.9,
    "tools": tools,
}

headers = {"Content-Type": "application/json"}
payload = json.dumps(data)
response = httpx.post(url, data=payload, headers=headers)

print("Status Code:", response.status_code)
try:
    response_data = response.json()["response"]
    print("LLM response:", response_data)

    # Extract tool calls if any
    tool_calls = response_data.get("tool_calls", [])
    if tool_calls:
        print(f"Found {len(tool_calls)} tool call(s)")
        for i, tc in enumerate(tool_calls):
            print(f"  Tool call {i + 1}: {tc}")
    else:
        print("No tool calls found")

except Exception as e:
    print(f"Error parsing JSON response: {e}")
    print("Raw response text:", response.text)

print("\n" + "=" * 50 + "\n")

# Test 2: If we got tool calls, simulate tool execution and send results
if response.status_code == 200:
    try:
        response_data = response.json()["response"]
        tool_calls = response_data.get("tool_calls", [])

        if tool_calls:
            print("=== Test 2: Sending tool results ===")

            # Add the assistant's response with tool calls to conversation
            assistant_message = {
                "role": "assistant",
                "content": response_data.get("content", ""),
                "tool_calls": [],
            }

            # Convert tool calls to OpenAI format for the conversation
            for tc in tool_calls:
                openai_tool_call = {
                    "id": tc.get("id")
                    or f"call_{len(assistant_message['tool_calls'])}",
                    "type": "function",
                    "function": {
                        "name": tc.get("name"),
                        "arguments": json.dumps(tc.get("args", {})),
                    },
                }
                assistant_message["tool_calls"].append(openai_tool_call)

            messages.append(assistant_message)

            # Add tool results - one for each tool call
            for i, tc in enumerate(tool_calls):
                tool_result = {
                    "role": "tool",
                    "tool_call_id": assistant_message["tool_calls"][i]["id"],
                    "name": tc.get("name"),
                    "content": json.dumps(
                        {
                            "temperature": 72,
                            "unit": "fahrenheit",
                            "description": "Sunny",
                        }
                    ),
                }
                messages.append(tool_result)

            print("Updated messages:")
            for i, msg in enumerate(messages):
                print(f"  Message {i + 1}: {msg}")

            # Send the updated conversation
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
                print("LLM response:", response.json()["response"])
            except Exception as e:
                print(f"Error parsing JSON response: {e}")
                print("Raw response text:", response.text)
        else:
            print("No tool calls to follow up on")

    except Exception as e:
        print(f"Error in test 2: {e}")
