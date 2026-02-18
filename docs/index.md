---
title: Home
summary: An OpenAI-compatible proxy for Argo API
description: Argo Proxy is a proxy application that forwards requests to an ARGO API and optionally converts the responses to be compatible with OpenAI's API format.
keywords: python, proxy, openai, argo
author: Peng Ding
hide:
  - navigation
---

# Argo Proxy

[![PyPI version](https://badge.fury.io/py/argo-proxy.svg?icon=si%3Apython)](https://badge.fury.io/py/argo-proxy)
[![GitHub version](https://badge.fury.io/gh/Oaklight%2FArgo-Proxy.svg?icon=si%3Agithub)](https://badge.fury.io/gh/Oaklight%2FArgo-Proxy)

**An OpenAI-compatible proxy for Argo API** - designed for efficiency, reliability, and ease of use.

## 🚀 Quick Start

```bash
pip install argo-proxy # install the package
argo-proxy # run the proxy
```

Function calling is available for Chat Completions endpoint starting from `v2.7.5`. Try with `pip install "argo-proxy>=2.7.5"`
Native function calling are supported for all Chat models. Gemini support added in `v2.8.0`.

## ✨ Key Features

- **OpenAI Compatible** — Use any OpenAI SDK or client with `/v1/chat/completions`, `/v1/completions`, `/v1/responses`, `/v1/embeddings`
- **Anthropic Compatible** — Use the Anthropic SDK or [Claude Code](usage/native-anthropic-passthrough.md) with `/v1/messages`
- **Native Function Calling** — Tool calls supported for OpenAI, Anthropic, and Google models
- **Vision Support** — Automatic image URL download and base64 conversion
- **Live Model Refresh** — Reload model list via `POST /refresh` without restarting

## NOTICE OF USAGE

The machine or server making API calls to Argo must be connected to the Argonne internal network or through a VPN on an Argonne-managed computer if you are working off-site. Your instance of the argo proxy should always be on-premise at an Argonne machine. The software is provided "as is," without any warranties. By using this software, you accept that the authors, contributors, and affiliated organizations will not be liable for any damages or issues arising from its use. You are solely responsible for ensuring the software meets your requirements.

## 🤝 Get Involved

- **[GitHub Repository](https://github.com/Oaklight/argo-proxy)** - Source code and issues
- **[User Guide](usage/index.md)** - Complete user guide
