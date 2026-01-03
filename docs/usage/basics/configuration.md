# Configuration

## Configuration File

If you don't want to manually configure it, the [First-Time Setup](../running.md#first-time-setup) will automatically create it for you.

The application uses `config.yaml` for configuration. Here's an example:

```yaml
argo_embedding_url: "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/"
argo_stream_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/"
argo_url: "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/"
port: 44497
host: 0.0.0.0
user: "your_username" # set during first-time setup
verbose: true # can be changed during setup
```

## Configuration Options Reference

| Option               | Description                                                  | Default            |
| -------------------- | ------------------------------------------------------------ | ------------------ |
| `argo_embedding_url` | Argo Embedding API URL                                       | Prod URL           |
| `argo_stream_url`    | Argo Stream API URL                                          | Dev URL (for now)  |
| `argo_url`           | Argo Chat API URL                                            | Dev URL (for now)  |
| `host`               | Host address to bind the server to                           | `0.0.0.0`          |
| `port`               | Application port (random available port selected by default) | randomly assigned  |
| `user`               | Your username                                                | (Set during setup) |
| `verbose`            | Debug logging                                                | `true`             |
| `real_stream`        | Enable real streaming mode (experimental)                    | `false` (omitted)            |

## Configuration File Locations

The application searches for `config.yaml` in the following order:

1. Current directory (`./config.yaml`)
2. User config directory (`~/.config/argoproxy/config.yaml`)
3. User home directory (`~/.argoproxy/config.yaml`)

The first configuration file found will be used.

## Environment-Specific Configuration

### Development vs Production URLs

- **Chat/Stream URLs**: Currently pointing to development environment (`apps-dev.inside.anl.gov/argoapi/api/v1/`) as it has the latest features.
- **Embedding URL**: Points to production environment (`apps.inside.anl.gov/argoapi/api/v1/`) as it is stable.

This configuration may change as the service evolves.

### Port Configuration

- **Default**: A random available port is automatically selected during setup
- **Override**: You can specify a custom port in the config file or via CLI
- **Range**: Any valid port number (1-65535, though system ports 1-1023 typically require admin privileges)

## Security Considerations

- This application is only usable if you connect to Argonne network, which means:
  - on Argonne network/campus
  - connected via Argonne VPN
  - connected via ssh tunnel to Argonne machines
- The configuration file contains your username but no passwords or API keys

## Validation

Use the `--validate` flag to check your configuration:

```bash
argo-proxy --validate
```

This will verify:

- Configuration file syntax
- URL connectivity
- Required fields presence
- Value validity
