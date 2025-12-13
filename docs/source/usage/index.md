# User Guide

```{toctree}
:maxdepth: 1

installation
running
models
endpoints
native-openai-passthrough
basics/index
advanced/index
```

## Getting Started

## Overview

Argo Proxy provides a comprehensive OpenAI-compatible interface to the ARGO API system. The basic usage workflow involves:

- [**Installation**](installation): Install Argo Proxy using pip
- [**Running**](running): Start the proxy server and perform first-time setup
- [**Models**](models): Choose from available chat and embedding models
- [**Endpoints**](endpoints): Learn about available API endpoints
- [**Native OpenAI Passthrough**](native-openai-passthrough): Direct passthrough mode for Argo Native OpenAI-compatible endpoints (optional, WIP)
- [**Basics Topics**](basics/index): Configuration and CLI usage in depth
- [**Advanced Topics**](advanced/index): Advanced features and topics

## Quick Reference

- **Default Port**: Randomly assigned (can be configured)
- **Config File Locations**: `./config.yaml`, `~/.config/argoproxy/config.yaml`, `~/.argoproxy/config.yaml`
- **Health Check**: `GET /health`
- **Version Info**: `GET /version`
- **OpenAI Compatible**: `/v1/chat/completions`, `/v1/embeddings`, `/v1/models`
