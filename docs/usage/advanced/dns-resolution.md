# DNS Resolution Overrides

## Overview

DNS resolution overrides allow you to remap a hostname to a different IP address at the DNS level, without changing the actual URL used for HTTP requests. This is particularly useful when accessing the Argo API through SSH tunnels or port forwarding, where the original hostname must be preserved for TLS certificate validation and SNI (Server Name Indication).

This feature works similarly to `curl --resolve host:port:address` — it keeps the HTTP `Host` header and TLS SNI intact while directing the underlying TCP connection to a different IP address.

## Use Case: SSH Tunnel / Port Forwarding

A common scenario arises when you are off Argonne campus and need to access the Argo API through an SSH tunnel:

1. **You set up an SSH tunnel** to forward a remote Argo API port to your local machine:

    ```bash
    ssh -L 443:apps-dev.inside.anl.gov:443 user@anl-gateway-host
    ```

    This makes the Argo API available at `127.0.0.1:443` on your local machine.

2. **The problem**: If you simply change the base URL to `https://127.0.0.1/argoapi`, the TLS handshake will fail because the server's certificate is issued for `apps-dev.inside.anl.gov`, not `127.0.0.1`.

3. **The solution**: DNS resolution overrides let you keep the original URL (`https://apps-dev.inside.anl.gov/argoapi`) while transparently routing the connection to `127.0.0.1`. The TLS certificate validates correctly because the hostname in the request still matches the certificate.

!!! tip "Why not just disable TLS verification?"
    Disabling TLS verification (`verify=False`) is insecure and not recommended. DNS resolution overrides provide a clean, secure alternative that preserves the full TLS certificate chain validation.

## Configuration

Add the `resolve_overrides` section to your `config.yaml`:

```yaml
resolve_overrides:
  "apps-dev.inside.anl.gov:443": "127.0.0.1"
```

The key is a `"host:port"` string, and the value is the IP address to resolve to. You can specify multiple overrides:

```yaml
resolve_overrides:
  "apps-dev.inside.anl.gov:443": "127.0.0.1"
  "apps.inside.anl.gov:443": "127.0.0.1"
```

!!! warning
    The port in the key must match the port used in the actual connection. For HTTPS URLs, this is typically `443`.

## How It Works

Under the hood, argo-proxy uses a `StaticOverrideResolver` that intercepts DNS lookups before they reach the system resolver:

1. When argo-proxy makes an outgoing HTTP request to `apps-dev.inside.anl.gov:443`, the resolver checks if there is a matching override entry.
2. If a match is found, it returns the configured IP address (`127.0.0.1`) instead of performing a real DNS lookup.
3. The HTTP client then connects to `127.0.0.1:443` but sends the TLS ClientHello with SNI set to `apps-dev.inside.anl.gov`.
4. The `Host` header in the HTTP request also remains `apps-dev.inside.anl.gov`.

This means the remote server (or your SSH tunnel endpoint) sees a properly formed request, and TLS certificate validation succeeds because the hostname matches.

!!! note
    This mechanism is conceptually identical to adding an entry in `/etc/hosts` or using `curl --resolve`, but it is scoped only to argo-proxy and does not affect other applications on your system.

## Skip URL Validation

By default, argo-proxy validates that configured URLs are reachable at startup. When using DNS resolution overrides with SSH tunnels, the tunnel may not be established yet when argo-proxy starts, or the validation may fail for other reasons.

You can skip URL validation in two ways:

=== "config.yaml"

    ```yaml
    skip_url_validation: true
    ```

=== "Environment Variable"

    ```bash
    export SKIP_URL_VALIDATION=true
    ```

!!! tip "When to use `skip_url_validation`"
    - **CI/CD pipelines**: Where network connectivity may not be available during startup.
    - **Containerized deployments**: Where the SSH tunnel or network setup happens asynchronously.
    - **Development environments**: Where you want to start argo-proxy before establishing the tunnel.

## Complete Example

Here is a step-by-step example of setting up argo-proxy with an SSH tunnel and DNS resolution overrides.

### Step 1: Set Up the SSH Tunnel

Forward the remote Argo API port to your local machine:

```bash
ssh -N -L 443:apps-dev.inside.anl.gov:443 user@anl-gateway-host
```

!!! note
    The `-N` flag tells SSH not to execute a remote command, which is useful for port forwarding only. You may need `sudo` or root privileges to bind to port 443 locally. Alternatively, use a high port like `8443` and adjust the configuration accordingly.

If using a non-privileged local port:

```bash
ssh -N -L 8443:apps-dev.inside.anl.gov:443 user@anl-gateway-host
```

### Step 2: Configure `config.yaml`

```yaml
# Config version
config_version: "2"

host: "0.0.0.0"
port: 44497
user: "your_username"

# Keep the original Argo base URL for proper TLS/SNI
argo_base_url: "https://apps-dev.inside.anl.gov/argoapi"

verbose: true

# Skip validation since the tunnel may not be ready at startup
skip_url_validation: true

# Route DNS resolution to localhost where the SSH tunnel is listening
resolve_overrides:
  "apps-dev.inside.anl.gov:443": "127.0.0.1"
```

!!! warning "Using a non-standard local port"
    If you forwarded to a local port other than 443 (e.g., `8443`), you need to use the individual endpoint URL overrides with the custom port instead of `argo_base_url`, and adjust the resolve override key accordingly:

    ```yaml
    argo_url: "https://apps-dev.inside.anl.gov:8443/argoapi/api/v1/resource/chat/"
    argo_stream_url: "https://apps-dev.inside.anl.gov:8443/argoapi/api/v1/resource/streamchat/"
    argo_embedding_url: "https://apps-dev.inside.anl.gov:8443/argoapi/api/v1/resource/embed/"

    resolve_overrides:
      "apps-dev.inside.anl.gov:8443": "127.0.0.1"
    ```

### Step 3: Start argo-proxy

```bash
argo-proxy
```

argo-proxy will start and route all Argo API requests through your SSH tunnel while maintaining proper TLS certificate validation.