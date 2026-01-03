# Running the Application

## Basic Usage

To start the application:

```bash
argo-proxy [config_path]
```

### Without Arguments

```bash
argo-proxy
```

Search for `config.yaml` under:

- current directory
- `~/.config/argoproxy/`
- `~/.argoproxy/`

The first one found will be used.

### With Config Path

Uses specified config file, if exists. Otherwise, falls back to default search.

```bash
argo-proxy /path/to/config.yaml
```

## First-Time Setup

When running without an existing config file:

1. The script offers to create `config.yaml` from `config.sample.yaml`
2. Automatically selects a random available port (can be overridden)
3. Prompts for:
   - Your username (sets `user` field)
   - Verbose mode preference (sets `verbose` field)
4. Validates connectivity to configured URLs
5. Shows the generated config in a formatted display for review before proceeding

### Example Setup Session

```bash
$ argo-proxy
No valid configuration found.
Would you like to create it from config.sample.yaml? [Y/n]:
Creating new configuration...
Use port [52226]? [Y/n/<port>]:
Enter your username: your_username
Enable verbose mode? [Y/n]
Created new configuration at: /home/your_username/.config/argoproxy/config.yaml
Using port 52226...
Validating URL connectivity...
Current configuration:
--------------------------------------
{
    "host": "0.0.0.0",
    "port": 52226,
    "user": "your_username",
    "argo_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/",
    "argo_stream_url": "https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/streamchat/",
    "argo_embedding_url": "https://apps.inside.anl.gov/argoapi/api/v1/resource/embed/",
    "verbose": true
}
--------------------------------------
# ... proxy server starting info display ...
```

## Startup Process

1. **Configuration Loading**: Searches for and loads configuration file
2. **Validation**: Checks configuration syntax and required fields
3. **Connectivity Test**: Validates connection to ARGO API endpoints
4. **Server Start**: Starts the proxy server and begins accepting requests

## Troubleshooting

### Common Issues

- **Port already in use**: Choose a different port or stop the conflicting service
- **Configuration not found**: Ensure config file exists in expected locations
- **Connectivity issues**: Check network access to ARGO API endpoints. You may need to contact CELS IT for setting up firewall conduit.
- **Permission errors**: Ensure proper file permissions for config file
