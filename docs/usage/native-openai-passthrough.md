# Native OpenAI Endpoint Passthrough

!!! note "v3 Update"
    In argo-proxy v3, native OpenAI endpoints are used **by default** in universal mode. You no longer need the `--native-openai` flag or `use_native_openai: true` config. This page is kept for reference.

    See [Endpoints](endpoints.md) for the v3 endpoint documentation and [CLI Tools Guide](cli-tools.md) for configuring client tools.

## Overview

In v3 universal mode, all requests to `/v1/chat/completions`, `/v1/responses`, and `/v1/embeddings` are routed to the native OpenAI-compatible upstream endpoint automatically. The native endpoint provides:

- Full streaming support with proper tool call handling
- Support for all models (GPT, Claude, Gemini) via ARGO's OpenAI-compatible gateway
- Standard OpenAI response format

## Configuration

The native OpenAI base URL is derived from `argo_base_url` automatically:

```yaml
# In config.yaml
argo_base_url: "https://apps-dev.inside.anl.gov/argoapi"
# native_openai_base_url defaults to: https://apps-dev.inside.anl.gov/argoapi/v1
```

To override:

```yaml
native_openai_base_url: "https://apps-dev.inside.anl.gov/argoapi/v1"
```

## Model Name Mapping

Argo model aliases (e.g., `argo:gpt-4o`, `argo:claude-4-sonnet`) are resolved to their upstream model IDs before forwarding.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:44497/v1",
    api_key="your-anl-username",
)

response = client.chat.completions.create(
    model="argo:gpt-4o",  # Resolved to actual model ID
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Related Documentation

- [Endpoints](endpoints.md)
- [CLI Tools Guide](cli-tools.md)
- [Configuration](basics/configuration.md)
