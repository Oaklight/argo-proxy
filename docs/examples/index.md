# Examples

This section provides comprehensive examples of how to use argo-proxy with different approaches and APIs.

## Raw Requests

For examples of how to use the raw request utilities (e.g., `httpx`, `requests`), refer to:

### Direct Access to ARGO

- **Direct Chat Example**: [argo_chat.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/argo_chat.py)
- **Direct Chat Stream Example**: [argo_chat_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/argo_chat_stream.py)
- **Direct Embedding Example**: [argo_embed.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/argo_embed.py)

### OpenAI Compatible Requests

- **Chat Completions Example**: [chat_completions.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/chat_completions.py)
- **Chat Completions Stream Example**: [chat_completions_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/chat_completions_stream.py)
- **Legacy Completions Example**: [legacy_completions.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/legacy_completions.py)
- **Legacy Completions Stream Example**: [legacy_completions_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/legacy_completions_stream.py)
- **Responses Example**: [responses.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/responses.py)
- **Responses Stream Example**: [responses_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/responses_stream.py)
- **Embedding Example**: [embedding.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/embedding.py)
- **o1 Mini Chat Completions Example**: [o1_mini_chat_completions.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/o1_mini_chat_completions.py)

### Vision and Image Input

- **Image Chat (Base64) Example**: [image_chat_base64.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/image_chat_base64.py)
- **Image Chat (URLs) Example**: [image_chat_direct_urls.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/image_chat_direct_urls.py)

## OpenAI Client

For examples demonstrating the use case of the OpenAI client (`openai.OpenAI`), refer to:

- **Chat Completions Example**: [chat_completions.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/chat_completions.py)
- **Chat Completions Stream Example**: [chat_completions_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/chat_completions_stream.py)
- **Legacy Completions Example**: [legacy_completions.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/legacy_completions.py)
- **Legacy Completions Stream Example**: [legacy_completions_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/legacy_completions_stream.py)
- **Responses Example**: [responses.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/responses.py)
- **Responses Stream Example**: [responses_stream.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/responses_stream.py)
- **Embedding Example**: [embedding.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/embedding.py)
- **O3 Mini Simple Chatbot Example**: [o3_mini_simple_chatbot.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/o3_mini_simple_chatbot.py)

### Vision and Image Input

- **Image Chat (Base64) Example**: [image_chat_base64.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/image_chat_base64.py)
- **Image Chat (URLs) Example**: [image_chat_direct_urls.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/image_chat_direct_urls.py)

## Tool Call Examples

The experimental tool calls (function calling) interface has been available since version v2.7.5.alpha1.

- **Function Calling OpenAI Client**: [function_calling_chat.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/openai_client/function_calling_chat.py)
- **Function Calling Raw Request**: [function_calling_chat.py](https://github.com/Oaklight/argo-proxy/blob/master/examples/raw_requests/function_calling_chat.py)

For more usage details, refer to the [OpenAI documentation](https://platform.openai.com/docs/guides/function-calling).

## Project Structure

```{note}
This project is still under active development. Folders and files may be added or removed without notice. The following is captured at version `v2.7.6`.
```

The following is an overview of the project's directory structure:

```bash
$ tree -I "__pycache__|*.egg-info|dist|dev_scripts|config.yaml|docs"
.
├── config.sample.yaml
├── examples
│   ├── openai_client
│   │   ├── chat_completions.py
│   │   ├── chat_completions_stream.py
│   │   ├── embedding.py
│   │   ├── function_calling_chat.py
│   │   ├── function_calling_response.py
│   │   ├── legacy_completions.py
│   │   ├── legacy_completions_stream.py
│   │   ├── o3_mini_simple_chatbot.py
│   │   ├── responses.py
│   │   └── responses_stream.py
│   └── raw_requests
│       ├── argo_chat.py
│       ├── argo_chat_stream.py
│       ├── argo_embed.py
│       ├── chat_completions.py
│       ├── chat_completions_stream.py
│       ├── embedding.py
│       ├── function_calling_chat.py
│       ├── function_calling_response.py
│       ├── legacy_completions.py
│       ├── legacy_completions_stream.py
│       ├── o1_mini_chat_completions.py
│       ├── responses.py
│       └── responses_stream.py
├── LICENSE
├── Makefile
├── pyproject.toml
├── README.md
├── run_app.sh
├── src
│   └── argoproxy
│       ├── app.py
│       ├── cli.py
│       ├── config.py
│       ├── endpoints
│       │   ├── chat.py
│       │   ├── completions.py
│       │   ├── embed.py
│       │   ├── extras.py
│       │   └── responses.py
│       ├── __init__.py
│       ├── models.py
│       ├── performance.py
│       ├── py.typed
│       ├── tool_calls
│       │   ├── input_handle.py
│       │   └── output_handle.py
│       ├── types
│       │   ├── chat_completion.py
│       │   ├── completions.py
│       │   ├── embedding.py
│       │   ├── function_call.py
│       │   ├── __init__.py
│       │   └── responses.py
│       └── utils
│           ├── input_handle.py
│           ├── misc.py
│           ├── tokens.py
│           └── transports.py
└── timeout_examples.md

10 directories, 54 files
```
