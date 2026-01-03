# User Guide

- [**Installation**](installation.md): Install Argo Proxy using pip
- [**Running**](running.md): Start the proxy server and perform first-time setup
- [**Models**](models.md): Choose from available chat and embedding models
- [**Endpoints**](endpoints.md): Learn about available API endpoints
- [**Native OpenAI Passthrough**](native-openai-passthrough.md): Direct passthrough mode for Argo Native OpenAI-compatible endpoints (optional, WIP)
- [**Basics Topics**](basics/index.md): Configuration and CLI usage in depth
- [**Advanced Topics**](advanced/index.md): Advanced features and topics

## Quick Reference

- **Default Port**: Randomly assigned (can be configured)
- **Config File Locations**: `./config.yaml`, `~/.config/argoproxy/config.yaml`, `~/.argoproxy/config.yaml`
- **Health Check**: `GET /health`
- **Version Info**: `GET /version`
- **OpenAI Compatible**: `/v1/chat/completions`, `/v1/embeddings`, `/v1/models`
