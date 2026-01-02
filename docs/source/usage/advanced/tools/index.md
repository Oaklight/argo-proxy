# Tool Calls (Function Calling)

```{toctree}
:maxdepth: 2
:caption: Tool Calls Documentation

getting-started
openai-parameters
toolregistry
```

Tool calls, also known as function calling, enable AI models to request the execution of external functions. This powerful feature allows you to extend AI capabilities by integrating with APIs, databases, file systems, and other external services.

## Overview

The tool calling feature has been available since version v2.7.5.alpha1 and provides:

- **Function Discovery**: AI models can analyze available functions and determine when to use them
- **Parameter Generation**: Models generate appropriate arguments for function calls
- **Result Integration**: Function results are incorporated into natural language responses
- **Flexible Integration**: Works with various function management approaches

## Quick Start

If you're new to tool calls, start with our [Getting Started Guide](getting-started.md) which covers:

- What tool calling really is (and common misconceptions)
- Basic implementation patterns
- Simple working examples
- Key concepts and workflow

## Documentation Structure

### Core Guides

- **[Getting Started](getting-started.md)** - Introduction and basic concepts
- **[OpenAI API Parameters](openai-parameters.md)** - Detailed parameter reference
- **[Advanced Usage](advanced-usage.md)** - Best practices and complex scenarios
- **[ToolRegistry Integration](toolregistry.md)** - Using the ToolRegistry library

### Key Topics Covered

#### Fundamentals

- Understanding the tool calling workflow
- Function schema design
- Parameter validation and error handling
- Security considerations

#### Implementation Approaches

- Manual schema creation
- ToolRegistry integration for simplified management
- Async function execution
- Rate limiting and caching

#### Advanced Patterns

- Schema-only tools for guided reasoning
- Complex parameter validation
- Performance optimization
- Real-world integration examples

## Feature Status

- **Available on**: Both streaming and non-streaming chat completion endpoints
- **Supported endpoints**: `/v1/chat/completions`
- **Not supported**: Argo passthrough (`/v1/chat`) and legacy completion endpoints (`/v1/completions`)
- **Status**: Production-ready feature with native function calling support

## Native Function Calling Support

Starting from recent versions, Argo Proxy supports **native function calling** for supported models:

### Supported Models for Native Function Calling

- **OpenAI models**: Full native function calling support
- **Anthropic models**: Full native function calling support
- **Gemini models**: Full native function calling support (added in v2.8.0)

### Key Features

- **OpenAI Format Compatibility**: All input and output remains in OpenAI format regardless of the underlying model
- **Automatic Conversion**: Provider-specific function call formats are automatically converted to OpenAI format
- **Seamless Integration**: No changes required to existing OpenAI-compatible code
- **Enhanced Performance**: Native function calling provides better reliability and performance compared to prompting-based approaches

### Implementation Notes

- **Chat Completions Only**: Native function calling is only available on the `/v1/chat/completions` endpoint
- **Argo Passthrough**: Native function calling for Argo passthrough mode (`/v1/chat`) is not implemented due to limited development time
- **Backward Compatibility**: Legacy prompting-based function calling remains available via the `--tool-prompting` CLI flag

## Supported Models

All chat models support tool calls, with varying levels of native function calling support as detailed above.

## Streaming Behavior

When using function calling with streaming:

- **Streamlined Tool Integration**: Use tools directly within streaming responses.
- **Automatic Fallback**: Switches to pseudo-streaming automatically when tools are active.
- **Zero-Config**: The mode change is transparent and requires no developer intervention.

## Choose Your Path

### New to Tool Calls?

Start with [Getting Started](getting-started.md) to understand the fundamentals.

### Need Parameter Details?

Check [OpenAI API Parameters](openai-parameters.md) for comprehensive parameter documentation.

### Want Simplified Management?

Explore [ToolRegistry Integration](toolregistry.md) for automatic schema generation and execution.

### Building Complex Systems?

Review [Advanced Usage](advanced-usage.md) for best practices, security, and performance optimization.

## Common Use Cases

- **API Integration**: Connect to weather services, databases, or external APIs
- **File Operations**: Read, write, and manipulate files safely
- **Data Processing**: Perform calculations, analysis, or transformations
- **System Operations**: Execute system commands or interact with services
- **Custom Business Logic**: Implement domain-specific functionality

## Important Notes

1. **LLMs don't execute functions** - They only request function calls based on descriptions
2. **You control execution** - Your application is responsible for actually running functions
3. **Validation is critical** - Always validate and sanitize function inputs
4. **Error handling matters** - Implement robust error handling for reliable operation

## Getting Help

If you encounter issues:

1. Check the troubleshooting sections in each guide
2. Validate your function schemas
3. Test functions independently before integration
4. Enable verbose logging for debugging

Ready to get started? Begin with our [Getting Started Guide](getting-started.md)!
