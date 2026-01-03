# OpenAI API Parameters for Tool Calls

This guide explains the specific parameters used when making tool calls with OpenAI-compatible APIs.

## Tool Definition Structure

### Basic Tool Schema

```json
{
  "type": "function",
  "function": {
    "name": "function_name",
    "description": "Clear description of what the function does",
    "parameters": {
      "type": "object",
      "properties": {
        "param1": {
          "type": "string",
          "description": "Description of parameter 1"
        },
        "param2": {
          "type": "number",
          "description": "Description of parameter 2"
        }
      },
      "required": ["param1"]
    }
  }
}
```

### Parameter Types

Supported parameter types in the JSON schema:

- `string`: Text values
- `number`: Numeric values (integers and floats)
- `boolean`: True/false values
- `array`: Lists of values
- `object`: Nested objects

### Advanced Parameter Schema

```json
{
  "type": "object",
  "properties": {
    "location": {
      "type": "string",
      "description": "City and state, e.g. San Francisco, CA"
    },
    "temperature_unit": {
      "type": "string",
      "enum": ["celsius", "fahrenheit"],
      "description": "Temperature unit"
    },
    "include_forecast": {
      "type": "boolean",
      "description": "Whether to include forecast data"
    },
    "days": {
      "type": "number",
      "minimum": 1,
      "maximum": 7,
      "description": "Number of forecast days"
    },
    "categories": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["weather", "temperature", "humidity", "wind"]
      },
      "description": "Data categories to include"
    }
  },
  "required": ["location"]
}
```

## Tool Choice Options

Control when and how tools are called using the `tool_choice` parameter:

### `auto` (Default)

```python
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "What's the weather?"}],
    tools=tools,
    tool_choice="auto"  # Model decides whether to call functions
)
```

The model decides whether to call functions based on the conversation context.

### `none`

```python
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "What's the weather?"}],
    tools=tools,
    tool_choice="none"  # Model will not call any functions
)
```

The model will not call any functions, even if tools are provided.

### `required`

```python
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "What's the weather?"}],
    tools=tools,
    tool_choice="required"  # Model must call at least one function
)
```

Forces the model to call at least one function.

### Specific Function

```python
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "What's the weather?"}],
    tools=tools,
    tool_choice={
        "type": "function",
        "function": {"name": "get_weather"}
    }
)
```

Forces the model to call a specific function.

## Request Parameters

### Complete Request Structure

```python
response = client.chat.completions.create(
    model="argo:gpt-4o",                    # Required: Model name
    messages=[                              # Required: Conversation history
        {"role": "user", "content": "Hello"}
    ],
    tools=[                                 # Optional: Available tools
        {
            "type": "function",
            "function": {
                "name": "my_function",
                "description": "Function description",
                "parameters": { /* schema */ }
            }
        }
    ],
    tool_choice="auto",                     # Optional: Tool choice strategy
    temperature=0.7,                        # Optional: Response randomness
    max_tokens=1000,                        # Optional: Maximum response length
    stream=False                            # Optional: Streaming mode
)
```

### Parameter Descriptions

| Parameter     | Type          | Required | Description                       |
| ------------- | ------------- | -------- | --------------------------------- |
| `model`       | string        | Yes      | The model to use for completion   |
| `messages`    | array         | Yes      | List of conversation messages     |
| `tools`       | array         | No       | List of available tools/functions |
| `tool_choice` | string/object | No       | How the model should choose tools |
| `temperature` | number        | No       | Sampling temperature (0-2)        |
| `max_tokens`  | integer       | No       | Maximum tokens in response        |
| `stream`      | boolean       | No       | Whether to stream the response    |

## Response Structure

### Tool Call Response

When the model decides to call a function, the response includes:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "id": "call_abc123",
            "type": "function",
            "function": {
              "name": "get_weather",
              "arguments": "{\"location\": \"New York\"}"
            }
          }
        ]
      }
    }
  ]
}
```

### Response Fields

| Field                | Type   | Description                          |
| -------------------- | ------ | ------------------------------------ |
| `id`                 | string | Unique identifier for the tool call  |
| `type`               | string | Always "function" for function calls |
| `function.name`      | string | Name of the function to call         |
| `function.arguments` | string | JSON string of function arguments    |

## Handling Tool Call Responses

### Complete Workflow

```python
# Initial request
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "What's the weather in Paris?"}],
    tools=tools,
    tool_choice="auto"
)

messages = [{"role": "user", "content": "What's the weather in Paris?"}]

# Handle tool calls
if response.choices[0].message.tool_calls:
    # Add assistant message with tool calls
    messages.append(response.choices[0].message)

    # Execute each tool call
    for tool_call in response.choices[0].message.tool_calls:
        function_result = execute_function_call(
            tool_call.function.name,
            json.loads(tool_call.function.arguments)
        )

        # Add tool response
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(function_result)
        })

    # Get final response
    final_response = client.chat.completions.create(
        model="argo:gpt-4o",
        messages=messages
    )
```

## Best Practices

### Schema Design

1. **Be explicit about types**: Always specify parameter types clearly
2. **Use enums for limited options**: Restrict values using `enum` arrays
3. **Set constraints**: Use `minimum`, `maximum`, `minLength`, `maxLength`
4. **Provide clear descriptions**: Help the model understand parameter usage

### Error Handling

```python
def safe_tool_execution(tool_call):
    try:
        function_name = tool_call.function.name
        arguments = json.loads(tool_call.function.arguments)

        # Validate arguments
        if not validate_arguments(function_name, arguments):
            return {"error": "Invalid arguments"}

        # Execute function
        result = execute_function(function_name, arguments)
        return {"result": result, "success": True}

    except json.JSONDecodeError:
        return {"error": "Invalid JSON in arguments"}
    except Exception as e:
        return {"error": f"Execution failed: {str(e)}"}
```

### Security Considerations

1. **Validate all inputs**: Never trust function arguments from the LLM
2. **Use parameter constraints**: Limit ranges and allowed values
3. **Implement timeouts**: Prevent long-running function calls
4. **Sanitize outputs**: Clean function results before returning to LLM

## Streaming Behavior

When using function calling with streaming:

- **Pseudo stream is automatically enforced** regardless of your configuration
- This ensures reliable function call processing with the current implementation
- The streaming mode switch is transparent and maintains a consistent user experience

## Common Issues

### Tool calls not triggered

- Check function descriptions are clear and relevant
- Verify `tool_choice` setting
- Ensure model supports function calling

### Invalid function arguments

- Validate parameter schema syntax
- Check required parameters are specified
- Review parameter descriptions for clarity

### Function execution errors

- Implement proper error handling in functions
- Validate input arguments before processing
- Check function implementation for bugs

## Examples

### Weather Function with Validation

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather information for a specific location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or 'City, Country' format (e.g., 'Tokyo' or 'Paris, France')",
                        "minLength": 2,
                        "maxLength": 100
                    },
                    "units": {
                        "type": "string",
                        "enum": ["metric", "imperial", "kelvin"],
                        "description": "Temperature units - 'metric' for Celsius, 'imperial' for Fahrenheit, 'kelvin' for Kelvin",
                        "default": "metric"
                    },
                    "include_forecast": {
                        "type": "boolean",
                        "description": "Whether to include 3-day forecast data",
                        "default": false
                    }
                },
                "required": ["location"]
            }
        }
    }
]
```

This comprehensive parameter guide should help you understand and implement tool calls effectively with the OpenAI-compatible API.
