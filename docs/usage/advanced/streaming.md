# Streaming Modes

## Universal Mode (v3 Default)

In v3 universal mode, **real streaming is always used**. Requests are streamed through the native upstream endpoints (OpenAI-compatible or Anthropic), which provide full streaming support including tool calls.

The streaming mode options (`--real-stream`, `--pseudo-stream`, `real_stream` config) are **legacy-only** and have no effect in universal mode.

## Legacy Mode Streaming

When running in legacy mode (`--legacy-argo`), two streaming modes are available:

### Real Stream (Default)

- **Default behavior**: Enabled by default (omitted or `real_stream: true` in config)
- **How it works**: Directly streams chunks from the upstream ARGO API as they arrive
- **Status**: Production-ready and stable since v2.7.7

#### Configuration

**Via config file:**

```yaml
# Use default real streaming
# Simply omit the setting (defaults to true)

# Or explicitly enable real streaming
real_stream: true
```

**Via CLI:**

```bash
argo-proxy serve --legacy-argo --real-stream
```

### Pseudo Stream

- **Enable via**: Set `real_stream: false` in config file or `--pseudo-stream` CLI flag
- **How it works**: Receives the complete response from upstream, then simulates streaming by sending chunks to the client
- **Status**: Available for compatibility and specific use cases

#### When to Use

- When you find glitches or issues with real streaming in legacy mode

#### Configuration

**Via config file:**

```yaml
real_stream: false
```

**Via CLI:**

```bash
argo-proxy serve --legacy-argo --pseudo-stream
```

## Choosing the Right Mode

For most users, **universal mode with default streaming** is the best choice. The legacy streaming options exist only for backward compatibility.

| Mode | Streaming | Tool Calls | Recommendation |
|------|-----------|------------|----------------|
| Universal (v3) | Real streaming via native endpoints | Full support | **Recommended** |
| Legacy + Real Stream | Real streaming via ARGO gateway | Limited | Only if needed |
| Legacy + Pseudo Stream | Simulated streaming | Limited | Only for compatibility |

## Troubleshooting

### Common Issues

- **Streaming stops unexpectedly in legacy mode**: Switch to pseudo stream mode for more reliable results, or switch to universal mode.
- **High latency in pseudo mode**: Normal behavior if your task is relatively hard for the model, or you require longer responses.
- **Connection timeouts**: Consider increasing `connection_test_timeout` in your config or switching to universal mode.
