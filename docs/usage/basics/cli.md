# CLI Options

The Argo Proxy command-line interface provides comprehensive options for configuration, management, and operation.

## Command Syntax

```bash
argo-proxy [-h] [--host HOST] [--port PORT] [--verbose | --quiet]
           [--real-stream | --pseudo-stream] [--tool-prompting]
           [--edit] [--validate] [--show] [--version]
           [config]
```

## Positional Arguments

### config

Path to the configuration file.

```bash
argo-proxy /path/to/config.yaml
```

- **Optional**: If not provided, searches default locations
- **Fallback**: If specified file doesn't exist, falls back to default search

## Optional Arguments

### Help and Information

#### `-h, --help`

Show help message and exit.

```bash
argo-proxy --help
```

#### `--version, -V`

Show the version and check for updates.

```bash
argo-proxy --version
```

- **Enhanced**: Also checks for available updates from PyPI
- **Information**: Displays current version and update instructions if newer version available

### Server Configuration

#### `--host HOST, -H HOST`

Host address to bind the server to.

```bash
argo-proxy --host 127.0.0.1
argo-proxy -H 0.0.0.0
```

- **Default**: Uses value from config file or `0.0.0.0`
- **Override**: Command-line value takes precedence over config file

#### `--port PORT, -p PORT`

Port number to bind the server to.

```bash
argo-proxy --port 8080
argo-proxy -p 44497
```

- **Default**: Uses value from config file or random available port
- **Override**: Command-line value takes precedence over config file

### Logging Control

#### `--verbose, -v`

Enable verbose logging.

```bash
argo-proxy --verbose
argo-proxy -v
```

- **Override**: Enables verbose logging even if `verbose: false` in config
- **Mutually exclusive**: Cannot be used with `--quiet`

#### `--quiet, -q`

Disable verbose logging.

```bash
argo-proxy --quiet
argo-proxy -q
```

- **Override**: Disables verbose logging even if `verbose: true` in config
- **Mutually exclusive**: Cannot be used with `--verbose`

### Streaming Configuration

#### `--real-stream, -rs`

Enable real streaming mode (default since v2.7.7).

```bash
argo-proxy --real-stream
argo-proxy -rs
```

- **Override**: Explicitly enables real streaming even if `real_stream: false` in config
- **Default**: Real streaming is the default behavior since v2.7.7

#### `--pseudo-stream, -ps`

Enable pseudo streaming mode.

```bash
argo-proxy --pseudo-stream
argo-proxy -ps
```

- **Override**: Enables pseudo streaming even if `real_stream: true` or omitted in config
- **Mutually exclusive**: Cannot be used with `--real-stream`

### Tool Calling Configuration

#### `--tool-prompting`

Enable prompting-based tool calls/function calling.

```bash
argo-proxy --tool-prompting
```

- **Behavior**: Uses prompting-based approach instead of native tool calls

### Configuration Management

#### `--edit, -e`

Open the configuration file in the system's default editor.

```bash
argo-proxy --edit
argo-proxy -e
```

- **Search**: If no config file specified, searches default locations
- **Editors**: Tries common editors (nano, vi, vim on Unix; notepad on Windows)
- **No server start**: Only opens editor, doesn't start the proxy server

#### `--validate, -vv`

Validate the configuration file and exit.

```bash
argo-proxy --validate
argo-proxy -vv
```

- **Validation**: Checks config syntax and connectivity
- **No server start**: Exits after validation without starting server
- **Useful for**: Deployment scripts and configuration testing

#### `--show, -s`

Show the current configuration during launch.

```bash
argo-proxy --show
argo-proxy -s
```

- **Display**: Shows fully resolved configuration including defaults
- **Combination**: Can be used with `--validate` to display without starting server

## Usage Examples

### Basic Usage

```bash
# Start with default configuration (real streaming since v2.7.7)
argo-proxy

# Start with specific config file
argo-proxy /path/to/config.yaml

# Start with custom host and port
argo-proxy --host 127.0.0.1 --port 8080

# Use legacy pseudo streaming
argo-proxy --pseudo-stream

# Enable tool prompting mode
argo-proxy --tool-prompting

# Combine multiple options
argo-proxy --pseudo-stream --tool-prompting --verbose

# Validate configuration without starting server
argo-proxy --validate --show
```
