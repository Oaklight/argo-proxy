# CLI Tools Configuration

Argo Proxy v3 serves all major LLM API formats, which means it works out of the box with popular CLI tools and AI coding assistants. This guide shows how to configure each tool to use argo-proxy as its backend.

!!! note "Prerequisites"
    All examples assume argo-proxy is running at `http://localhost:44497`. Replace with your actual host and port.

    Your ANL username is used as the API key for all tools.

## Claude Code

[Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) connects via the **Anthropic Messages API** (`/v1/messages`).

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

[Codex CLI](https://github.com/openai/codex) connects via the **OpenAI Chat API** (`/v1/chat/completions`).

```bash
export OPENAI_BASE_URL="http://localhost:44497/v1"
export OPENAI_API_KEY="your-anl-username"
codex
```

Or pass inline:

```bash
OPENAI_BASE_URL="http://localhost:44497/v1" \
OPENAI_API_KEY="your-anl-username" \
codex
```

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

[Gemini CLI](https://github.com/google-gemini/gemini-cli) connects via the **Google GenAI API** (`/v1beta/models/{model}:generateContent`).

```bash
export GEMINI_API_BASE="http://localhost:44497"
export GEMINI_API_KEY="your-anl-username"
gemini
```

!!! note
    Gemini CLI support depends on the tool allowing custom base URLs. Check the tool's documentation for the exact environment variable names.

---

## OpenCode

[OpenCode](https://github.com/opencode-ai/opencode) supports OpenAI-compatible endpoints.

Configure in `~/.config/opencode/config.json` or via environment variables:

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
| Codex CLI | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| Aider (OpenAI) | OpenAI | `OPENAI_API_BASE` | `http://localhost:44497/v1` |
| Aider (Anthropic) | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:44497` |
| Gemini CLI | Google GenAI | `GEMINI_API_BASE` | `http://localhost:44497` |
| OpenCode | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| OpenAI SDK | OpenAI | `OPENAI_BASE_URL` | `http://localhost:44497/v1` |
| Anthropic SDK | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:44497` |

!!! note
    For all tools, use your ANL username as the API key. The actual authentication is handled by the ARGO backend based on your network identity.
