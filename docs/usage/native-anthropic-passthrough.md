# Native Anthropic Endpoint Passthrough

!!! note "v3 Update"
    In argo-proxy v3, the Anthropic `/v1/messages` endpoint is **always available** in universal mode. You no longer need the `--native-anthropic` flag or `use_native_anthropic: true` config. This page is kept for reference.

    See [Endpoints](endpoints.md) for the v3 endpoint documentation and [CLI Tools Guide](cli-tools.md) for configuring Claude Code and other Anthropic clients.

## Overview

In v3 universal mode, the `/v1/messages` endpoint accepts Anthropic Messages API requests natively. Claude models are routed to the native Anthropic upstream for best compatibility (avoiding tool call issues on the OpenAI-compatible gateway). Non-Claude models are translated to OpenAI Chat format via llm-rosetta.

## Configuration

The native Anthropic base URL is derived from `argo_base_url` automatically:

```yaml
# In config.yaml
argo_base_url: "https://apps-dev.inside.anl.gov/argoapi"
# native_anthropic_base_url defaults to: https://apps-dev.inside.anl.gov/argoapi
```

To override:

```yaml
native_anthropic_base_url: "https://apps-dev.inside.anl.gov/argoapi"
```

## Usage with Anthropic SDK

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:44497",
    api_key="your-anl-username",
)

message = client.messages.create(
    model="argo:claude-4-sonnet",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ],
)
print(message.content[0].text)
```

### Streaming

```python
with client.messages.stream(
    model="argo:claude-4-sonnet",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Count from 1 to 10."}
    ],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

## Usage with Claude Code

See the [CLI Tools Guide](cli-tools.md#claude-code) for detailed Claude Code configuration.

## Related Documentation

- [Endpoints](endpoints.md)
- [CLI Tools Guide](cli-tools.md)
- [Configuration](basics/configuration.md)
