# Define the function declaration for the model
import json

import httpx

url = "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"

schedule_meeting_function = {
    "name": "schedule_meeting",
    "description": "Schedules a meeting with specified attendees at a given time and date.",
    "parameters": {
        "type": "object",
        "properties": {
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of people attending the meeting.",
            },
            "date": {
                "type": "string",
                "description": "Date of the meeting (e.g., '2024-07-29')",
            },
            "time": {
                "type": "string",
                "description": "Time of the meeting (e.g., '15:00')",
            },
            "topic": {
                "type": "string",
                "description": "The subject or topic of the meeting.",
            },
        },
        "required": ["attendees", "date", "time", "topic"],
    },
}

power_disco_ball = {
    "name": "power_disco_ball",
    "description": "Powers the spinning disco ball.",
    "parameters": {
        "type": "object",
        "properties": {
            "power": {
                "type": "boolean",
                "description": "Whether to turn the disco ball on or off.",
            }
        },
        "required": ["power"],
    },
}

start_music = {
    "name": "start_music",
    "description": "Play some music matching the specified parameters.",
    "parameters": {
        "type": "object",
        "properties": {
            "energetic": {
                "type": "boolean",
                "description": "Whether the music is energetic or not.",
            },
            "loud": {
                "type": "boolean",
                "description": "Whether the music is loud or not.",
            },
        },
        "required": ["energetic", "loud"],
    },
}

dim_lights = {
    "name": "dim_lights",
    "description": "Dim the lights.",
    "parameters": {
        "type": "object",
        "properties": {
            "brightness": {
                "type": "number",
                "description": "The brightness of the lights, 0.0 is off, 1.0 is full.",
            }
        },
        "required": ["brightness"],
    },
}

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

tools = [
    schedule_meeting_function,
    power_disco_ball,
    start_music,
    dim_lights,
    get_weather,
]

messages = [
    {
        "role": "user",
        "content": "What's the weather like in Chicago and Shanghai today?",
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


headers = {
    "Content-Type": "application/json",
}


# Convert the dict to JSON
payload = json.dumps(data)
# Send POST request
response = httpx.post(url, data=payload, headers=headers)

# Receive the response data
print("Status Code:", response.status_code)
try:
    print("LLM response: ", response.json()["response"])
except Exception as e:
    print(f"Error parsing JSON response: {e}")
    print("Raw response text: ", response.text)


mock_tool_call = {
    "role": "assistant",
    "tool_calls": [
        {
            "id": None,
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Chicago, IL", "unit": "fahrenheit"}',
            },
        },
        {
            "id": None,
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": '{"location": "Shanghai, China", "unit": "fahrenheit"}',
            },
        },
    ],
    "content": "",
}

mock_tool_result = [
    {
        "role": "tool",
        "tool_call_id": None,
        "name": "get_weather",
        "content": '{"temperature": 72, "unit": "fahrenheit", "description": "Sunny"}',
    },
    {
        "role": "tool",
        "tool_call_id": None,
        "name": "get_weather",
        "content": '{"temperature": 100, "unit": "fahrenheit", "description": "Sunny"}',
    },
]

messages.append(mock_tool_call)
messages.extend(mock_tool_result)

data = {
    "user": "pding",
    "model": "gemini25flash",
    "messages": messages,
    "stop": [],
    "temperature": 0.1,
    "top_p": 0.9,
    "tools": tools,
}


# Convert the dict to JSON
payload = json.dumps(data)
# Send POST request
response = httpx.post(url, data=payload, headers=headers)

# Receive the response data
print("Status Code:", response.status_code)
try:
    print("LLM response: ", response.json()["response"])
except Exception as e:
    print(f"Error parsing JSON response: {e}")
    print("Raw response text: ", response.text)
