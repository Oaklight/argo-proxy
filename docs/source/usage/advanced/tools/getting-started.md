# Getting Started with Tool Calls (Function Calling)

Tool calls, also known as function calling, allow AI models to request the execution of external functions. This feature has been available since version v2.7.5.alpha1 and now includes **native function calling support** for OpenAI, Anthropic, and Gemini models (added in v2.8.0).

## What is Tool Calling?

**Important**: Tool calling is often misunderstood. Let's clarify what actually happens:

### The Reality of Tool Calling

1. **LLMs don't execute functions** - They cannot and do not run your code
2. **LLMs only see descriptions** - They work with JSON schemas that describe your functions
3. **LLMs make requests** - They tell you what function to call and with what arguments
4. **You do the work** - Your application executes the function and returns results
5. **LLMs process results** - They incorporate the function results into their response

### The Tool Calling Workflow

```
User: "What's the weather in Shanghai?"
  ↓
LLM: "I need to call get_weather function with location='Shanghai'"
  ↓
Your App: Executes get_weather("Shanghai") → {"temp": "22°C", "condition": "sunny"}
  ↓
LLM: "The weather in Shanghai is 22°C and sunny"
```

### What LLMs Actually See

When you provide a function schema, the LLM only sees the description:

```json
{
  "name": "get_weather",
  "description": "Get current weather for a location",
  "parameters": {
    "type": "object",
    "properties": {
      "location": { "type": "string", "description": "City name" }
    }
  }
}
```

The LLM has **no knowledge** of your actual implementation - it only knows what you tell it in the description.

## Basic Example

Here's a simple example to get you started:

```python
import openai
import json

client = openai.OpenAI(
    base_url="http://localhost:44497/v1",
    api_key="dummy"
)

# Step 1: Implement your function
def get_weather(location: str) -> dict:
    """Get current weather for a location"""
    return {
        "location": location,
        "temperature": "22°C",
        "condition": "sunny",
        "humidity": "65%"
    }

# Step 2: Create the JSON schema
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or 'City, Country' format"
                    }
                },
                "required": ["location"]
            }
        }
    }
]

# Step 3: Function execution handler
def execute_function_call(function_name: str, arguments: dict):
    """Execute the actual function based on LLM's request"""
    if function_name == "get_weather":
        return get_weather(**arguments)
    else:
        return {"error": f"Unknown function: {function_name}"}

# Step 4: Make a request with tool calls
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[
        {"role": "user", "content": "What's the weather in New York?"}
    ],
    tools=tools,
    tool_choice="auto"
)

# Step 5: Handle tool calls in the response
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)

        # Execute the actual function
        result = execute_function_call(function_name, function_args)

        print(f"Function: {function_name}")
        print(f"Arguments: {function_args}")
        print(f"Result: {result}")
```

## Key Points to Remember

- The LLM only sees the schema in `tools`, not your actual function implementation
- You must manually ensure the schema matches your function signature
- You are responsible for executing the function when the LLM requests it
- Always validate and sanitize inputs from the LLM before execution

## Next Steps

- Learn about [OpenAI API Parameters](openai-parameters.md) for tool calls
- Explore [ToolRegistry Integration](toolregistry.md) for simplified tool management
- Check out [Advanced Usage](advanced-usage.md) for complex scenarios

## Availability

- **Available on**: Both streaming and non-streaming **chat completion** endpoints
- **Supported endpoints**: `/v1/chat/completions`
- **Not supported**: Argo passthrough (`/v1/chat`) and legacy completion endpoints (`/v1/completions`)
- **Status**: Production-ready feature with native function calling support

## Native Function Calling

Argo Proxy now supports **native function calling** for supported models:

### Supported Models

- **OpenAI models**: ✅ Full native function calling support
- **Anthropic models**: ✅ Full native function calling support
- **Gemini models**: ✅ Full native function calling support (added in v2.8.0)

### Key Benefits

- **Better Performance**: Native function calling provides improved reliability and speed
- **OpenAI Compatibility**: All input and output remains in standard OpenAI format
- **Seamless Migration**: Existing OpenAI-compatible code works without changes

### Legacy Support

For compatibility, prompting-based function calling is still available:

```bash
# Use legacy prompting-based function calling
argo-proxy --tool-prompting
```

## Supported Models

All chat models support tool calls, with varying levels of native function calling support as detailed above.
