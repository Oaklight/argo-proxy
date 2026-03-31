# AI Coding Tools

Argo Proxy v3 serves all major LLM API formats, which means it works out of the box with popular CLI tools and AI coding assistants. This guide shows how to configure each tool to use argo-proxy as its backend.

!!! note "Prerequisites"
    All examples assume argo-proxy is running at `http://localhost:44497`. Replace with your actual host and port.

    Your ANL username is used as the API key for all tools.

## Claude Code

[Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) (tested with v2.1.81) connects via the **Anthropic Messages API** (`/v1/messages`).

=== "Config File (Recommended)"

    ```bash
    claude config set -g apiKeyHelper "echo 'your-anl-username'"
    claude config set -g env.ANTHROPIC_BASE_URL "http://localhost:44497"
    claude config set -g env.CLAUDE_CODE_SKIP_ANTHROPIC_AUTH "1"
    ```

    This writes to `~/.claude/settings.json`:

    ```json
    {
        "apiKeyHelper": "echo 'your-anl-username'",
        "env": {
            "ANTHROPIC_BASE_URL": "http://localhost:44497",
            "CLAUDE_CODE_SKIP_ANTHROPIC_AUTH": "1"
        }
    }
    ```

=== "Environment Variables"

    ```bash
    export ANTHROPIC_BASE_URL="http://localhost:44497"
    export ANTHROPIC_API_KEY="your-anl-username"
    export CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1
    claude
    ```

!!! important
    - `CLAUDE_CODE_SKIP_ANTHROPIC_AUTH=1` is **required** — it skips Anthropic's default authentication flow
    - Set `ANTHROPIC_BASE_URL` to the proxy root (e.g., `http://localhost:44497`), **not** `http://localhost:44497/v1/messages` — Claude Code appends the path automatically

---

## Codex CLI (OpenAI)

[Codex CLI](https://github.com/openai/codex) (tested with v0.116.0) connects via the **OpenAI Responses API** (`/v1/responses`).

=== "Config File (Recommended)"

    Add a custom provider in `~/.codex/config.toml`:

    ```toml
    model = "argo:gpt-4o"
    model_provider = "argo"

    [model_providers.argo]
    name = "Argo Proxy"
    base_url = "http://localhost:44497/v1"
    env_key = "ARGO_API_KEY"
    wire_api = "responses"
    ```

    Then set the API key in your shell profile:

    ```bash
    export ARGO_API_KEY="your-anl-username"
    ```

=== "Environment Variables"

    ```bash
    export OPENAI_BASE_URL="http://localhost:44497/v1"
    export OPENAI_API_KEY="your-anl-username"
    codex
    ```

!!! note
    Codex CLI uses the **Responses API** wire format by default. When using the config file approach, `wire_api = "responses"` makes this explicit.

---

## Aider

[Aider](https://aider.chat/) supports both OpenAI and Anthropic backends.

=== "OpenAI Mode"

    ```bash
    export OPENAI_API_BASE="http://localhost:44497/v1"
    export OPENAI_API_KEY="your-anl-username"
    aider --model argo:gpt-4o
    ```

=== "Anthropic Mode"

    ```bash
    export ANTHROPIC_BASE_URL="http://localhost:44497"
    export ANTHROPIC_API_KEY="your-anl-username"
    aider --model argo:claude-4-sonnet
    ```

!!! tip
    You can add these to your `.aider.conf.yml` or shell profile for persistence.

---

## Gemini CLI

[Gemini CLI](https://github.com/google-gemini/gemini-cli) (tested with v0.34.0) connects via the **Google GenAI API** (`/v1beta/models/{model}:generateContent`).

=== "Config Files (Recommended)"

    **1. `~/.gemini/.env`** — Gemini CLI auto-reads this file on startup:

    ```bash
    GEMINI_API_KEY=your-anl-username
    GOOGLE_GEMINI_BASE_URL=http://localhost:44497
    ```

    **2. `~/.gemini/settings.json`** — set auth mode and default model:

    ```json
    {
        "model": {
            "name": "argo:gpt-4.1"
        },
        "security": {
            "auth": {
                "selectedType": "gemini-api-key"
            }
        }
    }
    ```

    With both files configured, just run `gemini` — no extra flags needed.

=== "Environment Variables"

    ```bash
    GOOGLE_GEMINI_BASE_URL=http://localhost:44497 \
    GEMINI_API_KEY=your-anl-username \
    gemini -m argo:gpt-4.1
    ```

!!! important
    - Set `GOOGLE_GEMINI_BASE_URL` to the proxy root (e.g., `http://localhost:44497`), **not** including any API path — Gemini CLI appends the path automatically
    - The `selectedType: "gemini-api-key"` setting tells Gemini CLI to use the API key auth flow instead of Google OAuth
    - The `model.name` field in `settings.json` sets the default model, so you don't need `-m` every time

!!! tip "Using with other proxies (e.g., OneAPI)"
    If your proxy expects Bearer token authentication, add this to `~/.gemini/.env`:

    ```bash
    GEMINI_API_KEY_AUTH_MECHANISM=bearer
    ```

    This tells the Google GenAI SDK to send the API key as a `Bearer` token in the `Authorization` header instead of as a query parameter.

---

## OpenCode

[OpenCode](https://github.com/opencode-ai/opencode) (tested with v1.2.27) supports OpenAI-compatible endpoints.

=== "Config File (Recommended)"

    Add a custom provider in `~/.config/opencode/opencode.json`:

    ```json
    {
        "provider": {
            "argo-proxy": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Argo Proxy",
                "options": {
                    "baseURL": "http://localhost:44497/v1",
                    "apiKey": "your-anl-username"
                },
                "models": {
                    "argo:gpt-4o": {
                        "name": "GPT-4o"
                    },
                    "argo:claude-4-sonnet": {
                        "name": "Claude 4 Sonnet"
                    }
                }
            }
        }
    }
    ```

=== "Environment Variables"

    ```bash
    export OPENAI_BASE_URL="http://localhost:44497/v1"
    export OPENAI_API_KEY="your-anl-username"
    opencode
    ```

---

## Kilo Code

[Kilo Code](https://kilocode.ai/) (VS Code extension) supports Anthropic API.

Configure in Kilo Code settings:

- **Base URL**: `http://localhost:44497`
- **API Key**: `your-anl-username`

---

## Generic OpenAI SDK

Any tool or script using the OpenAI Python SDK:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:44497/v1",
    api_key="your-anl-username",
)

response = client.chat.completions.create(
    model="argo:gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

## Generic Anthropic SDK

Any tool or script using the Anthropic Python SDK:

```python
import anthropic

client = anthropic.Anthropic(
    base_url="http://localhost:44497",
    api_key="your-anl-username",
)

message = client.messages.create(
    model="argo:claude-4-sonnet",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}],
)
print(message.content[0].text)
```

## Summary

| Tool | API Format | Base URL Env Var | Value |
|------|-----------|-----------------|-------|
| Claude Code | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:44497` |
| Codex CLI | OpenAI Responses | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| Aider (OpenAI) | OpenAI | `OPENAI_API_BASE` | `http://localhost:44497/v1` |
| Aider (Anthropic) | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:44497` |
| Gemini CLI | Google GenAI | `GOOGLE_GEMINI_BASE_URL` | `http://localhost:44497` (+ `~/.gemini/.env`) |
| OpenCode | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| OpenAI SDK | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| Anthropic SDK | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:44497` |

!!! note
    For all tools, use your ANL username as the API key. The actual authentication is handled by the ARGO backend based on your network identity.
