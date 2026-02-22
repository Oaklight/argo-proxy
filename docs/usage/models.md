# Models

Argo Proxy dynamically fetches the model list from the upstream ARGO API at startup. Rather than maintaining a static list of models (which quickly becomes outdated), this page explains the **naming scheme** used by Argo Proxy and how to **query available models** at runtime.

## Querying Available Models

### List Models

Send a `GET` request to the `/v1/models` endpoint to retrieve all currently available models:

```bash
curl http://localhost:44497/v1/models
```

The response follows the OpenAI-compatible format:

```json
{
    "object": "list",
    "data": [
        {
            "id": "argo:gpt-4o",
            "internal_name": "gpt4o",
            "object": "model",
            "created": 1700000000,
            "owned_by": "openai"
        },
        ...
    ]
}
```

Each entry contains:

- **`id`** — the Argo Proxy alias you use in API requests (e.g. `argo:gpt-4o`)
- **`internal_name`** — the upstream ARGO internal model identifier (e.g. `gpt4o`)
- **`owned_by`** — the model provider family (`openai`, `anthropic`, `google`, or `unknown`)

### Refresh Model List

If new models are added upstream, you can reload the model list without restarting:

```bash
curl -X POST http://localhost:44497/refresh
```

See [Endpoints — `/refresh`](endpoints.md#refresh) for details on the response format.

## Model Naming Scheme

All Argo Proxy model names use the `argo:` prefix followed by a human-readable, OpenAI-style name. The naming rules vary by model family.

### OpenAI Models

Standard GPT models use the format `argo:gpt-{version}`:

| Pattern | Example |
| --- | --- |
| `argo:gpt-{version}` | `argo:gpt-4`, `argo:gpt-4-turbo`, `argo:gpt-4o` |
| `argo:gpt-{version}-{variant}` | `argo:gpt-3.5-turbo-16k`, `argo:gpt-4.1-mini` |

OpenAI reasoning models (o-series) have **two equivalent aliases**:

| Pattern | Example |
| --- | --- |
| `argo:gpt-{o-model}` | `argo:gpt-o3-mini` |
| `argo:{o-model}` | `argo:o3-mini` |

Both forms resolve to the same upstream model. Use whichever you prefer.

### Anthropic Claude Models

Claude models have **two equivalent aliases** with different ordering:

| Pattern | Example |
| --- | --- |
| `argo:claude-{codename}-{generation}` | `argo:claude-sonnet-4`, `argo:claude-opus-4` |
| `argo:claude-{generation}-{codename}` | `argo:claude-4-sonnet`, `argo:claude-4-opus` |

For versioned models, a version suffix is appended:

| Pattern | Example |
| --- | --- |
| `argo:claude-{codename}-{generation}-{version}` | `argo:claude-sonnet-3.5-v2` |
| `argo:claude-{generation}-{codename}-{version}` | `argo:claude-3.5-sonnet-v2` |

### Google Gemini Models

Gemini models use the format `argo:gemini-{version}-{variant}`:

| Pattern | Example |
| --- | --- |
| `argo:gemini-{version}-{variant}` | `argo:gemini-2.5-pro`, `argo:gemini-2.5-flash` |

### Embedding Models

Embedding models follow OpenAI's naming convention:

| Pattern | Example |
| --- | --- |
| `argo:text-embedding-{name}` | `argo:text-embedding-ada-002`, `argo:text-embedding-3-small` |

## Flexible Model Name Resolution

Argo Proxy is lenient when resolving model names. The following variations are all accepted:

- **Prefix**: `argo:gpt-4o` or just `gpt-4o` (the `argo:` prefix is optional)
- **Separator**: `argo:gpt-4o` or `argo/gpt-4o` (slash works as well)
- **Case**: `argo:GPT-4o` or `argo:gpt-4o` (case-insensitive)

If a model name cannot be resolved, Argo Proxy falls back to `gpt4o` for chat models and `v3small` for embedding models.

## Why No Static Model List?

The upstream ARGO API evolves over time — models are added, retired, or renamed. Argo Proxy fetches the model list dynamically at startup and generates aliases automatically based on the naming rules above. This means:

1. **New models are available immediately** after an upstream update (just call `/refresh` or restart).
2. **Documentation stays accurate** without manual updates.
3. **You always have the ground truth** via the `/v1/models` endpoint.