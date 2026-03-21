# User Guide

Argo Proxy v3 is a **universal API gateway** for LLM services via ARGO. It serves all major API formats — OpenAI Chat, OpenAI Responses, Anthropic Messages, and Google GenAI — from a single proxy instance, with automatic model-based routing and cross-format translation.

## Getting Started

- [**Installation**](installation.md): Install argo-proxy using pip
- [**Running**](running.md): Start the proxy server and perform first-time setup
- [**Models**](models.md): Choose from available chat and embedding models
- [**Endpoints**](endpoints.md): Learn about all available API endpoints
- [**CLI Tools Guide**](cli-tools.md): Configure Claude Code, Codex CLI, Aider, Gemini CLI, and more

## Reference

- [**Basics Topics**](basics/index.md): Configuration and CLI usage in depth
- [**Advanced Topics**](advanced/index.md): DNS resolution, streaming, vision, and tool use

## Quick Reference

- **Default Port**: Randomly assigned (can be configured)
- **Config File Locations**: `./config.yaml`, `~/.config/argoproxy/config.yaml`, `~/.argoproxy/config.yaml`
- **Health Check**: `GET /health`
- **Version Info**: `GET /version`
- **Refresh Models**: `POST /refresh`
- **OpenAI Chat**: `POST /v1/chat/completions`
- **OpenAI Responses**: `POST /v1/responses`
- **Anthropic Messages**: `POST /v1/messages`
- **Google GenAI**: `POST /v1beta/models/{model}:generateContent`
- **Embeddings**: `POST /v1/embeddings`
- **Model List**: `GET /v1/models`
