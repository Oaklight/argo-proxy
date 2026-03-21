---
title: Home
summary: A universal API gateway for LLM services via Argo
description: Argo Proxy is a universal API gateway that translates between OpenAI, Anthropic, and Google GenAI formats, routing to the optimal upstream ARGO endpoint automatically.
keywords: python, proxy, openai, anthropic, google, argo, llm, gateway
author: Peng Ding
hide:
  - navigation
---

# Argo Proxy

[![PyPI version](https://img.shields.io/pypi/v/argo-proxy?color=green)](https://pypi.org/project/argo-proxy/)
[![PyPI pre-release](https://img.shields.io/pypi/v/argo-proxy?include_prereleases&label=pre-release&color=green)](https://pypi.org/project/argo-proxy/)

[![GitHub Release](https://img.shields.io/github/v/release/Oaklight/argo-proxy?color=green)](https://github.com/Oaklight/argo-proxy/releases)

**A universal API gateway for LLM services via Argo** — translates between OpenAI, Anthropic, and Google GenAI formats, routing requests to the optimal upstream ARGO endpoint automatically.

## Quick Start

```bash
pip install argo-proxy        # install the package
argo-proxy serve              # run the proxy in universal mode
```

## Key Features

- **Universal API Gateway** — Serve all 4 major API formats from a single proxy:
    - OpenAI Chat Completions (`/v1/chat/completions`)
    - OpenAI Responses (`/v1/responses`)
    - Anthropic Messages (`/v1/messages`)
    - Google GenAI (`/v1beta/models/{model}:generateContent`)
- **Smart Model Routing** — Automatically routes to the optimal upstream (OpenAI-compatible or native Anthropic) based on the requested model
- **Cross-Format Translation** — powered by [llm-rosetta](https://github.com/Oaklight/llm-rosetta), seamlessly converts between API formats when needed
- **CLI Tool Ready** — Works out of the box with Claude Code, Codex CLI, Aider, Gemini CLI, OpenCode, and more (see [CLI Tools Guide](usage/cli-tools.md))
- **Native Function Calling** — Full tool call support across all providers and formats
- **Vision Support** — Automatic image URL download and base64 conversion
- **Live Model Refresh** — Reload model list via `POST /refresh` without restarting
- **Self-Update** — Built-in `argo-proxy update check` and `argo-proxy update install` commands

## NOTICE OF USAGE

The machine or server making API calls to Argo must be connected to the Argonne internal network or through a VPN on an Argonne-managed computer if you are working off-site. Your instance of the argo proxy should always be on-premise at an Argonne machine. The software is provided "as is," without any warranties. By using this software, you accept that the authors, contributors, and affiliated organizations will not be liable for any damages or issues arising from its use. You are solely responsible for ensuring the software meets your requirements.

## Get Involved

- **[GitHub Repository](https://github.com/Oaklight/argo-proxy)** - Source code and issues
- **[User Guide](usage/index.md)** - Complete user guide
