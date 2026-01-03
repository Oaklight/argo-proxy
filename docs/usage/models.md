# Available Models

Argo Proxy provides access to various AI models through the ARGO API, with OpenAI-compatible naming conventions for easy integration.

## Chat Models

### OpenAI Series

The OpenAI model series includes various GPT models with different capabilities and context lengths.

| Original ARGO Model Name | Argo Proxy Name                          | Description                    | Thinking |
| ------------------------ | ---------------------------------------- | ------------------------------ | -------- |
| `gpt35`                  | `argo:gpt-3.5-turbo`                     | GPT-3.5 Turbo                  | No       |
| `gpt35large`             | `argo:gpt-3.5-turbo-16k`                 | GPT-3.5 Turbo with 16K context | No       |
| `gpt4`                   | `argo:gpt-4`                             | GPT-4 base model               | No       |
| `gpt4large`              | `argo:gpt-4-32k`                         | GPT-4 with 32K context         | No       |
| `gpt4turbo`              | `argo:gpt-4-turbo`                       | GPT-4 Turbo                    | No       |
| `gpt4o`                  | `argo:gpt-4o`                            | GPT-4o                         | No       |
| `gpt4olatest`            | `argo:gpt-4o-latest`                     | Latest GPT-4o version          | No       |
| `gpto1preview`           | `argo:gpt-o1-preview`, `argo:o1-preview` | GPT-o1 Preview                 | **Yes**  |
| `gpto1mini`              | `argo:gpt-o1-mini`, `argo:o1-mini`       | GPT-o1 Mini                    | **Yes**  |
| `gpto3mini`              | `argo:gpt-o3-mini`, `argo:o3-mini`       | GPT-o3 Mini                    | **Yes**  |
| `gpto1`                  | `argo:gpt-o1`, `argo:o1`                 | GPT-o1                         | **Yes**  |
| `gpto3`                  | `argo:gpt-o3`, `argo:o3`                 | GPT-o3                         | **Yes**  |
| `gpto4mini`              | `argo:gpt-o4-mini`, `argo:o4-mini`       | GPT-o4 Mini                    | **Yes**  |
| `gpt41`                  | `argo:gpt-4.1`                           | GPT-4.1                        | No       |
| `gpt41mini`              | `argo:gpt-4.1-mini`                      | GPT-4.1 Mini                   | No       |
| `gpt41nano`              | `argo:gpt-4.1-nano`                      | GPT-4.1 Nano                   | No       |

### Google Gemini Series

Google's Gemini models offer advanced multimodal capabilities.

| Original ARGO Model Name | Argo Proxy Name         | Description      | Thinking |
| ------------------------ | ----------------------- | ---------------- | -------- |
| `gemini25pro`            | `argo:gemini-2.5-pro`   | Gemini 2.5 Pro   | **Yes**  |
| `gemini25flash`          | `argo:gemini-2.5-flash` | Gemini 2.5 Flash | **Yes**  |

### Anthropic Claude Series

Anthropic's Claude models are known for their safety and reasoning capabilities.

| Original ARGO Model Name | Argo Proxy Name                                    | Description       | Thinking |
| ------------------------ | -------------------------------------------------- | ----------------- | -------- |
| `claudeopus4`            | `argo:claude-opus-4`, `argo:claude-4-opus`         | Claude Opus 4     | **Yes**  |
| `claudesonnet4`          | `argo:claude-sonnet-4`, `argo:claude-4-sonnet`     | Claude Sonnet 4   | **Yes**  |
| `claudesonnet37`         | `argo:claude-sonnet-3.7`, `argo:claude-3.7-sonnet` | Claude Sonnet 3.7 | **Yes**  |
| `claudesonnet35v2`       | `argo:claude-sonnet-3.5`, `argo:claude-3.5-sonnet` | Claude Sonnet 3.5 | No       |

## Embedding Models

Embedding models convert text into numerical vectors for similarity search, clustering, and other ML tasks.

| Original ARGO Model Name | Argo Proxy Name               | Description                   | Thinking |
| ------------------------ | ----------------------------- | ----------------------------- | -------- |
| `ada002`                 | `argo:text-embedding-ada-002` | OpenAI Ada 002 embeddings     | N/A      |
| `v3small`                | `argo:text-embedding-3-small` | OpenAI text-embedding-3-small | N/A      |
| `v3large`                | `argo:text-embedding-3-large` | OpenAI text-embedding-3-large | N/A      |
