# Streaming Modes

Argo Proxy supports two streaming modes for Chat Completions, Legacy Completions and Responses endpoints. Each mode has its own advantages and use cases. This guide explains the differences between the two modes and helps you choose the right one for your needs.

Why use stream mode?
Some applications - llm clients, IDE extensions (like cline, continue.dev) and many chat-based tools—require stream mode to function correctly. Stream mode also allows you to create apps that provide a "flowing" feeling, letting users see responses generated word-by-word or line-by-line in real time, rather than waiting for the full output. This can greatly improve the responsiveness and perceived performance of your application.

## Real Stream (Default since v2.7.7)

- **Default behavior**: Enabled by default starting from v2.7.7 (omitted or `real_stream: true` in config)
- **How it works**: Directly streams chunks from the upstream API as they arrive
- **Status**: Production-ready and stable since v2.7.7

### Advantages

- True real-time streaming behavior
- Lower latency for streaming responses
- More responsive user experience

### Configuration

**Via config file:**

```yaml
# Use default real streaming (since v2.7.7)
# Simply omit the setting (defaults to true)

# Or explicitly enable real streaming
real_stream: true
```

**Via CLI:**

```bash
# Use default real streaming (since v2.7.7)
argo-proxy
```

## Pseudo Stream

- **Enable via**: Set `real_stream: false` in config file
- **How it works**: Receives the complete response from upstream, then simulates streaming by sending chunks to the client
- **Status**: available for compatibility and specific use cases

### When to Use

- When you find glitches or issues with real streaming

### Advantages

- More stable and reliable experience
- Better error handling and recovery
- Consistent performance

### Disadvantages

- "Hard task" for LLM may take longer to start streaming

### Configuration

**Via config file:**

```yaml
# Explicitly enable pseudo streaming (legacy)
real_stream: false
```

## Function Calling Behavior

When using function calling (tool calls):

- **Pseudo stream is automatically enforced** regardless of your configuration
- This ensures reliable function call processing with the current prompting-based implementation
- Users will not notice this automatic switch as the experience remains smooth
- Native function calling support is work in progress (WIP)

## Choosing the Right Mode

### Use Real Stream When (Default since v2.7.7)

- Running in production environments
- You want the best streaming performance
- Most general use cases
- When you need true real-time streaming behavior

### Use Pseudo Stream When

- You experience issues with real streaming
- Network conditions are highly variable
- You prefer the previous behavior

## Troubleshooting

### Common Issues

- **Streaming stops unexpectedly**: Switch to pseudo stream mode for more reliable results.
- **High latency in pseudo mode**: Normal behavior if your task is relatively hard for the model, or you require longer responses.
- **Connection timeouts in real mode**: Consider switching to pseudo stream for better reliability
