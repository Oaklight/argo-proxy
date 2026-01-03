# ToolRegistry Integration

[ToolRegistry](https://github.com/Oaklight/ToolRegistry) is a lightweight yet powerful Python tool management library designed to simplify tool call management. It seamlessly integrates with any OpenAI-compatible API, providing a more efficient tool call experience.

## Why Choose ToolRegistry?

### 1. Say Goodbye to Manually Writing Function Descriptions

No need to manually write complex JSON Schemas to describe your functions. ToolRegistry automatically generates accurate OpenAI-compatible tool descriptions from Python function type hints and docstrings.

```python
# Traditional method: manually writing JSON Schema
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "The city name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["location"]
        }
    }
}]

# ToolRegistry method: automatic generation
from toolregistry import ToolRegistry

registry = ToolRegistry()

@registry.register
def get_weather(location: str, unit: str = "celsius") -> dict:
    """Get current weather for a location"""
    # Implementation code
    pass

tools = registry.get_tools_json()  # Automatically generates complete JSON Schema
```

### 2. Integrate a Wide Range of External Tools

ToolRegistry supports integrating tools from various sources, making it easy to extend AI capabilities:

- **MCP (Model Context Protocol) tools**: Integrate tools provided by MCP servers, supporting all MCP-defined transport methods
- **OpenAPI specifications**: Automatically generate tools from OpenAPI/Swagger specifications
- **LangChain tools**: Reuse the existing LangChain tool ecosystem
- **Custom class-based tools**: Integrate tools implemented with classes

```python
# One line of code to integrate various tool sources
registry.register_from_mcp(...)
registry.register_from_openapi(...)
registry.register_from_langchain(...)
registry.register_from_class(...)
```

### 3. Prebuilt Convenient Tool Library

`toolregistry.hub` provides a rich set of prebuilt tools covering common use cases:

- File operation tools
- Network request tools
- Web search tools
- System information tools
- Mathematical calculation tools

```python
from toolregistry.hub import FileOps, WebSearchGoogle, Calculator

registry.register_from_class(FileOps)
registry.register_from_class(WebSearchGoogle())
registry.register_from_class(Calculator)
```

### 4. Automatic Parallel Execution

When the AI model requests multiple tool calls, ToolRegistry automatically executes these calls in parallel, significantly improving performance:

```python
# Automatically execute multiple tool calls in parallel
tool_responses = registry.execute_tool_calls(
    tool_calls,
    execution_mode="process"  # Default uses process pool for parallel execution
)
```

### 5. Mix and Orchestrate Different Types of Tools

Seamlessly mix and orchestrate tools from different sources in a single registry:

```python
registry = ToolRegistry()

# Register custom functions
@registry.register
def custom_calculation(x: float, y: float) -> float:
    """Custom mathematical operation"""
    return x ** y + y ** x

# Integrate external tools
client_config = HttpxClientConfig(base_url=f"http://localhost:{PORT}")
openapi_spec = load_openapi_spec("http://localhost:{PORT}")
registry.register_from_openapi(client_config=client_config, openapi_spec=openapi_spec)

registry.register_from_mcp("https://mcphub.url/mcp")

# All tools can now be managed and called uniformly
all_tools = registry.get_tools_json()
```

## Quick Start

### Installation

```bash
pip install toolregistry
```

For additional feature modules:

```bash
pip install toolregistry[mcp,openapi,langchain]
```

### Basic Usage Example

```python
import openai
from toolregistry import ToolRegistry

# Create a registry and register functions
registry = ToolRegistry()

@registry.register
def add_numbers(a: float, b: float) -> float:
    """Add two numbers together"""
    return a + b

# Integrate with Argo Proxy
client = openai.OpenAI(
    base_url="http://localhost:44497/v1",
    api_key="dummy"
)

# Get tools and send requests
tools = registry.get_tools_json()
response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "What's 15 + 27?"}],
    tools=tools
)

# Execute tool calls
if response.choices[0].message.tool_calls:
    tool_calls = response.choices[0].message.tool_calls
    tool_responses = registry.execute_tool_calls(tool_calls)

    # Reconstruct message history
    assistant_messages = registry.recover_tool_call_assistant_message(
        tool_calls, tool_responses
    )

    # Get the final response
    messages = [{"role": "user", "content": "What's 15 + 27?"}]
    messages.extend(assistant_messages)

    final_response = client.chat.completions.create(
        model="argo:gpt-4o",
        messages=messages
    )

    print(final_response.choices[0].message.content)
```

## Full Documentation

ToolRegistry provides rich features and advanced usage. For more details, visit the official documentation:

### 📚 [ToolRegistry Official Documentation](https://toolregistry.readthedocs.io/)

The official documentation includes:

- **[Getting Started Guide](https://toolregistry.readthedocs.io/en/stable/usage/)** - Detailed installation and basic usage tutorials
- **[API Reference](https://toolregistry.readthedocs.io/en/stable/api/)** - Complete API documentation
- **[Concurrency Modes](https://toolregistry.readthedocs.io/en/stable/usage/concurrency_modes.html)** - Detailed configuration for parallel execution
- **[Best Practices](https://toolregistry.readthedocs.io/en/stable/usage/best_practices.html)** - Recommendations for production use
- **[Integration Guide](https://toolregistry.readthedocs.io/en/stable/usage/integrations/mcp.html)** - Methods for integrating various tool sources
- **[Example Collection](https://toolregistry.readthedocs.io/en/stable/examples/)** - Complete examples for practical use cases

### 🔗 Related Links

- **GitHub Repository**: [https://github.com/Oaklight/ToolRegistry](https://github.com/Oaklight/ToolRegistry)
- **PyPI Package**: [https://pypi.org/project/toolregistry/](https://pypi.org/project/toolregistry/)
- **Issue Feedback**: [GitHub Issues](https://github.com/Oaklight/ToolRegistry/issues)

ToolRegistry makes tool calls simple and powerful!
