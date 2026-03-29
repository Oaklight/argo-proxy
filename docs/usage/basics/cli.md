# CLI Reference

Argo Proxy v3 uses a subcommand-based CLI. If no subcommand is given, `serve` is assumed for backward compatibility.

## Top-Level Usage

```
argo-proxy [-h] [-V] {serve,config,logs,update,models} ...
```

### Global Options

| Option | Description |
|--------|-------------|
| `-h, --help` | Show help message and exit |
| `-V, --version` | Show version and check for updates |

---

## `serve` — Start the Proxy Server

The default subcommand. Starts the argo-proxy server in **universal mode** (all 4 API formats).

```bash
argo-proxy serve [config] [options]
```

Backward-compatible shorthand (no subcommand):

```bash
argo-proxy config.yaml --port 8080 --verbose
```

### Positional Arguments

| Argument | Description |
|----------|-------------|
| `config` | Path to configuration file (optional, searches default locations if omitted) |

### Server Options

| Option | Description |
|--------|-------------|
| `--host HOST, -H HOST` | Host address to bind the server to (default: from config or `0.0.0.0`) |
| `--port PORT, -p PORT` | Port number (default: from config or random available port) |
| `--verbose, -v` | Enable verbose logging |
| `--quiet, -q` | Disable verbose logging |
| `--show, -s` | Show the current configuration during launch |
| `--no-banner` | Suppress the ASCII banner on startup |
| `--username-passthrough` | Use API key from request headers as user field |
| `--legacy-argo` | Use legacy ARGO gateway pipeline instead of universal dispatch |

### Legacy-Only Options

These options only apply when `--legacy-argo` is enabled:

| Option | Description |
|--------|-------------|
| `--real-stream, -rs` | Enable real streaming (default behavior) |
| `--pseudo-stream, -ps` | Enable pseudo streaming |
| `--tool-prompting` | Enable prompting-based tool calls |
| `--enable-leaked-tool-fix` | Enable AST-based leaked tool call detection |

### Examples

```bash
# Start in universal mode (default)
argo-proxy serve

# Start with custom host and port
argo-proxy serve --host 127.0.0.1 --port 8080

# Start with specific config file
argo-proxy serve /path/to/config.yaml

# Show config on startup
argo-proxy serve --show --verbose

# Start in legacy ARGO gateway mode
argo-proxy serve --legacy-argo
```

---

## `config` — Manage Configuration

Manage configuration files without starting the server.

```bash
argo-proxy config {edit,validate,show,migrate,init,env} [config]
```

### Actions

#### `config edit`

Open the configuration file in the system's default editor.

```bash
argo-proxy config edit
argo-proxy config edit /path/to/config.yaml
```

#### `config validate`

Validate the configuration file and test connectivity.

```bash
argo-proxy config validate
```

In universal mode, validates connectivity to the native OpenAI models endpoint (`GET /v1/models`). In legacy mode, validates the ARGO gateway chat and embedding endpoints.

#### `config show`

Display the fully resolved configuration.

```bash
argo-proxy config show
```

Shows different fields depending on mode:

- **Universal mode**: `argo_base_url`, `native_openai_base_url`, `native_anthropic_base_url`
- **Legacy mode**: `argo_url`, `argo_stream_url`, `argo_embedding_url`

#### `config migrate`

Migrate configuration from v1/v2 format to v3 format.

```bash
argo-proxy config migrate
argo-proxy config migrate /path/to/config.yaml
```

This will:

1. Create a `.bak` backup of the original file
2. Set `config_version: "3"`
3. Infer `argo_base_url` from legacy individual endpoint URLs if not set
4. Remove deprecated keys (`use_native_openai`, `use_native_anthropic`, `provider_tool_format`)
5. Drop stale/unknown fields and produce canonical v3 output

#### `config init`

Create a new configuration interactively. Reuses the same wizard as first-time setup.

```bash
# Create at default location (~/.config/argoproxy/config.yaml)
argo-proxy config init

# Create at custom path
argo-proxy config init /path/to/config.yaml

# Overwrite existing config without confirmation
argo-proxy config init --force
```

| Option | Description |
|--------|-------------|
| `config` | Custom file path (optional) |
| `--force, -f` | Overwrite existing config without confirmation |

#### `config env`

Show or switch the upstream ARGO API environment.

```bash
# Show current environment
argo-proxy config env

# Switch to production
argo-proxy config env prod

# Switch with explicit config path
argo-proxy config env dev -c /path/to/config.yaml
```

Available environments:

| Environment | Base URL |
|-------------|----------|
| `prod` | `https://apps.inside.anl.gov/argoapi` |
| `dev` | `https://apps-dev.inside.anl.gov/argoapi` (default) |
| `test` | `https://apps-test.inside.anl.gov/argoapi` |

| Option | Description |
|--------|-------------|
| `environment` | Target environment: `prod`, `dev`, or `test` (optional — omit to show current) |
| `-c, --config` | Config file path |

---

## `logs` — Collect Diagnostic Logs

Collect leaked tool call logs for analysis and debugging.

```bash
argo-proxy logs {collect} [config]
```

### Actions

#### `logs collect`

Collect all leaked tool call logs into a timestamped tar.gz archive.

```bash
argo-proxy logs collect
```

---

## `update` — Check and Install Updates

Check for new versions and install updates.

```bash
argo-proxy update {check,install} [options]
```

### Actions

#### `update check`

Check for available stable and pre-release versions on PyPI.

```bash
argo-proxy update check
```

Example output:

```
argo-proxy v3.0.0b3 (installed)

  Stable:      v2.8.9  (installed is newer)
  Pre-release: v3.0.0b3  (up to date)

  Changelog:    https://argo-proxy.readthedocs.io/en/latest/changelog/
```

#### `update install`

Install the latest version.

```bash
# Install latest stable
argo-proxy update install

# Install latest pre-release
argo-proxy update install --pre
```

Automatically detects `uv`, `pip`, or `python -m pip` for installation.

---

## `models` — List Available Models

List all available upstream models with their aliases and family classification.

```bash
argo-proxy models [config] [--json]
```

### Options

| Option | Description |
|--------|-------------|
| `config` | Path to configuration file (optional) |
| `--json` | Output in JSON format |

### Examples

```bash
# List models in table format
argo-proxy models

# Output as JSON
argo-proxy models --json
```

Example output:

```
Available models: 22 models, 50 aliases

  OpenAI (8 models)
    gpt4o                          argo:gpt-4o
    gpt4omini                      argo:gpt-4o-mini
    ...

  Anthropic (5 models)
    claudesonnet4                  argo:claude-4-sonnet, argo:claude-sonnet-4
    claudeopus4                    argo:claude-4-opus, argo:claude-opus-4
    ...

  Google (4 models)
    gemini25flash                  argo:gemini-2.5-flash
    ...
```

---

## Environment Variables

The following environment variables override configuration file settings:

| Variable | Description |
|----------|-------------|
| `CONFIG_PATH` | Path to config file |
| `PORT` | Server port |
| `VERBOSE` | Enable/disable verbose logging |
| `ARGO_BASE_URL` | Override the Argo base URL |
| `USE_LEGACY_ARGO` | Enable legacy ARGO gateway mode |
| `SKIP_URL_VALIDATION` | Skip URL validation at startup |

!!! note "Deprecated Environment Variables"
    The following variables are deprecated in v3.0.0 and will be ignored with a warning:

    - `USE_NATIVE_OPENAI` — native endpoints are now used by default
    - `USE_NATIVE_ANTHROPIC` — native endpoints are now used by default
    - `PROVIDER_TOOL_FORMAT` — format conversion is handled by llm-rosetta
