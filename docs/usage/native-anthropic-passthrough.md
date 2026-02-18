# Native Anthropic Endpoint Passthrough

## Overview

The Native Anthropic endpoint passthrough mode exposes a `/v1/messages` endpoint that is compatible with Anthropic's Messages API. This allows you to use the official Anthropic Python SDK, Claude Code, or any Anthropic-compatible client directly against Argo Proxy.

**Available from**: v2.8.4

## Configuration

### Method 1: Using CLI Flag

Start the proxy with the `--native-anthropic` flag:

```bash
argo-proxy --native-anthropic
```

### Method 2: Configuration File

Add the following to your `config.yaml` file:

```yaml
# Enable native Anthropic endpoint passthrough mode (default: false)
use_native_anthropic: true

# Native Anthropic endpoint base URL (optional, derived from argo_base_url by default)
# native_anthropic_base_url: "https://apps-dev.inside.anl.gov/argoapi/v1/messages"
```

### Method 3: Environment Variable

```bash
export USE_NATIVE_ANTHROPIC=true
argo-proxy
```

## Supported Endpoint

When native Anthropic mode is enabled, the following endpoint is available:

- `POST /v1/messages` → Anthropic Messages API

This endpoint supports both streaming and non-streaming requests.

## Usage with Anthropic Python SDK

The Anthropic Python SDK can be pointed at Argo Proxy by setting the `base_url` parameter:

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:44497",
    api_key="your-anl-username",  # Your ANL username
)

# Non-streaming
message = client.messages.create(
    model="argo:claude-4.5-sonnet",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ],
)
print(message.content[0].text)
```

### Streaming with the SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:44497",
    api_key="your-anl-username",
)

with client.messages.stream(
    model="argo:claude-4.5-sonnet",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Count from 1 to 10."}
    ],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
```

## Usage with Claude Code

[Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) can be configured to use Argo Proxy as its backend. You need to set three environment variables:

```bash
export ANTHROPIC_BASE_URL="http://localhost:44497"
export ANTHROPIC_API_KEY="your-anl-username"
export CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1

claude
```

Or as a one-liner:

```bash
ANTHROPIC_BASE_URL="http://localhost:44497" \
ANTHROPIC_API_KEY="your-anl-username" \
CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1 \
claude
```

You can also add these to your shell profile (e.g., `~/.bashrc` or `~/.zshrc`) for persistence:

```bash
# Argo Proxy + Claude Code
export ANTHROPIC_BASE_URL="http://localhost:44497"
export ANTHROPIC_API_KEY="$(echo 'your-anl-username')"
export CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1
```

!!! note
    - `CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1` is **required** — it tells Claude Code to skip Anthropic's default authentication flow and use the API key as-is.
    - Claude Code appends `/v1/messages` to the base URL automatically, so set `ANTHROPIC_BASE_URL` to the root of your Argo Proxy instance (e.g., `http://localhost:44497`), **not** `http://localhost:44497/v1/messages`.
    - Replace `your-anl-username` with your actual Argonne domain username.

## Usage with REST API (httpx / curl)

If you prefer not to use the SDK, you can send requests directly:

### Non-streaming with curl

```bash
curl -X POST http://localhost:44497/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-anl-username" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "argo:claude-4.5-sonnet",
    "max_tokens": 100,
    "messages": [
      {"role": "user", "content": "Hello, say hi back in one sentence."}
    ]
  }'
```

### Non-streaming with Python httpx

```python
import httpx

response = httpx.post(
    "http://localhost:44497/v1/messages",
    json={
        "model": "argo:claude-4.5-sonnet",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": "Hello, say hi back."}
        ],
    },
    headers={
        "Content-Type": "application/json",
        "x-api-key": "your-anl-username",
        "anthropic-version": "2023-06-01",
    },
    timeout=60.0,
)
print(response.json())
```

### Streaming with Python httpx

```python
import httpx

with httpx.stream(
    "POST",
    "http://localhost:44497/v1/messages",
    json={
        "model": "argo:claude-4.5-sonnet",
        "max_tokens": 100,
        "stream": True,
        "messages": [
            {"role": "user", "content": "Count from 1 to 5."}
        ],
    },
    headers={
        "Content-Type": "application/json",
        "x-api-key": "your-anl-username",
        "anthropic-version": "2023-06-01",
    },
    timeout=60.0,
) as response:
    for chunk in response.iter_bytes():
        if chunk:
            print(chunk.decode(errors="replace"), end="", flush=True)
print()
```

## Behavior

### Passthrough Mode

In native Anthropic mode:

1. **No Format Conversion**: Requests and responses use Anthropic's native format — no OpenAI conversion is applied
2. **Model Name Mapping**: Argo model aliases (e.g., `argo:claude-4.5-sonnet`) are resolved to their upstream model IDs automatically
3. **Image Processing**: Image URLs in messages are automatically downloaded and converted to base64
4. **Tool Call Processing**: Tools are handled according to the target model family
5. **User Identification**: Your ANL username is passed through as both the `user` field and `metadata.user_id`

### Differences from Standard Mode

| Feature                      | Standard Mode | Native Anthropic Mode |
| ---------------------------- | ------------- | --------------------- |
| Request Format               | OpenAI        | Anthropic             |
| Response Format              | OpenAI        | Anthropic             |
| Model Name Mapping           | ✓             | ✓                     |
| Image Processing             | ✓             | ✓                     |
| Tool Call Processing         | ✓             | ✓                     |
| Streaming                    | ✓             | ✓                     |

## Model Name Mapping

Even in native Anthropic mode, the proxy supports Argo model aliases. You can use names like `argo:claude-4.5-sonnet`, `argo:claude-4-opus`, etc., and they will be resolved to their upstream model IDs before forwarding.

Non-prefixed model names (e.g., `claude-sonnet-4-20250514`) are passed through as-is without resolution.

## Troubleshooting

### Connection Errors

If you encounter connection errors:

1. Ensure you are on the ANL network, connected via VPN, or tunneled through SSH
2. Verify the `native_anthropic_base_url` configuration is correct
3. Confirm the endpoint URL is accessible from your machine

### Authentication Errors

If you receive authentication errors:

1. Ensure `api_key` (SDK) or `x-api-key` (REST) is set to your ANL username
2. Include the `anthropic-version` header when using REST requests

### Claude Code Not Connecting

If Claude Code cannot connect:

1. Verify `ANTHROPIC_BASE_URL` is set to the proxy root (e.g., `http://localhost:44497`), **not** the full `/v1/messages` path
2. Verify `ANTHROPIC_API_KEY` is set to your ANL username
3. Verify `CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1` is set — without this, Claude Code will attempt Anthropic's default auth flow and fail
4. Ensure argo-proxy is running with `--native-anthropic`

## Related Documentation

- [Configuration Guide](basics/configuration.md)
- [CLI Usage](basics/cli.md)
- [Endpoints Documentation](endpoints.md)
- [Native OpenAI Passthrough](native-openai-passthrough.md)