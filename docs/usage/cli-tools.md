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
    model = "argo:gpt-5"
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
    aider --model argo:gpt-5
    ```

=== "Anthropic Mode"

    ```bash
    export ANTHROPIC_BASE_URL="http://localhost:44497"
    export ANTHROPIC_API_KEY="your-anl-username"
    aider --model argo:claude-4.5-sonnet
    ```

!!! tip
    You can add these to your `.aider.conf.yml` or shell profile for persistence.

---

## Gemini CLI (Discontinued)

!!! warning "Discontinued"
    Gemini CLI stopped serving on 2026-06-18 and has been replaced by [Google Antigravity CLI (agy)](#google-antigravity-cli-agy). The section below is kept for reference only.

[Gemini CLI](https://github.com/google-gemini/gemini-cli) connected via the **Google GenAI API** (`/v1beta/models/{model}:generateContent`).

=== "Config Files"

    **1. `~/.gemini/.env`**:

    ```bash
    GEMINI_API_KEY=your-anl-username
    GOOGLE_GEMINI_BASE_URL=http://localhost:44497
    ```

    **2. `~/.gemini/settings.json`**:

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

=== "Environment Variables"

    ```bash
    GOOGLE_GEMINI_BASE_URL=http://localhost:44497 \
    GEMINI_API_KEY=your-anl-username \
    gemini -m argo:gpt-4.1
    ```

---

## Google Antigravity CLI (agy)

[Google Antigravity CLI](https://developers.google.com/gemini/agy) (`agy`; legacy mode first documented on v1.1.20, gateway mode verified on v1.3.5) is the successor to Gemini CLI. It speaks the **Google GenAI API** (`/v1beta/models/{model}:generateContent`) and also has an undocumented **gateway mode** that accepts the OpenAI wire protocol.

=== "Gateway Mode (Recommended)"

    Gateway mode is configured entirely through environment variables. It authenticates with a bearer token, sends the model id **verbatim**, and skips agy's built-in Gemini catalog — which is what makes non-Google models such as `argo:claude-opus-4.6` actually take effect.

    **1. `~/.gemini/antigravity-cli/settings.json`** — `model` is a **string** (v1.3.5 rejects `{"name": ...}`), and `modelProvider` must be **absent**:

    ```json
    {
        "model": "argo:claude-opus-4.6"
    }
    ```

    **2. Environment variables** (add to shell profile):

    ```bash
    export AGY_LLM_GATEWAY_URL="http://localhost:44497"
    export AGY_LLM_GATEWAY_API_KEY="your-anl-username"
    export AGY_LLM_GATEWAY_WIRE_PROTOCOL="openai"
    export AGY_LLM_GATEWAY_MODELS="argo:claude-opus-4.6"
    ```

    Then just run `agy`.

    `AGY_LLM_GATEWAY_WIRE_PROTOCOL` accepts only two values:

    - `openai` — `/v1/models` plus chat completions
    - `genai` — `/v1beta/models/{model}:streamGenerateContent`

    Any other value is rejected (`gateway wireProtocol "<x>" is unsupported; must be "genai" or "openai"`). argo-proxy serves both.

    Set `AGY_LLM_GATEWAY_MODELS` (comma-separated) as well. Without it, agy fetches the gateway's model catalog, and that **discovery stops at 32 models** (`44 custom gateway model(s) exceeded the maximum placeholder limit (32); skipped to prevent Model enum collision`); a `model` outside the first 32 silently resolves to whichever model sits at index 0. With the list set, discovery is skipped entirely and `model` is matched against it verbatim.

=== "Legacy GenAI Mode"

    **1. `~/.gemini/antigravity-cli/settings.json`**:

    ```json
    {
        "modelProvider": "gemini",
        "model": "argo:gpt-5"
    }
    ```

    **2. Environment variables** (add to shell profile):

    ```bash
    export GEMINI_API_KEY="your-anl-username"
    export GOOGLE_GEMINI_BASE_URL="http://localhost:44497"
    ```

    `model` must be a plain string. The `{"name": ...}` object form used by older agy versions is rejected on v1.3.x with `invalid settings: model`.

    Then just run `agy`.

    This path still works against argo-proxy, but agy resolves `model` against its own built-in Gemini catalog first, so a non-Google id is replaced before the request is sent (`model alias "argo:claude-opus-4.6" resolved to "Gemini 3.1 Pro (Low)"`). Prefer gateway mode when you want a specific non-Google model.

!!! important "Planner model requirement"
    agy uses a hardcoded internal planner model (`gemini-3.1-pro-preview`) alongside your chosen model. This **cannot be overridden** via `settings.json` or CLI flags — there is no user-facing configuration for it. The model must be available on the upstream — argo-proxy maps it automatically if the upstream provides it.

!!! note
    - Config path changed from Gemini CLI's `~/.gemini/settings.json` to `~/.gemini/antigravity-cli/settings.json`
    - `modelProvider: "gemini"` belongs to legacy mode only. In gateway mode it must be absent — with it set, agy demands a `GEMINI_API_KEY` that gateway mode never reads and exits with `modelProvider is set to "gemini" ... but the GEMINI_API_KEY environment variable is not set`
    - agy sends `x-goog-api-key` header for auth, which argo-proxy supports natively
    - HTTP/2 is not required; agy works over both HTTP/2 and HTTP/1.1

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
                    "argo:gpt-5": {
                        "name": "GPT-5"
                    },
                    "argo:claude-4.5-sonnet": {
                        "name": "Claude 4.5 Sonnet"
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
    model="argo:gpt-5",
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
    model="argo:claude-4.5-sonnet",
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
| Gemini CLI (discontinued) | Google GenAI | `GOOGLE_GEMINI_BASE_URL` | `http://localhost:44497` |
| agy (legacy mode) | Google GenAI | `GOOGLE_GEMINI_BASE_URL` | `http://localhost:44497` |
| agy (gateway mode) | GenAI or OpenAI | `AGY_LLM_GATEWAY_URL` | `http://localhost:44497` |
| OpenCode | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| OpenAI SDK | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| Anthropic SDK | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:44497` |

!!! note
    For all tools, use your ANL username as the API key. The actual authentication is handled by the ARGO backend based on your network identity.
