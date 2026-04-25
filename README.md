# argo-proxy

[![PyPI version](https://img.shields.io/pypi/v/argo-proxy?color=green)](https://pypi.org/project/argo-proxy/)
[![PyPI pre-release](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/Oaklight/c6a14fa27347321adfed1a01964b17c1/raw/pypi-badge.json)](https://pypi.org/project/argo-proxy/#history)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

A universal API gateway for LLM services via ARGO. Translates between OpenAI, Anthropic, and Google GenAI API formats, routing requests to optimal upstream ARGO endpoints. Works with AI coding tools like Claude Code, Codex CLI, Aider, Gemini CLI, and more.

For detailed documentation, visit the [argo-proxy ReadTheDocs page](https://argo-proxy.readthedocs.io/en/latest/).

## TL;DR

```bash
pip install argo-proxy   # install
argo-proxy serve         # start the proxy
```

A single proxy instance serves **all 4 major LLM API formats**:

| API Format | Endpoint | Example Client |
| --- | --- | --- |
| OpenAI Chat Completions | `/v1/chat/completions` | OpenAI SDK, Aider, OpenCode |
| OpenAI Responses | `/v1/responses` | Codex CLI |
| Anthropic Messages | `/v1/messages` | Claude Code, Kilo Code |
| Google GenAI | `/v1beta/models/{model}:generateContent` | Gemini CLI |

## NOTICE OF USAGE

The machine or server making API calls to Argo must be connected to the Argonne internal network or through a VPN on an Argonne-managed computer if you are working off-site. Your instance of the argo proxy should always be on-premise at an Argonne machine. The software is provided "as is," without any warranties. By using this software, you accept that the authors, contributors, and affiliated organizations will not be liable for any damages or issues arising from its use. You are solely responsible for ensuring the software meets your requirements.

- [Notice of Usage](#notice-of-usage)
- [Deployment](#deployment)
    - [Prerequisites](#prerequisites)
    - [Configuration](#configuration)
    - [Running the Proxy](#running-the-proxy)
    - [First-Time Setup](#first-time-setup)
    - [Configuration Options Reference](#configuration-options-reference)
    - [CLI Reference](#cli-reference)
- [Usage](#usage)
    - [Endpoints](#endpoints)
    - [Models](#models)
    - [Tool Calls](#tool-calls)
    - [AI Coding Tools Integration](#ai-coding-tools-integration)
    - [Examples](#examples)
- [Bug Reports and Contributions](#bug-reports-and-contributions)

## Deployment

### Prerequisites

- **Python 3.10+** is required. </br>
  Recommended: use conda, mamba, or pipx to manage an exclusive environment. </br>
  **Conda/Mamba** Download and install from: <https://conda-forge.org/download/> </br>
  **pipx** Download and install from: <https://pipx.pypa.io/stable/installation/>

- Install:

  PyPI current version: ![PyPI - Version](https://img.shields.io/pypi/v/argo-proxy)

  ```bash
  pip install argo-proxy
  ```

  To upgrade:

  ```bash
  argo-proxy update check    # check for updates (includes dependency status)
  argo-proxy update install  # install latest stable
  argo-proxy update install --pre  # install latest pre-release
  ```

  Or, from source (at the repo root):
  ![GitHub Release](https://img.shields.io/github/v/release/Oaklight/argo-proxy)

  ```bash
  pip install .
  ```

### Configuration

The application uses a YAML config file (v3 format). If you don't have one, [First-Time Setup](#first-time-setup) will create it interactively.

```yaml
config_version: "3"
user: "your_username"
host: 0.0.0.0
port: 44497
verbose: true

argo_base_url: "https://apps.inside.anl.gov/argoapi"
```

Config file search order (first found is used):

1. `./config.yaml` (current directory)
2. `~/.config/argoproxy/config.yaml`
3. `~/.argoproxy/config.yaml`

Migrate from v1/v2 config:

```bash
argo-proxy config migrate /path/to/old/config.yaml
```

### Running the Proxy

```bash
argo-proxy serve                     # default config search
argo-proxy serve /path/to/config.yaml  # explicit config
argo-proxy serve --verbose --show    # verbose mode, show config at startup
```

### First-Time Setup

Create a new config interactively:

```bash
argo-proxy config init
```

This will:

1. Prompt for your ANL username
2. Select a random available port (can be overridden)
3. Choose upstream environment (prod/dev/test)
4. Validate connectivity to upstream URLs
5. Write the config file to `~/.config/argoproxy/config.yaml`

### Configuration Options Reference

| Option | Description | Default |
| --- | --- | --- |
| `config_version` | Config format version | `"3"` |
| `user` | Your ANL username | (required) |
| `host` | Host address to bind to | `0.0.0.0` |
| `port` | Port number | `44497` |
| `verbose` | Enable verbose logging | `true` |
| `argo_base_url` | Base URL for ARGO API | Dev URL |
| `native_openai_base_url` | Custom OpenAI endpoint (auto-derived if unset) | — |
| `native_anthropic_base_url` | Custom Anthropic endpoint (auto-derived if unset) | — |
| `anthropic_stream_mode` | Non-streaming Anthropic handling: `force`/`retry`/`passthrough` | `force` |
| `force_conversion` | Always run full format conversion | `false` |
| `use_legacy_argo` | Use legacy ARGO gateway pipeline | `false` |
| `skip_url_validation` | Skip upstream URL checks on startup | `false` |
| `connection_test_timeout` | Seconds for URL validation | `5` |
| `resolve_overrides` | DNS overrides for SSH tunnels (host:port -> IP) | `{}` |
| `max_log_history` | Keep last N messages in verbose logs | `3` |
| `enable_payload_control` | Enable image payload size control | `false` |
| `max_payload_size` | Max image payload size in MB | `20` |
| `image_timeout` | Image download timeout in seconds | `30` |
| `concurrent_downloads` | Parallel image downloads | `10` |

### CLI Reference

```
argo-proxy [-h] [--version] {serve,config,logs,update,models}
```

| Command | Description |
| --- | --- |
| `serve [config]` | Start the proxy server |
| `config edit` | Open config in default editor |
| `config validate` | Validate config and check connectivity |
| `config show` | Display resolved config |
| `config migrate` | Migrate v1/v2 config to v3 |
| `config init` | Interactive config setup |
| `config list` | List all found config files |
| `config env [prod\|dev\|test]` | Show or switch upstream environment |
| `logs collect [--type TYPE]` | Collect diagnostic logs |
| `update check` | Check for updates (argo-proxy + llm-rosetta) |
| `update install [--pre]` | Install latest version |
| `models [--json]` | List available models and aliases |

Key `serve` flags:

```bash
argo-proxy serve --verbose               # verbose logging
argo-proxy serve --force-conversion      # always convert via llm-rosetta
argo-proxy serve --username-passthrough  # use API key as username
argo-proxy serve --anthropic-stream-mode retry  # try non-streaming first
argo-proxy serve --legacy-argo           # use legacy ARGO gateway pipeline
argo-proxy serve --dump-requests         # dump request/response for debugging
```

## Usage

### Endpoints

#### API Format Endpoints

All four formats are served simultaneously from a single proxy instance:

| Endpoint | Format | Typical Client |
| --- | --- | --- |
| `/v1/chat/completions` | OpenAI Chat Completions | OpenAI SDK, Aider, OpenCode |
| `/v1/responses` | OpenAI Responses | Codex CLI |
| `/v1/messages` | Anthropic Messages | Claude Code, Anthropic SDK |
| `/v1beta/models/{model}:generateContent` | Google GenAI | Gemini CLI |
| `/v1beta/models/{model}:streamGenerateContent` | Google GenAI (streaming) | Gemini CLI |
| `/v1/embeddings` | Embeddings | OpenAI SDK |

#### Utility Endpoints

| Endpoint | Description |
| --- | --- |
| `/v1/models` | List available models (OpenAI-compatible format) |
| `/refresh` | Reload model list from upstream (POST) |
| `/health` | Health check |
| `/version` | Version info with update status |

#### Timeout Override

You can override the default timeout with a `timeout` parameter in your request body. See [Timeout Override Examples](https://argo-proxy.readthedocs.io/en/latest/usage/basics/timeout_examples/) for details.

### Models

Models are **fetched dynamically from upstream** at startup. Use `argo-proxy models` or `GET /v1/models` to list all available models and aliases. Refresh without restart via `POST /refresh`.

#### Model Naming

Model names are flexible and case-insensitive:

- **OpenAI**: `argo:gpt-4o`, `gpt-4o`, `argo:gpt-4.1-mini`, `argo:o3-mini`
- **Claude**: `argo:claude-4-opus` or `argo:claude-opus-4`, `argo:claude-4.6-sonnet`
- **Gemini**: `argo:gemini-2.5-pro`, `argo:gemini-2.5-flash`
- **Embedding**: `argo:text-embedding-ada-002`, `argo:text-embedding-3-small`

The `argo:` prefix is optional -- bare model names like `gpt-4o` or `claude-4-sonnet` work too.

### Tool Calls

Native function calling is supported for **all three providers**:

- **OpenAI models**: Full native function calling
- **Anthropic models**: Full native function calling
- **Gemini models**: Full native function calling

Available on `/v1/chat/completions` in both streaming and non-streaming modes. Cross-format tool call translation is handled automatically via [llm-rosetta](https://github.com/Oaklight/llm-rosetta).

For usage details, refer to the [OpenAI function calling guide](https://platform.openai.com/docs/guides/function-calling) and the [tool calls documentation](https://argo-proxy.readthedocs.io/en/latest/usage/advanced/tools/getting-started/).

A lightweight tool management library is also available: [ToolRegistry](https://github.com/Oaklight/ToolRegistry).

### AI Coding Tools Integration

Argo-proxy works out of the box with popular AI coding tools:

| Tool | API Format | Base URL Env Var | Value |
| --- | --- | --- | --- |
| [Claude Code](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/#claude-code) | Anthropic | `ANTHROPIC_BASE_URL` | `http://localhost:<port>` |
| [Codex CLI](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/#codex-cli) | OpenAI Responses | `OPENAI_BASE_URL` | `http://localhost:<port>/v1` |
| [Aider](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/#aider) | OpenAI or Anthropic | `OPENAI_API_BASE` / `ANTHROPIC_BASE_URL` | `http://localhost:<port>/v1` |
| [Gemini CLI](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/#gemini-cli) | Google GenAI | `GOOGLE_GEMINI_BASE_URL` | `http://localhost:<port>` |
| [OpenCode](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/#opencode) | OpenAI | `OPENAI_BASE_URL` | `http://localhost:<port>/v1` |
| [Kilo Code](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/#kilo-code) | Anthropic | (VS Code settings) | `http://localhost:<port>` |

All tools use your ANL username as the API key. For detailed setup instructions, see the [CLI Tools Integration Guide](https://argo-proxy.readthedocs.io/en/latest/usage/cli-tools/).

### Examples

#### OpenAI Format

**SDK-based** (`openai.OpenAI`):
- [Chat Completions](examples/openai/sdk_based/chat_completions.py) | [Streaming](examples/openai/sdk_based/chat_completions_stream.py)
- [Responses](examples/openai/sdk_based/responses.py) | [Streaming](examples/openai/sdk_based/responses_stream.py)
- [Function Calling (Chat)](examples/openai/sdk_based/function_calling_chat.py) | [Function Calling (Responses)](examples/openai/sdk_based/function_calling_response.py)
- [Image Chat](examples/openai/sdk_based/image_chat_direct_urls.py) | [Image Base64](examples/openai/sdk_based/image_chat_base64.py)
- [Embedding](examples/openai/sdk_based/embedding.py)
- [Legacy Completions](examples/openai/sdk_based/legacy_completions.py) | [Streaming](examples/openai/sdk_based/legacy_completions_stream.py)

**REST-based** (`httpx` / `requests`):
- [Chat Completions](examples/openai/rest_based/chat_completions.py) | [Streaming](examples/openai/rest_based/chat_completions_stream.py)
- [Responses](examples/openai/rest_based/responses.py) | [Streaming](examples/openai/rest_based/responses_stream.py)
- [Function Calling](examples/openai/rest_based/function_calling_chat.py) | [Embedding](examples/openai/rest_based/embedding.py)

#### Anthropic Format

**SDK-based** (`anthropic.Anthropic`):
- [Native Messages](examples/anthropic/sdk_based/native_anthropic_test.py)
- [Function Calling](examples/anthropic/sdk_based/function_calling.py) | [Image Chat](examples/anthropic/sdk_based/image_chat.py)

**REST-based**:
- [Native Messages](examples/anthropic/rest_based/native_anthropic_messages.py) | [Streaming](examples/anthropic/rest_based/native_anthropic_messages_stream.py)
- [Function Calling](examples/anthropic/rest_based/function_calling.py) | [Image Chat](examples/anthropic/rest_based/image_chat.py)

#### Direct ARGO Access

- [Chat](examples/argo/argo_chat.py) | [Stream](examples/argo/argo_chat_stream.py) | [Embed](examples/argo/argo_embed.py)

## Bug Reports and Contributions

This project is developed in my spare time. Bugs and issues may exist. If you encounter any or have suggestions for improvements, please [open an issue](https://github.com/Oaklight/argo-openai-proxy/issues/new) or [submit a pull request](https://github.com/Oaklight/argo-openai-proxy/compare). Your contributions are highly appreciated!
