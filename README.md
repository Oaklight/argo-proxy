# argo-proxy

[![PyPI version](https://badge.fury.io/py/argo-proxy.svg?icon=si%3Apython)](https://badge.fury.io/py/argo-proxy)
[![GitHub version](https://badge.fury.io/gh/oaklight%2Fargo-proxy.svg?icon=si%3Agithub)](https://badge.fury.io/gh/oaklight%2Fargo-proxy)

This project is a proxy application that forwards requests to an ARGO API and optionally converts the responses to be compatible with OpenAI's API format. It can be used in conjunction with [autossh-tunnel-dockerized](https://github.com/Oaklight/autossh-tunnel-dockerized) or other secure connection tools.

For detailed information, please refer to documentation at [argo-proxy ReadtheDocs page](https://argo-proxy.readthedocs.io/en/latest/)

## TL;DR

```bash
pip install argo-proxy # install the package
argo-proxy # run the proxy
```

Function calling is available for Chat Completions endpoint starting from `v2.7.5`.
Try with `pip install "argo-proxy>=2.7.5"`

**Now all models have native function calling in standard mode.** (Gemini native function calling support added in v2.8.0.)

## NOTICE OF USAGE

The machine or server making API calls to Argo must be connected to the Argonne internal network or through a VPN on an Argonne-managed computer if you are working off-site. Your instance of the argo proxy should always be on-premise at an Argonne machine. The software is provided "as is," without any warranties. By using this software, you accept that the authors, contributors, and affiliated organizations will not be liable for any damages or issues arising from its use. You are solely responsible for ensuring the software meets your requirements.

- [Notice of Usage](#notice-of-usage)
- [Deployment](#deployment)
  - [Prerequisites](#prerequisites)
  - [Configuration File](#configuration-file)
  - [Running the Application](#running-the-application)
  - [First-Time Setup](#first-time-setup)
  - [Configuration Options Reference](#configuration-options-reference)
  - [Streaming Modes: Real Stream vs Pseudo Stream](#streaming-modes-real-stream-vs-pseudo-stream)
  - [`argo-proxy` CLI Available Options](#argo-proxy-cli-available-options)
  - [Management Utilities](#management-utilities)
- [Usage](#usage)
  - [Endpoints](#endpoints)
    - [OpenAI Compatible](#openai-compatible)
    - [Not OpenAI Compatible](#not-openai-compatible)
    - [Timeout Override](#timeout-override)
  - [Models](#models)
    - [Chat Models](#chat-models)
    - [Embedding Models](#embedding-models)
  - [Tool Calls](#tool-calls)
    - [Tool Call Examples](#tool-call-examples)
    - [ToolRegistry](#toolregistry)
  - [Examples](#examples)
    - [Raw Requests](#raw-requests)
    - [OpenAI Client](#openai-client)
- [Bug Reports and Contributions](#bug-reports-and-contributions)

## Deployment

### Prerequisites

- **Python 3.10+** is required. </br>
  It is recommended to use conda, mamba, or pipx, etc., to manage an exclusive environment. </br>
  **Conda/Mamba** Download and install from: <https://conda-forge.org/download/> </br>
  **pipx** Download and install from: <https://pipx.pypa.io/stable/installation/>

- Install dependencies:

  PyPI current version: ![PyPI - Version](https://img.shields.io/pypi/v/argo-proxy)

  ```bash
  pip install argo-proxy
  ```

  To upgrade:

  ```bash
  argo-proxy --version  # Display current version
  # Check against PyPI version
  pip install argo-proxy --upgrade
  ```

  or, if you decide to use dev version (make sure you are at the root of the repo cloned):
  ![GitHub Release](https://img.shields.io/github/v/release/Oaklight/argo-proxy)

  ```bash
  pip install .
  ```

### Configuration File

If you don't want to manually configure it, the [First-Time Setup](#first-time-setup) will automatically create it for you.

The application uses `config.yaml` for configuration. Here's an example:

```yaml
argo_embedding_url: "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/"
argo_stream_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/"
argo_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
port: 44497
host: 0.0.0.0
user: "your_username" # set during first-time setup
verbose: true # can be changed during setup
```

### Running the Application

To start the application:

```bash
argo-proxy [config_path]
```

- Without arguments: search for `config.yaml` under:
  - current directory
  - `~/.config/argoproxy/`
  - `~/.argoproxy/`
    The first one found will be used.
- With path: uses specified config file, if exists. Otherwise, falls back to default search.

  ```bash
  argo-proxy /path/to/config.yaml
  ```

- With `--edit` flag: opens the config file in the default editor for modification.

### First-Time Setup

When running without an existing config file:

1. The script offers to create `config.yaml` from `config.sample.yaml`
2. Automatically selects a random available port (can be overridden)
3. Prompts for:
   - Your username (sets `user` field)
   - Verbose mode preference (sets `verbose` field)
4. Validates connectivity to configured URLs
5. Shows the generated config in a formatted display for review before proceeding

Example session:

```bash
$ argo-proxy
No valid configuration found.
Would you like to create it from config.sample.yaml? [Y/n]:
Creating new configuration...
Use port [52226]? [Y/n/<port>]:
Enter your username: your_username
Enable verbose mode? [Y/n]
Created new configuration at: /home/your_username/.config/argoproxy/config.yaml
Using port 52226...
Validating URL connectivity...
Current configuration:
--------------------------------------
{
    "host": "0.0.0.0",
    "port": 52226,
    "user": "your_username",
    "argo_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/",
    "argo_stream_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/",
    "argo_embedding_url": "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/",
    "verbose": true
}
--------------------------------------
# ... proxy server starting info display ...
```

### Configuration Options Reference

| Option               | Description                                                  | Default            |
| -------------------- | ------------------------------------------------------------ | ------------------ |
| `argo_embedding_url` | Argo Embedding API URL                                       | Prod URL           |
| `argo_stream_url`    | Argo Stream API URL                                          | Dev URL (for now)  |
| `argo_url`           | Argo Chat API URL                                            | Dev URL (for now)  |
| `host`               | Host address to bind the server to                           | `0.0.0.0`          |
| `port`               | Application port (random available port selected by default) | randomly assigned  |
| `user`               | Your username                                                | (Set during setup) |
| `verbose`            | Debug logging                                                | `true`             |
| `real_stream`        | Enable real streaming mode (default since v2.7.7)            | `true`             |

### Streaming Modes: Real Stream vs Pseudo Stream

Argo Proxy supports two streaming modes for chat completions:

#### Real Stream (Default since v2.7.7)

- **Default behavior**: Enabled by default since v2.7.7 (`real_stream: true` or omitted in config)
- **How it works**: Directly streams chunks from the upstream API as they arrive
- **Advantages**:
  - True real-time streaming behavior
  - Lower latency for streaming responses
  - More responsive user experience
  - **Recommended for production use**

#### Pseudo Stream

- **Enable via**: Set `real_stream: false` in config file or use `--pseudo-stream` CLI flag
- **How it works**: Receives the complete response from upstream, then simulates streaming by sending chunks to the client
- **Status**: Available for compatibility with previous behavior and function calling

#### Configuration Examples

**Via config file:**

```yaml
# Enable real streaming (experimental)
real_stream: true

# Or explicitly use pseudo streaming (default)
real_stream: false
```

**Via CLI flag:**

```bash
# Use default real streaming (since v2.7.7)
argo-proxy

# Enable legacy pseudo streaming
argo-proxy --pseudo-stream
```

#### Function Calling Behavior

When using function calling (tool calls):

- **Native function calling support**: Available for OpenAI and Anthropic models. Gemini models is in development
- **Real streaming compatible**: Native function calling works with both streaming modes
- **OpenAI format**: All input and output remains in OpenAI format regardless of underlying model
- **Legacy support**: Prompting-based function calling available via `--tool-prompting` flag

### `argo-proxy` CLI Available Options

```bash
$ argo-proxy -h
usage: argo-proxy [-h] [--host HOST] [--port PORT] [--verbose | --quiet]
                  [--real-stream | --pseudo-stream] [--tool-prompting]
                  [--edit] [--validate] [--show] [--version]
                  [config]

Argo Proxy CLI

positional arguments:
  config                Path to the configuration file

options:
  -h, --help            show this help message and exit
  --host HOST, -H HOST  Host address to bind the server to
  --port PORT, -p PORT  Port number to bind the server to
  --verbose, -v         Enable verbose logging, override if `verbose` set False in config
  --quiet, -q           Disable verbose logging, override if `verbose` set True in config
  --real-stream, -rs    Enable real streaming (default behavior), override if `real_stream` set False in config
  --pseudo-stream, -ps  Enable pseudo streaming, override if `real_stream` set True or omitted in config
  --tool-prompting      Enable prompting-based tool calls/function calling, otherwise use native tool calls/function calling
  --edit, -e            Open the configuration file in the system's default editor for editing
  --validate, -vv       Validate the configuration file and exit
  --show, -s            Show the current configuration during launch
  --version, -V         Show the version and check for updates
```

### Management Utilities

The following options help manage the configuration file:

- `--edit, -e`: Open the configuration file in the system's default editor for editing.
  - If no config file is specified, it will search in default locations (~/.config/argoproxy/, ~/.argoproxy/, or current directory)
  - Tries common editors like nano, vi, vim (unix-like systems) or notepad (Windows)

- `--validate, -vv`: Validate the configuration file and exit without starting the server.
  - Useful for checking config syntax and connectivity before deployment

- `--show, -s`: Show the current configuration during launch.
  - Displays the fully resolved configuration including defaults
  - Can be used with `--validate` to just display configuration without starting the server

```bash
# Example usage:
argo-proxy --edit  # Edit config file
argo-proxy --validate --show  # Validate and display config
argo-proxy --show  # Show config at startup
```

## Usage

### Endpoints

#### OpenAI Compatible

These endpoints convert responses from the ARGO API to be compatible with OpenAI's format:

- **`/v1/responses`**: Available from v2.7.0. Response API.
- **`/v1/chat/completions`**: Chat Completions API.
- **`/v1/completions`**: Legacy Completions API.
- **`/v1/embeddings`**: Embedding API.
- **`/v1/models`**: Lists available models in OpenAI-compatible format.

#### Not OpenAI Compatible

These endpoints interact directly with the ARGO API and do not convert responses to OpenAI's format:

- **`/v1/chat`**: Proxies requests to the ARGO API without conversion.
- **`/v1/embed`**: Proxies requests to the ARGO Embedding API without conversion.

#### Utility Endpoints

- **`/health`**: Health check endpoint. Returns `200 OK` if the server is running.
- **`/version`**: Returns the version of the ArgoProxy server. Notifies if a new version is available. Available from 2.7.0.post1.

#### Timeout Override

You can override the default timeout with a `timeout` parameter in your request. This parameter is optional for client request. Proxy server will keep the connection open until it finishes or client disconnects.

Details of how to make such override in different query flavors: [Timeout Override Examples](timeout_examples.md)

### Models

#### Chat Models

##### OpenAI Series

| Original ARGO Model Name | Argo Proxy Name                          |
| ------------------------ | ---------------------------------------- |
| `gpt35`                  | `argo:gpt-3.5-turbo`                     |
| `gpt35large`             | `argo:gpt-3.5-turbo-16k`                 |
| `gpt4`                   | `argo:gpt-4`                             |
| `gpt4large`              | `argo:gpt-4-32k`                         |
| `gpt4turbo`              | `argo:gpt-4-turbo`                       |
| `gpt4o`                  | `argo:gpt-4o`                            |
| `gpt4olatest`            | `argo:gpt-4o-latest`                     |
| `gpto1preview`           | `argo:gpt-o1-preview`, `argo:o1-preview` |
| `gpto1mini`              | `argo:gpt-o1-mini`, `argo:o1-mini`       |
| `gpto3mini`              | `argo:gpt-o3-mini`, `argo:o3-mini`       |
| `gpto1`                  | `argo:gpt-o1`, `argo:o1`                 |
| `gpto3`                  | `argo:gpt-o3`, `argo:o3`                 |
| `gpto4mini`              | `argo:gpt-o4-mini`, `argo:o4-mini`       |
| `gpt41`                  | `argo:gpt-4.1`                           |
| `gpt41mini`              | `argo:gpt-4.1-mini`                      |
| `gpt41nano`              | `argo:gpt-4.1-nano`                      |

##### Google Gemini Series

| Original ARGO Model Name | Argo Proxy Name         |
| ------------------------ | ----------------------- |
| `gemini25pro`            | `argo:gemini-2.5-pro`   |
| `gemini25flash`          | `argo:gemini-2.5-flash` |

##### Anthropic Claude Series

| Original ARGO Model Name | Argo Proxy Name                                    |
| ------------------------ | -------------------------------------------------- |
| `claudeopus4`            | `argo:claude-opus-4`, `argo:claude-4-opus`         |
| `claudesonnet4`          | `argo:claude-sonnet-4`, `argo:claude-4-sonnet`     |
| `claudesonnet37`         | `argo:claude-sonnet-3.7`, `argo:claude-3.7-sonnet` |
| `claudesonnet35v2`       | `argo:claude-sonnet-3.5`, `argo:claude-3.5-sonnet` |

#### Embedding Models

| Original ARGO Model Name | Argo Proxy Name               |
| ------------------------ | ----------------------------- |
| `ada002`                 | `argo:text-embedding-ada-002` |
| `v3small`                | `argo:text-embedding-3-small` |
| `v3large`                | `argo:text-embedding-3-large` |

### Tool Calls

The tool calls (function calling) interface has been available since version v2.7.5.alpha1, now with **native function calling support**.

#### Native Function Calling Support

- **OpenAI models**: Full native function calling support
- **Anthropic models**: Full native function calling support
- **Gemini models**: Full native function calling support (added in v2.8.0)
- **OpenAI format**: All input and output remains in OpenAI format regardless of underlying model

#### Availability

- Available on both streaming and non-streaming **chat completion** endpoints
- Only supported on `/v1/chat/completions` endpoint
- Argo passthrough endpoint (`/v1/chat`) and response endpoint (`/v1/chat/response`) not yet implemented due to limited development time
- Legacy completion endpoints (`/v1/completions`) do not support tool calling

#### Tool Call Examples

- **Function Calling OpenAI Client**: [function_calling_chat.py](examples/openai_client/function_calling_chat.py)
- **Function Calling Raw Request**: [function_calling_chat.py](examples/raw_requests/function_calling_chat.py)

For more usage details, refer to the [OpenAI documentation](https://platform.openai.com/docs/guides/function-calling).

#### ToolRegistry

A lightweight yet powerful Python helper library is available for various tool handling: [ToolRegistry](https://github.com/Oaklight/ToolRegistry). It works with any OpenAI-compatible API, including Argo Proxy starting from version v2.7.5.alpha1.

### Examples

#### Raw Requests

For examples of how to use the raw request utilities (e.g., `httpx`, `requests`), refer to:

##### Direct Access to ARGO

- **Direct Chat Example**: [argo_chat.py](examples/raw_requests/argo_chat.py)
- **Direct Chat Stream Example**: [argo_chat_stream.py](examples/raw_requests/argo_chat_stream.py)
- **Direct Embedding Example**: [argo_embed.py](examples/raw_requests/argo_embed.py)

##### OpenAI Compatible Requests

- **Chat Completions Example**: [chat_completions.py](examples/raw_requests/chat_completions.py)
- **Chat Completions Stream Example**: [chat_completions_stream.py](examples/raw_requests/chat_completions_stream.py)
- **Legacy Completions Example**: [legacy_completions.py](examples/raw_requests/legacy_completions.py)
- **Legacy Completions Stream Example**: [legacy_completions_stream.py](examples/raw_requests/legacy_completions_stream.py)
- **Responses Example**: [responses.py](examples/raw_requests/responses.py)
- **Responses Stream Example**: [responses_stream.py](examples/raw_requests/responses_stream.py)
- **Embedding Example**: [embedding.py](examples/raw_requests/embedding.py)
- **o1 Mini Chat Completions Example**: [o1_mini_chat_completions.py](examples/raw_requests/o1_mini_chat_completions.py)

#### OpenAI Client

For examples demonstrating the use case of the OpenAI client (`openai.OpenAI`), refer to:

- **Chat Completions Example**: [chat_completions.py](examples/openai_client/chat_completions.py)
- **Chat Completions Stream Example**: [chat_completions_stream.py](examples/openai_client/chat_completions_stream.py)
- **Legacy Completions Example**: [legacy_completions.py](examples/openai_client/legacy_completions.py)
- **Legacy Completions Stream Example**: [legacy_completions_stream.py](examples/openai_client/legacy_completions_stream.py)
- **Responses Example**: [responses.py](examples/openai_client/responses.py)
- **Responses Stream Example**: [responses_stream.py](examples/openai_client/responses_stream.py)
- **Embedding Example**: [embedding.py](examples/openai_client/embedding.py)
- **O3 Mini Simple Chatbot Example**: [o3_mini_simple_chatbot.py](examples/openai_client/o3_mini_simple_chatbot.py)

## Bug Reports and Contributions

This project is developed in my spare time. Bugs and issues may exist. If you encounter any or have suggestions for improvements, please [open an issue](https://github.com/Oaklight/argo-proxy/issues/new) or [submit a pull request](https://github.com/Oaklight/argo-proxy/compare). Your contributions are highly appreciated!
