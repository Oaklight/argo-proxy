# Native OpenAI Endpoint Passthrough

## Overview

The Native OpenAI endpoint passthrough mode allows you to directly forward requests to a native OpenAI-compatible endpoint without any transformation or processing. This is useful when:

- You want to use the native OpenAI endpoint without Argo Proxy's transformation layer
- You need complete passthrough of requests and responses
- You want to test native endpoint behavior

This is a feature work in progress, so you may encounter issues or limitations.

## Configuration

### Method 1: Using CLI Flag

Start the proxy with the `--native-openai` flag:

```bash
argo-proxy --native-openai
```

### Method 2: Configuration File

Add the following to your `config.yaml` file:

```yaml
# Enable native OpenAI endpoint passthrough mode (default: false)
use_native_openai: true

# Native OpenAI endpoint base URL (optional, defaults shown below)
# Development endpoint (default):
native_openai_base_url: "https://apps-dev.inside.anl.gov/argoapi/v1/"
# Production endpoint:
# native_openai_base_url: "https://apps.inside.anl.gov/argoapi/v1/"
```

### Method 3: Environment Variable

```bash
export USE_NATIVE_OPENAI=true
argo-proxy
```

## Endpoint URLs

The default base URL for the native OpenAI endpoint is:

```
https://apps-dev.inside.anl.gov/argoapi/v1/
```

In the future, if Argo team provides other native openai endpoints (production version, for example), you may update this URL setting.

## Supported Endpoints

When native OpenAI mode is enabled, the following endpoints are available:

**Available Endpoints:**

- `/v1/chat/completions` → `{base_url}/chat/completions` ✓

**Unavailable Endpoints:**

- `/v1/completions` → `{base_url}/completions` ✗ (`404 Not Found` from upstream)
- `/v1/embeddings` → `{base_url}/embeddings` ✗ (`404 Not Found` from upstream)

## Behavior

### Passthrough Mode

In native OpenAI mode:

1. **No Transformation**: Requests and responses are passed through directly without any format conversion
2. **Tool Call Processing**: Tool calls are automatically converted to the appropriate format for the target model
3. **Image Processing**: Image URLs are automatically downloaded and converted to base64
4. **Preserve Original Response**: Upstream API responses are returned as-is to the client

### Differences from Standard Mode

| Feature                      | Standard Mode | Native OpenAI Mode               |
| ---------------------------- | ------------- | -------------------------------- |
| Request Transformation       | ✓             | N/A                              |
| Response Transformation      | ✓             | N/A                              |
| Tool Call Processing         | ✓             | See Tool Call Processing section |
| Image Processing             | ✓             | ✓                                |
| Model Name Mapping           | ✓             | ✓                                |
| Message Format Normalization | ✓             | N/A                              |

## Model Name Mapping

Even in native OpenAI mode, the proxy supports model name mapping. This means you can use Argo model aliases like `argo:gpt-4o`, `argo:claude-4-sonnet`, etc., and they will be automatically resolved to their actual model IDs before being sent to the upstream endpoint.

Example:

```python
# You can use Argo aliases
response = client.chat.completions.create(
    model="argo:gpt-4o",  # Will be resolved to actual model ID
    messages=[{"role": "user", "content": "Hello!"}]
)

# Or use the actual model IDs directly
response = client.chat.completions.create(
    model="gpt4o",  # Direct model ID
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Tool Call Processing

⚠️ **Limited Compatibility**: Tool calling in native OpenAI mode is currently only supported for OpenAI models. As of December 2025:

**Working Models:**

- OpenAI models (argo:gpt-4o, argo:gpt-4o-mini, etc.) ✓

**Non-Working Models:**

- Claude models (argo:claude-4-sonnet, etc.) ✗ (400 Bad Request)
- Gemini models (argo:gemini-2.5-flash, etc.) ✗ (500 Internal Server Error)

**Known Issues:**

- Claude models: `tool_choice: Input should be a valid dictionary or object to extract fields from`
- Gemini models: `'name' KeyError`

**Workaround**: For non-OpenAI models, use standard mode instead of native OpenAI mode for tool calling functionality.

### Streaming Tool Call Behavior ⚠️

**Important**: The streaming tool call behavior in native OpenAI mode differs significantly from standard mode:

#### Standard Mode (Non-Native)

- **Pseudo Streaming**: Upstream API doesn't support tool calls in streaming mode
- **Fake Implementation**: Tool calls are simulated using pseudo stream at non-streaming upstream endpoint
- **Complete Objects**: Returned tool call objects are complete as single pieces
- **No Assembly Required**: Tool call data arrives as complete, ready-to-use objects

#### Native OpenAI Mode

- **Real Streaming**: Upstream API supports actual OpenAI streaming tool calls
- **Piecewise Delivery**: Tool call blocks are returned in pieces/chunks across multiple streaming events
- **Manual Assembly Required**: Programmers must collect and assemble tool call pieces themselves
- **Fragmented Data**: Each streaming chunk may contain partial tool call information

**Example of streaming tool call data in native mode:**

```json
// Stream chunk 1: initial tool call with name and ID
{
  "choices": [{
    "delta": {
      "tool_calls": [{
        "index": 0,
        "id": "call_H8p0Tts1AmjZLFwxHxEgfdev",
        "function": {
          "arguments": "",
          "name": "add"
        },
        "type": "function"
      }]
    }
  }]
}

// Stream chunks 2-9: arguments field built character by character
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"{\""}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"a"}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"\":"}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"12"}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"\","}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"b"}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"\":"}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"30"}}]}}]}
{"choices":[{"delta":{"tool_calls":[{"function":{"arguments":"}"}}]}}]}

// Final chunk: tool_calls completed
{"choices":[{"delta":{"tool_calls":null},"finish_reason":"tool_calls"}]}
```

**Implementation Note**: When using native OpenAI mode with streaming tool calls, you need to:

1. Collect all `tool_calls` pieces across streaming chunks
2. Assemble the complete tool call object by combining fragments
3. Handle the incremental nature of tool call data delivery

For simpler usage, consider using non-streaming mode or standard mode if you need complete tool call objects without manual assembly.

## Notes

1. **Model Name Mapping**: Argo model aliases (e.g., `argo:gpt-4o`) are supported and will be resolved automatically (same as standard mode)
2. **Image Processing**: HTTP/HTTPS image URLs are automatically downloaded and converted to base64, with optional payload size optimization (same as standard mode)

## Troubleshooting

### Connection Errors

If you encounter connection errors:

1. Check if you're on the ANL network, or connected via VPN, or tunneled through SSH.
2. Verify the `native_openai_base_url` configuration is correct
3. Confirm the endpoint URL is accessible from an ANL computer.

### Format Errors

If you encounter format errors:

1. Ensure your request conforms to OpenAI API specifications
2. Check model names are correct (argo-proxy aliases supported)
3. Verify request parameters are valid

### Endpoint Availability Issues

If you encounter 404 errors for certain endpoints:

- **Legacy Completions** (`/v1/completions`): Currently unavailable in native OpenAI mode
- **Embeddings** (`/v1/embeddings`): Currently unavailable in native OpenAI mode
- **Workaround**: Use `/v1/chat/completions` for text generation or switch to standard mode

### Tool Calling Errors

If you encounter tool calling errors:

1. **Claude models**: If you get `tool_choice: Input should be a valid dictionary or object to extract fields from`, switch to standard mode
2. **Gemini models**: If you get `'name' KeyError`, switch to standard mode
3. **OpenAI models**: Tool calling should work correctly in native OpenAI mode

### Common Error Messages

| Error Message                                               | Model  | Solution                              |
| ----------------------------------------------------------- | ------ | ------------------------------------- |
| `404 Client Error: Not Found`                               | All    | Endpoint not available in native mode |
| `tool_choice: Input should be a valid dictionary or object` | Claude | Use standard mode instead             |
| `'name' KeyError`                                           | Gemini | Use standard mode instead             |
| `500 Internal Server Error`                                 | Gemini | Use standard mode instead             |

## Testing

You can test the implementation yourself using the OpenAI Python SDK or any HTTP client that supports the OpenAI API format.

Example test with curl:

```bash
# Start proxy with native OpenAI mode
argo-proxy --native-openai

# Test chat completion
curl http://localhost:44497/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Related Documentation

- [Configuration Guide](basics/configuration.md)
- [CLI Usage](basics/cli.md)
- [Endpoints Documentation](endpoints.md)
