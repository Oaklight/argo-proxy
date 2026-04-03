# Streaming Modes

## Universal Mode (v3 Default)

In v3 universal mode, **real streaming is always used**. Requests are streamed through the native upstream endpoints (OpenAI-compatible or Anthropic), which provide full streaming support including tool calls.

The streaming mode options (`--real-stream`, `--pseudo-stream`, `real_stream` config) are **legacy-only** and have no effect in universal mode.

### Anthropic Non-Streaming Handling

Anthropic's API returns an HTTP 500 error ("Streaming is required for operations that may take longer than 10 minutes") for non-streaming requests that it predicts will be long-running. This bounce-back is returned immediately, not after a timeout.

The `--anthropic-stream-mode` option controls how argo-proxy handles this:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `force` (default) | Always force streaming upstream, aggregate SSE events back into a non-streaming response | Most reliable, no risk of bounce-back |
| `retry` | Try non-streaming first; on bounce-back, auto-retry with forced streaming and dump the request for diagnostics | Best for collecting diagnostic data while maintaining reliability |
| `passthrough` | Never force streaming, pass through as-is | Debugging, or when all requests are known to be short |

#### Configuration

**Via CLI:**

```bash
argo-proxy serve --anthropic-stream-mode retry
```

**Via config file:**

```yaml
anthropic_stream_mode: retry
```

**Via environment variable:**

```bash
ANTHROPIC_STREAM_MODE=retry argo-proxy serve
```

#### Retry Mode Diagnostics

When `retry` mode triggers a forced-streaming retry, the original request is saved to `<config_dir>/stream_retry_dumps/` as a timestamped JSON file containing:

- The full request body
- The upstream URL
- The error status code and error text
- A timestamp

These dump files can be collected with `argo-proxy logs collect --type stream-retry` for analysis.

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
