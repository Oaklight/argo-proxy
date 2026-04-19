# API Endpoints

Argo Proxy provides a universal API gateway that serves all major LLM API formats. In v3 universal mode (default), requests are automatically routed to the optimal upstream endpoint based on the model family.

Here we assume the service is running on `localhost:44497`. Replace with your actual service address.

## Universal Endpoints (v3)

These endpoints are always available and support all models through automatic format translation via [llm-rosetta](https://github.com/Oaklight/llm-rosetta).

### `/v1/chat/completions` — OpenAI Chat

The primary endpoint for OpenAI Chat Completions API.

```bash
POST http://localhost:44497/v1/chat/completions
```

Supports all models (GPT, Claude, Gemini). Requests for Claude models are automatically translated to native Anthropic format upstream, while GPT and Gemini models use the native OpenAI-compatible upstream.

### `/v1/responses` — OpenAI Responses

OpenAI's Responses API endpoint.

```bash
POST http://localhost:44497/v1/responses
```

Supports all models. Cross-format translation is handled automatically.

### `/v1/messages` — Anthropic Messages

Native Anthropic Messages API endpoint. Use this with the Anthropic SDK, Claude Code, or any Anthropic-compatible client.

```bash
POST http://localhost:44497/v1/messages
```

Supports all models. Requests for non-Claude models are automatically translated to OpenAI Chat format upstream.

### `/v1beta/models/{model}:generateContent` — Google GenAI

Google GenAI (Gemini) content generation endpoint.

```bash
POST http://localhost:44497/v1beta/models/gemini-2.5-flash:generateContent
```

### `/v1beta/models/{model}:streamGenerateContent` — Google GenAI (Streaming)

Google GenAI streaming endpoint.

```bash
POST http://localhost:44497/v1beta/models/gemini-2.5-flash:streamGenerateContent
```

### `/v1/embeddings` — Embeddings

OpenAI-compatible embedding API. Passed through to the native OpenAI endpoint.

```bash
POST http://localhost:44497/v1/embeddings
```

### `/v1/models` — Model List

Lists available models in OpenAI-compatible format.

```bash
GET http://localhost:44497/v1/models
```

**Response**: Returns a list of available chat and embedding models with their aliases.

## Routing Logic

In universal mode, argo-proxy routes requests to the optimal upstream based on the model family:

| Model Family | Upstream | Reason |
|---|---|---|
| OpenAI (GPT) | OpenAI Chat endpoint | Natural fit |
| Google (Gemini) | OpenAI Chat endpoint | Only option on ARGO |
| Anthropic (Claude) | Anthropic native endpoint | Avoids tool call issues on OpenAI-compat |
| Unknown | OpenAI Chat endpoint | Best-effort default |

When the client format matches the upstream format (e.g., OpenAI client + GPT model), requests pass through directly without conversion. When formats differ (e.g., Anthropic client + GPT model), llm-rosetta handles the translation.

## Upstream Authentication

The ARGO backend identifies users through different fields depending on the upstream endpoint format:

| Upstream Format | Primary Auth Field | Fallback | Location |
|---|---|---|---|
| OpenAI (Chat, Responses, Embeddings) | `user` | `Authorization: Bearer` | Body / Header |
| Anthropic (Messages) | `x-api-key` | `Authorization: Bearer` | Header |
| Legacy ARGO (Chat, StreamChat) | `user` | — | Body |

Argo-proxy automatically populates these fields using the `user` value from your configuration. When `--username-passthrough` is enabled, the API key provided by the downstream client is used instead.

## Legacy Endpoints

These endpoints are only available when legacy mode is enabled (`--legacy-argo` or `use_legacy_argo: true`).

### `/v1/chat`

Proxies requests directly to the legacy ARGO Chat API without format conversion.

```bash
POST http://localhost:44497/v1/chat
```

### `/v1/embed`

Proxies requests directly to the legacy ARGO Embedding API.

```bash
POST http://localhost:44497/v1/embed
```

### `/v1/completions`

Legacy Completions API (text completion). Only available in legacy mode.

```bash
POST http://localhost:44497/v1/completions
```

## Utility Endpoints

### `/health`

Health check endpoint for monitoring and load balancing.

```bash
GET http://localhost:44497/health
```

**Response**: Returns `200 OK` with `{"status": "healthy"}` if the server is running.

### `/version`

Returns version information, update availability, and dependency status.

```bash
GET http://localhost:44497/version
```

**Response**:

```json
{
    "version": "3.0.0",
    "latest_stable": "3.0.0",
    "latest_pre": null,
    "up_to_date": true,
    "message": "You're using the latest version",
    "update_commands": null,
    "dependencies": {
        "llm-rosetta": {
            "installed": "0.5.1",
            "latest_stable": "0.5.1",
            "latest_pre": null,
            "up_to_date": true,
            "update_command": "pip install --upgrade llm-rosetta"
        }
    },
    "pypi": "https://pypi.org/project/argo-proxy/",
    "changelog": "https://argo-proxy.readthedocs.io/en/latest/changelog/"
}
```

The `dependencies` field reports the update status of critical dependencies (currently llm-rosetta). It is `null` when no critical dependencies are installed. The `update_commands` field contains CLI and pip upgrade commands when an argo-proxy update is available.

### `/refresh`

Reloads the model list from the upstream ARGO API without restarting.

```bash
POST http://localhost:44497/refresh
```

**Response**:

```json
{
    "status": "ok",
    "message": "Model list refreshed successfully",
    "previous": {
        "unique_models": 20,
        "total_aliases": 45
    },
    "current": {
        "unique_models": 22,
        "total_aliases": 50,
        "chat_models": 19,
        "embed_models": 3
    }
}
```
