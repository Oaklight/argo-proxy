# Configuration

## Configuration File

If you don't have a configuration file, the [First-Time Setup](../running.md#first-time-setup) will create one for you interactively. You can also migrate from v1/v2 configs using `argo-proxy config migrate`.

The application uses `config.yaml` for configuration. Here's the v3 format:

```yaml
# Config version (for migration tracking)
config_version: "3"

host: "0.0.0.0"
port: 44497
user: "your_username"

# Argo API base URL - all endpoint URLs are derived from this
argo_base_url: "https://apps-dev.inside.anl.gov/argoapi"

# Native upstream endpoint URLs (derived from argo_base_url if not set)
# native_openai_base_url: "https://apps-dev.inside.anl.gov/argoapi/v1"
# native_anthropic_base_url: "https://apps-dev.inside.anl.gov/argoapi"

verbose: true
```

In most cases, you only need to set `argo_base_url` — the native upstream URLs are automatically derived:

- `native_openai_base_url` defaults to `{argo_base_url}/v1`
- `native_anthropic_base_url` defaults to `{argo_base_url}` itself

## Configuration Options Reference

| Option | Description | Default |
|--------|-------------|---------|
| `config_version` | Config format version (set to `"3"` for v3) | `""` |
| `argo_base_url` | Base URL for the Argo API | Dev URL |
| `native_openai_base_url` | Base URL for OpenAI-compatible endpoints | `{argo_base_url}/v1` |
| `native_anthropic_base_url` | Base URL for Anthropic endpoint | `{argo_base_url}` |
| `host` | Host address to bind the server to | `0.0.0.0` |
| `port` | Application port | Randomly assigned |
| `user` | Your ANL username | (Set during setup) |
| `verbose` | Debug logging | `true` |
| `use_legacy_argo` | Enable legacy ARGO gateway mode | `false` |
| `skip_url_validation` | Skip URL connectivity check at startup | `false` |
| `connection_test_timeout` | Timeout (seconds) per URL validation request | `5` |
| `resolve_overrides` | DNS resolution overrides (see [DNS Resolution](../advanced/dns-resolution.md)) | `{}` |
| `enable_payload_control` | Enable automatic image payload size control | `false` |
| `max_payload_size` | Max payload size in MB (total for all images) | `20` |
| `image_timeout` | Image download timeout in seconds | `30` |
| `concurrent_downloads` | Max parallel image downloads | `10` |

## Configuration File Locations

The application searches for `config.yaml` in the following order:

1. Current directory (`./config.yaml`)
2. User config directory (`~/.config/argoproxy/config.yaml`)
3. User home directory (`~/.argoproxy/config.yaml`)

The first configuration file found will be used.

## Modes

### Universal Mode (Default)

In universal mode (the default in v3), argo-proxy acts as a universal API gateway:

- Serves all 4 API formats (OpenAI Chat, OpenAI Responses, Anthropic Messages, Google GenAI)
- Routes to native upstream endpoints based on model family
- Uses [llm-rosetta](https://github.com/Oaklight/llm-rosetta) for cross-format translation

The `config show` output displays:

```json
{
    "argo_base_url": "https://apps-dev.inside.anl.gov/argoapi",
    "mode": "universal",
    "native_anthropic_base_url": "https://apps-dev.inside.anl.gov/argoapi",
    "native_openai_base_url": "https://apps-dev.inside.anl.gov/argoapi/v1",
    "port": 44497,
    "user": "your_username",
    "verbose": true
}
```

### Legacy Mode

Enable with `use_legacy_argo: true` in config or `--legacy-argo` on the CLI. This uses the old ARGO gateway pipeline with individual endpoint URLs:

```yaml
use_legacy_argo: true
argo_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
argo_stream_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/"
argo_embedding_url: "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/"
```

!!! warning
    Legacy mode has limited streaming and tool call support. Use universal mode unless you have a specific reason for legacy mode.

## Migrating from v2

Run `argo-proxy config migrate` to automatically upgrade your config:

```bash
$ argo-proxy config migrate
Migrating config: /home/user/.config/argoproxy/config.yaml
Backup saved: /home/user/.config/argoproxy/config.yaml.bak
============================================================
Migration complete:
  - config_version: (none) -> 3
  - removed deprecated key: use_native_openai
  - added native_openai_base_url: https://apps-dev.inside.anl.gov/argoapi/v1
  - added native_anthropic_base_url: https://apps-dev.inside.anl.gov/argoapi
============================================================
```

## Security Considerations

- This application is only usable if you connect to Argonne network, which means:
    - on Argonne network/campus
    - connected via Argonne VPN
    - connected via ssh tunnel to Argonne machines
- The configuration file contains your username but no passwords or API keys

## Validation

Use `argo-proxy config validate` to check your configuration:

```bash
argo-proxy config validate
```

This will verify:

- Configuration file syntax
- Required fields presence
- URL connectivity (native endpoint in universal mode, gateway endpoints in legacy mode)
- Value validity
