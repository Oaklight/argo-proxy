# Native OpenAI Endpoint Passthrough

## Overview

The Native OpenAI endpoint passthrough mode allows you to directly forward requests to a native OpenAI-compatible endpoint without any transformation or processing. This is useful when:

- You want to use the native OpenAI endpoint without Argo's transformation layer
- You need complete passthrough of requests and responses
- You want to test native endpoint behavior

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

You can customize this URL via the `native_openai_base_url` parameter in your configuration file to point to either:

- **Development endpoint**: `https://apps-dev.inside.anl.gov/argoapi/v1/`
- **Production endpoint**: `https://apps.inside.anl.gov/argoapi/v1/`

## Supported Endpoints

When native OpenAI mode is enabled, the following endpoints are directly passed through to upstream:

- `/v1/chat/completions` → `{base_url}/chat/completions`
- `/v1/completions` → `{base_url}/completions`
- `/v1/embeddings` → `{base_url}/embeddings`

## Usage Examples

### Python (OpenAI SDK)

```python
from openai import OpenAI

# Configure client to use local proxy
client = OpenAI(
    api_key="your-api-key",
    base_url="http://localhost:44497/v1",
)

# Chat completion
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
)

print(response.choices[0].message.content)
```

### Streaming Response

```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "Count from 1 to 5"}
    ],
    stream=True,
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Embeddings

```python
response = client.embeddings.create(
    model="text-embedding-3-small",
    input="Hello, world!",
)

print(f"Embedding dimension: {len(response.data[0].embedding)}")
```

## Behavior

### Passthrough Mode

In native OpenAI mode:

1. **No Transformation**: Requests and responses are passed through directly without any format conversion
2. **No Tool Processing**: Tool calls or function calls are not processed
3. **No Image Processing**: Image URLs are not processed or optimized
4. **Preserve Original Response**: Upstream API responses are returned as-is to the client

### Differences from Standard Mode

| Feature                      | Standard Mode | Native OpenAI Mode |
| ---------------------------- | ------------- | ------------------ |
| Request Transformation       | ✓             | N/A                |
| Response Transformation      | ✓             | N/A                |
| Tool Call Processing         | ✓             | N/A                |
| Image Processing             | ✓             | ✓                  |
| Model Name Mapping           | ✓             | ✓                  |
| Message Format Normalization | ✓             | N/A                |

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

## Notes

1. **Network Access**: Ensure your environment can access the native OpenAI endpoint URL
2. **Authentication**: If the upstream endpoint requires authentication, include appropriate authentication in request headers
3. **Compatibility**: In native mode, all requests must conform to the upstream API's format requirements
4. **Username Passthrough**: If `--username-passthrough` is enabled, user information will still be added to requests
5. **Model Name Mapping**: Argo model aliases (e.g., `argo:gpt-4o`) are supported and will be resolved automatically
6. **Image Processing**: HTTP/HTTPS image URLs are automatically downloaded and converted to base64, with optional payload size optimization

## Troubleshooting

### Connection Errors

If you encounter connection errors:

1. Check if you're on the ANL network or connected via VPN
2. Verify the `native_openai_base_url` configuration is correct
3. Confirm the endpoint URL is accessible

### Authentication Errors

If you encounter authentication errors:

1. Ensure valid API key is included in request headers
2. Check your credentials have access to the native endpoint

### Format Errors

If you encounter format errors:

1. Ensure your request conforms to OpenAI API specifications
2. Check model names are correct
3. Verify request parameters are valid

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
