# Running the Application

## Basic Usage

To start the application:

```bash
argo-proxy serve [config_path]
```

Or simply (backward compatible):

```bash
argo-proxy [config_path]
```

### Without Arguments

```bash
argo-proxy
```

Searches for `config.yaml` under:

- current directory
- `~/.config/argoproxy/`
- `~/.argoproxy/`

The first one found will be used.

### With Config Path

Uses specified config file, if it exists. Otherwise, falls back to default search.

```bash
argo-proxy serve /path/to/config.yaml
```

## First-Time Setup

When running without an existing config file:

1. The script offers to create `config.yaml` interactively
2. Automatically selects a random available port (can be overridden)
3. Prompts for:
    - Your username (sets `user` field)
    - Verbose mode preference (sets `verbose` field)
4. Validates connectivity to upstream endpoints
5. Shows the generated config for review before proceeding

### Example Setup Session

```
$ argo-proxy
No valid configuration found.
Would you like to create it from config.sample.yaml? [Y/n]:
Creating new configuration...
Use port [52226]? [Y/n/<port>]:
Enter your username: your_username
Enable verbose mode? [Y/n]
Created new configuration at: /home/your_username/.config/argoproxy/config.yaml

Validating URL connectivity...
All URLs connectivity validated successfully.

Current configuration:
--------------------------------------
{
    "argo_base_url": "https://apps-dev.inside.anl.gov/argoapi",
    "mode": "universal",
    "native_anthropic_base_url": "https://apps-dev.inside.anl.gov/argoapi",
    "native_openai_base_url": "https://apps-dev.inside.anl.gov/argoapi/v1",
    "port": 52226,
    "user": "your_username",
    "verbose": true
}
--------------------------------------
```

## Startup Process

1. **Banner**: Displays ASCII banner with version and mode information
2. **Configuration Loading**: Searches for and loads configuration file
3. **Validation**: Checks configuration syntax, required fields, and URL connectivity
4. **Mode Display**: Shows operating mode (Universal or Legacy)
5. **Model Registry**: Loads available models from upstream and displays model stats
6. **Server Start**: Starts the proxy server and begins accepting requests

### Startup Banner

The startup banner shows the current version, update availability, and operating mode:

```
============================================================
🚀 ARGO PROXY v3.0.0 (Latest)
⚙️  MODE: Universal (llm-rosetta)
============================================================
```

## Managing Configuration

Use the `config` subcommand to manage your configuration without starting the server:

```bash
# Edit config in your default editor
argo-proxy config edit

# Validate config and test connectivity
argo-proxy config validate

# Show current config
argo-proxy config show

# Migrate from v2 to v3
argo-proxy config migrate
```

## Checking for Updates

```bash
# Check available versions
argo-proxy update check

# Install latest stable
argo-proxy update install

# Install latest pre-release
argo-proxy update install --pre
```

## Troubleshooting

### Common Issues

- **Port already in use**: Choose a different port or stop the conflicting service
- **Configuration not found**: Ensure config file exists in expected locations
- **Connectivity issues**: Check network access to ARGO API endpoints. You may need to contact CELS IT for setting up firewall conduit.
- **Permission errors**: Ensure proper file permissions for config file
- **Deprecated config warnings**: Run `argo-proxy config migrate` to update your v2 config to v3 format
