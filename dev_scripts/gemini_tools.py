import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_HTTP_OPTIONS = {"base_url": "https://generativelanguage.googleapis.com/"}
print(GEMINI_HTTP_OPTIONS)

# Define the function declaration for the model
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


# Configure the client and tools
client = genai.Client(api_key=GEMINI_API_KEY, http_options=GEMINI_HTTP_OPTIONS)
house_tools = [
    types.Tool(function_declarations=[power_disco_ball, start_music, dim_lights])
]
config = types.GenerateContentConfig(
    tools=house_tools,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    # Force the model to call 'any' function, instead of chatting.
    tool_config=types.ToolConfig(
        function_calling_config=types.FunctionCallingConfig(mode="ANY")
    ),
)


messages = [
    types.Content(parts=[types.Part(text="Turn this place into a party!")], role="user")
]
response = client.models.generate_content(
    model="gemini-2.5-flash", contents=messages, config=config
)


results = []
# Print out each of the function calls requested from this single call
print("Example 1: Forced function calling")
for fn in response.function_calls:
    # args = ", ".join(f"{key}={val}" for key, val in fn.args.items())
    # print(f"{fn.name}({args})")
    print(fn)
    # fake some response
    results.append(
        types.Part.from_function_response(name=fn.name, response={"result": "done"})
    )
# print(response.candidates)

messages.append(response.candidates[0].content)
messages.append(types.Content(parts=results, role="user"))

print(messages)
response = client.models.generate_content(
    model="gemini-2.5-pro", contents=messages, config=config
)
print(response.candidates)
