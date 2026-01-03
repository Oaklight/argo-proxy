# Timeout Override

You can override the default timeout with a `timeout` parameter in your request. This parameter is optional for client request. Proxy server will keep the connection open until it finishes or client disconnects.

## Raw Request Examples

### Using httpx

```python
import httpx

# Chat completions with timeout override
response = httpx.post(
    "http://localhost:44497/v1/chat/completions",
    json={
        "model": "argo:gpt-4",
        "messages": [{"role": "user", "content": "Hello!"}],
        "timeout": 120  # 120 seconds timeout
    },
    timeout=130  # Client timeout should be longer than server timeout
)
```

### Using requests

```python
import requests

# Chat completions with timeout override
response = requests.post(
    "http://localhost:44497/v1/chat/completions",
    json={
        "model": "argo:gpt-4",
        "messages": [{"role": "user", "content": "Hello!"}],
        "timeout": 120  # 120 seconds timeout
    },
    timeout=130  # Client timeout should be longer than server timeout
)
```

## OpenAI Client Examples

### Using OpenAI Python Client

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:44497/v1",
    api_key="dummy"  # Required but not used
)

# Chat completions with timeout override
response = client.chat.completions.create(
    model="argo:gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_body={"timeout": 120},  # 120 seconds timeout
    timeout=130  # Client timeout should be longer than server timeout
)
```

### Streaming with Timeout Override

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:44497/v1",
    api_key="dummy"
)

# Streaming chat completions with timeout override
stream = client.chat.completions.create(
    model="argo:gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True,
    extra_body={"timeout": 120},  # 120 seconds timeout
    timeout=130  # Client timeout should be longer than server timeout
)

for chunk in stream:
    if chunk.choices[0].delta.content is not None:
        print(chunk.choices[0].delta.content, end="")
```

## Important Notes

1. **Server vs Client Timeout**: Always set your client timeout to be longer than the server timeout to avoid premature disconnections.

2. **Default Behavior**: If no timeout is specified, the proxy server will use its default timeout settings.

3. **Streaming Considerations**: For streaming requests, the timeout applies to the entire stream duration, not individual chunks.

4. **Error Handling**: If the server timeout is exceeded, you'll receive an appropriate error response from the proxy.
