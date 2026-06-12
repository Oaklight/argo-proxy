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
            "id": "argo:gpt-5",
            "internal_name": "gpt5",
            "object": "model",
            "created": 1700000000,
            "owned_by": "openai"
        },
        ...
    ]
}
```

Each entry contains:

- **`id`** — the Argo Proxy alias you use in API requests (e.g. `argo:gpt-5`)
- **`internal_name`** — the upstream ARGO internal model identifier (e.g. `gpt5`)
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
| `argo:gpt-{version}` | `argo:gpt-4o`, `argo:gpt-5` |
| `argo:gpt-{version}-{variant}` | `argo:gpt-4.1-mini`, `argo:gpt-5-nano` |

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
| `argo:claude-{codename}-{generation}` | `argo:claude-sonnet-4.5`, `argo:claude-opus-4.7` |
| `argo:claude-{generation}-{codename}` | `argo:claude-4.5-sonnet`, `argo:claude-4.7-opus` |

Both forms resolve to the same upstream model. Use whichever you prefer.

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

- **Prefix**: `argo:gpt-5` or just `gpt-5` (the `argo:` prefix is optional)
- **Separator**: `argo:gpt-5` or `argo/gpt-5` (slash works as well)
- **Case**: `argo:GPT-5` or `argo:gpt-5` (case-insensitive)

If a model name cannot be resolved, Argo Proxy falls back to `gpt5nano` for chat models and `v3small` for embedding models. A warning is logged when this happens.

## Why No Static Model List?

The upstream ARGO API evolves over time — models are added, retired, or renamed. Argo Proxy fetches the model list dynamically at startup and generates aliases automatically based on the naming rules above. This means:

1. **New models are available immediately** after an upstream update (just call `/refresh` or restart).
2. **Documentation stays accurate** without manual updates.
3. **You always have the ground truth** via the `/v1/models` endpoint.