# Changelog

This page records the major version changes and important feature updates of the Argo Proxy project.

## v3.0.0 (2026-04-19)

**First stable release of the v3 architecture.**

After 16 beta iterations (b4–b16), argo-proxy v3 is now considered production-ready. This release includes all beta changes plus two final fixes.

### Fixed

- **`max_tokens` → `max_completion_tokens` in passthrough mode** (#112): OpenAI deprecated `max_tokens` for newer models (GPT-4o, o1, etc.). In same-format passthrough (`openai_chat → openai_chat`), the deprecated parameter was forwarded as-is, causing 400 errors. Now automatically converted to `max_completion_tokens`
- **`thinking.type: "adaptive"` normalization** (#112): Anthropic's `adaptive` thinking type is not supported by all upstream gateways. In passthrough mode, now automatically converted to `"enabled"` with `budget_tokens` derived from `max_tokens`
- **`content: null` normalization** (#113): Assistant messages with `tool_calls` often have `content: null` (valid per OpenAI API spec). Some upstream gateways crash when iterating over null content. Now normalized to `content: ""` in all dispatch paths

### Changed

- Requires llm-rosetta >= 0.5.1

**Full Changelog**: https://github.com/Oaklight/argo-proxy/compare/v3.0.0b16...v3.0.0<br>
**PyPI**: https://pypi.org/project/argo-proxy/3.0.0/

### Post v3.0.0 Updates (2026-04-19)

**Dependency Reduction**

- Replaced `PyYAML` and `packaging` with vendored zero-dependency modules (`zerodep/yaml` v0.3.1, `zerodep/semver` v0.4.0), reducing external runtime dependencies from 8 to 6

**Dependency Update Detection**

- Added llm-rosetta update detection to all version-check touchpoints:
    - `argo-proxy update check` now shows a table with both argo-proxy and llm-rosetta versions (columns: Package, Installed, Stable, Pre, Status)
    - `argo-proxy --version` appends dependency status when updates are available
    - Startup banner shows a warning when llm-rosetta has an update
    - `/version` endpoint includes a `dependencies` field in the JSON response

**CI/CD**

- Added CI workflow (`.github/workflows/ci.yml`) with ruff lint, format check, and ty type check
- Pinned dev tooling: ruff >= 0.15.0, ty >= 0.0.31, complexipy >= 5.2.0

---

## v3.0.0b16 (2026-04-16)

### Fixed

- **Gemini parallel tool call rejection via ARGO gateway** (#109): The ANL ARGO gateway rejects requests containing parallel tool calls (multiple `tool_calls` in a single assistant message) for Gemini models. argo-proxy now detects Gemini-family models and automatically reorders parallel tool calls into sequential assistant+tool message pairs before forwarding upstream. The reordering logic has been extracted from the legacy pipeline into `utils/tool_calls.py` for long-term maintainability

## v3.0.0b15 (2026-04-14)

### Fixed

- **`developer` role rejected by Argo upstream** (#107): The ANL Argo gateway uses an older OpenAI SDK that does not recognize the `developer` role (introduced for reasoning models o1/o3/o4). The gateway mishandles the unrecognized role, injecting a spurious `tool_calls` field and causing a misleading `Unknown parameter: 'messages[0].tool_calls'` error. argo-proxy now downgrades `developer` → `system` in all outbound paths (passthrough, cross-format, buffered-streaming). The mapping is safe — all OpenAI models accept `system`

### New

- **Metadata preservation via `ConversionContext`** (#105): All cross-format conversion paths now thread a shared `ConversionContext(options={"metadata_mode": "preserve"})` through the full request→response lifecycle. This enables lossless round-trip conversion of provider-specific metadata fields (e.g. `refusal`, `annotations`, `citations`, extended usage details) that were previously dropped

### Changed

- **Bumped llm-rosetta to v0.5.0**: Picks up developer role mapping fix in Responses converter, tool call ID prefix mapping for cross-format conversion, Google modality token handling, and gateway admin features ([Oaklight/llm-rosetta v0.4.2–v0.5.0](https://github.com/Oaklight/llm-rosetta/releases/tag/v0.5.0))

## v3.0.0b14 (2026-04-11)

### New

- **`--force-conversion` mode**: New CLI flag and config option (`force_conversion: true`) that forces all requests through the full llm-rosetta conversion pipeline (source → IR → target), even when source and target providers match. This bypasses same-format passthrough and enables parameter normalization (e.g. `max_tokens` → `max_completion_tokens` for OpenAI Chat), full IR validation on every request, and more detailed runtime error/warning logs from the conversion pipeline. Disabled by default to preserve existing passthrough behavior. Configurable via `--force-conversion` CLI flag, `FORCE_CONVERSION` environment variable, or `force_conversion: true` in config.yaml

### Changed

- **Bumped llm-rosetta to v0.4.1**: Picks up Open Responses spec support, metadata preservation for lossless A→IR→A round-trip across all 4 providers, `force_conversion` parameter for full pipeline execution on same-provider requests, multimodal tool result conversion (#99), and vendored validate.py with type introspection caching ([Oaklight/llm-rosetta v0.4.0–v0.4.1](https://github.com/Oaklight/llm-rosetta/releases/tag/v0.4.1))

## v3.0.0b13 (2026-04-08)

### New

- **Upstream error request/response dumping**: All dispatch paths (passthrough, buffered, streaming, cross-format conversion) now dump request and response payloads on any upstream 4xx/5xx error to `<config_dir>/error_dumps/` for diagnostics. Dumps include source/target provider context for easier debugging of cross-provider conversion issues. Registered as `error-dump` in `argo-proxy logs collect --type` (#100, #101)

### Improved

- **`config list` discovers all config file variants**: Previously only checked 3 hardcoded paths. Now uses glob patterns to find all config files (e.g. `config.ozan.yaml`, `config-public.yaml`) across standard search directories

### Fixed

- **`input_image` type rejected by Anthropic in cross-provider conversion** (#99): Multimodal tool results (e.g. matplotlib plots from MCP servers) containing OpenAI's `input_image` content type were passed through to Anthropic without conversion, causing 400 errors. Fixed upstream in llm-rosetta via multimodal tool result conversion across all 4 providers (Oaklight/llm-rosetta#92)
- **`StreamContext` import path**: Updated import to match llm-rosetta v0.3.0 module structure

### Changed

- **Bumped llm-rosetta to v0.3.1**: Picks up multimodal tool result conversion (#99), `StreamContext` import path fix, and streaming reliability improvements ([Oaklight/llm-rosetta v0.3.0–v0.3.1](https://github.com/Oaklight/llm-rosetta/releases/tag/v0.3.1))

## v3.0.0b12 (2026-04-03)

### New

- **Configurable Anthropic non-streaming stream mode** (`--anthropic-stream-mode`): Controls how non-streaming requests to Anthropic upstream are handled. Three modes:
    - `force` (default): Always force streaming upstream and aggregate SSE events back into a non-streaming response. This is the same behavior as v3.0.0b9+ and avoids Anthropic's "Streaming is required for operations that may take longer than 10 minutes" bounce-back error
    - `retry`: Try the request as non-streaming first. If Anthropic returns the "streaming required" bounce-back (HTTP 500), automatically retry with forced streaming. Dumps the original request to `<config_dir>/stream_retry_dumps/` for diagnostics
    - `passthrough`: Never force streaming, pass through as-is. Useful for debugging or when requests are known to be short
- **Generalized `logs collect` CLI**: `argo-proxy logs collect` now supports `--type {leaked-tool,stream-retry,all}` to collect different categories of diagnostic logs. Default is `all`. New log categories can be added by registering in `_DIAGNOSTIC_LOG_TYPES`
- **`config list` subcommand**: `argo-proxy config list` lists all config files found in standard search paths, marking the active one
- **Unified `/version` endpoint**: The HTTP `/version` endpoint now returns both stable and pre-release version info (matching CLI `update check` behavior), with `latest_stable`, `latest_pre`, `update_commands` (CLI + pip), and `changelog` URL

### Improved

- **CLI output cleanup**: All CLI subcommand output (`config`, `update`, `logs`) now uses clean `print()` instead of `log_info()` with timestamps, producing cleaner terminal output
- **Dual update commands**: Version check surfaces (`--version`, startup banner, `update check`, `/version` endpoint) now show both `argo-proxy update install` (primary) and `pip install --upgrade` (alternative) as upgrade paths

### Changed

- **`ANTHROPIC_STREAM_MODE` environment variable**: New env var to set the Anthropic stream mode without CLI flags. Accepts `force`, `retry`, or `passthrough`
- **`anthropic_stream_mode` config field**: Can also be set in `config.yaml` (persisted only when non-default). Placed in the "Upstream" config section
- **Legacy code consolidation**: All legacy-only modules (`types/`, `tool_calls/`, legacy endpoints, legacy utils) moved under `_legacy/` top-level package. Embeddings passthrough extracted to `endpoints/passthrough.py` for universal mode. `utils/models.py` cleaned up — dead code removed, legacy-only functions moved to `_legacy/utils/models.py`

## v3.0.0b11 (2026-03-31)

### Improved

- **CLI typo detection**: Misspelled subcommands now show a helpful suggestion instead of silently falling through to the `serve` handler with the typo treated as a config file path (e.g. `argo-proxy server` → `unknown command 'server'. Did you mean 'serve'?`). Uses `difflib.get_close_matches` with cutoff 0.9; file-path-like arguments (containing `.`, `/`, `\`, or matching an existing file) are excluded from fuzzy matching
- **Reduced default log history truncation**: Verbose request logs now keep the last 3 conversation history items (down from 5) to reduce noise from large message entries

### New

- **`max_log_history` config option**: Controls how many conversation history items are kept in verbose request logs. Default: `3`. Set higher if you need more context in logs for debugging long conversations

## v3.0.0b10 (2026-03-29)

### Features

- **File logging with gzip rotation**: New `log_to_file` config option enables structured file logging to `~/.local/share/argoproxy/logs/` with automatic daily rotation and gzip compression of old files. Console output remains unchanged
- **Diagnostic logging for streaming chunks**: Verbose mode now logs the first upstream chunk and stream completion stats (chunk count, duration) for easier debugging

### Improved

- **Request logging — history truncation and Responses API support** *([@caidao22](https://github.com/caidao22))*: Conversation history in logs is now truncated to the last 5 items (configurable via `max_history_items`) with a `[... N earlier items omitted ...]` placeholder. Added sanitization for Responses API `input` items (`input_text`/`output_text` truncation). Request summary now includes `input=N` for Responses API requests. `log_converted_request` gated behind verbose check to skip unnecessary deep copies
- **Per-request user tagging in logs**: When `USERNAME_PASSTHROUGH=true`, all dispatch log entries now include `user=<identity>` so operators can trace requests back to individual users for debugging. Uses `contextvars` to tag all log calls within a request's lifetime — covers `[ORIGINAL]`, `[CONVERTED]`, `[UPSTREAM ERROR]`, `[ModelRegistry]`, and all dispatch-level messages

### Fixed

- **Auth credential fallback in dispatch upstream headers**: When clients (e.g. Codex CLI) send no auth headers, upstream requests were missing credentials entirely, causing 401 errors. Added `_extract_client_credential()` with provider-aware header priority (Anthropic prefers `x-api-key`, OpenAI prefers `Authorization: Bearer`) and `_build_upstream_headers()` with `fallback_user` parameter — without `--username-passthrough`, always uses `config.user`; with it, extracts from client request first, falls back to `config.user`
- **Graceful client disconnect handling**: Client disconnects during streaming no longer produce noisy tracebacks — `ConnectionResetError` is caught and logged cleanly
- **Catch aiohttp `ClientConnectionResetError` in dispatch**: aiohttp's `ClientConnectionResetError` (raised when writing to a closing transport) is not a subclass of stdlib `ConnectionResetError`, so it was falling through to the generic exception handler and logging as `ERROR`. Now caught explicitly alongside stdlib connection errors and logged as a warning

### Changed

- **Bumped llm-rosetta to v0.2.6**: Picks up orphaned tool_call IR-level fix, parallel tool_call_index propagation, Responses streaming item_id tracking, non-function tool name preservation, orphaned tool_choice stripping, and stream event ordering fixes ([Oaklight/llm-rosetta v0.2.6](https://github.com/Oaklight/llm-rosetta/releases/tag/v0.2.6))

## v3.0.0b9 (2026-03-29)

### Features

- **`config init` subcommand**: Interactive config creation wizard, accessible via `argo-proxy config init [path] [--force]`. Supports custom file paths and overwrite confirmation for existing configs. Reuses the same interactive flow as first-time setup
- **`config env` subcommand**: Show or switch upstream ARGO API environment via `argo-proxy config env [prod|dev|test]`. Three environments available: production (`apps.inside.anl.gov`), development (`apps-dev.inside.anl.gov`, default), and test (`apps-test.inside.anl.gov`)

### Changed

- **ReadTheDocs links in CLI help**: Each subcommand's `--help` now includes a `Docs:` URL pointing to the corresponding ReadTheDocs page
- **Updated `config.sample.yaml` and configuration docs**: Reorganized sample config with logical section grouping matching `_format_config_yaml()` output. Added upstream environment table (prod/dev/test URLs), conditional fields documentation, and removed legacy endpoint examples

### Fixed

- **Force streaming for Anthropic non-streaming requests**: Anthropic API requires streaming for operations that may exceed 10 minutes, causing `500` errors (`"Streaming is required for operations that may take longer than 10 minutes"`) for non-streaming requests from clients like Claude Code. Solved transparently at the proxy layer: all non-streaming requests targeting Anthropic are now sent with `stream: true` upstream, SSE events are aggregated into a complete Messages API response, and standard JSON is returned to the client. Covers both same-format passthrough (Anthropic → Anthropic) and cross-format conversion (e.g. OpenAI → Anthropic) paths
- **`config migrate` produces canonical v3 format**: Rewrote CLI `config migrate` to use the standard `load_config → ArgoConfig.from_dict → to_persistent_dict → _format_config_yaml` pipeline instead of raw dict manipulation. Migrated output now matches the format produced by a fresh `create_config()` init flow. Infers `argo_base_url` from legacy individual URL fields (`argo_url`, `argo_stream_url`, `argo_embedding_url`), drops stale/unknown fields (e.g. `mode`, `num_workers`), removes deprecated keys, and cleans up v3 configs with dirty derived fields. `to_persistent_dict()` now conditionally persists non-default optional fields (`use_legacy_argo`, `skip_url_validation`, `native_openai_base_url`, `native_anthropic_base_url`)
- **Banner version check for pre-release versions**: When the installed version is a pre-release (e.g. `3.0.0b7`), the startup banner now compares against the latest pre-release on PyPI instead of only the latest stable version. Previously it would incorrectly show "(Latest)" even when a newer pre-release was available. Extracted shared `get_pypi_versions()` async function and deduplicated version-fetching logic between the banner display and `update check` handler

## v3.0.0b8 (2026-03-27)

### Features

- **ARGO authentication warning detection**: Detects the upstream `AUTHENTICATION NOTICE FROM ARGO` warning injected into responses when a username is not registered, and returns a `403 Forbidden` error with code `argo_auth_warning` instead of forwarding the polluted content to the client. Covers all endpoint types (OpenAI, Anthropic, legacy ARGO) in both streaming and non-streaming modes
- **Startup username validation**: During initialization, argo-proxy now validates the configured username against the upstream ARGO API by making a test request. If the username is not registered, it rejects the input and re-prompts — invalid usernames can no longer slip through to runtime
- **Interactive init flow improvements**: First-time setup now prompts for the upstream base URL before username/port, validates upstream connectivity (GET `/v1/models`) immediately, and loops until a reachable URL is given. The verbose mode prompt is moved to the end, after all validations pass
- **Config YAML formatting**: Saved config files now use logical section grouping (Core settings, Upstream, Network & validation, Image processing) with comments and blank lines for readability

### Changed

- **Streaming passthrough buffering**: Passthrough streaming handlers (`native_openai`, `native_anthropic`, `dispatch`) now buffer initial chunks (up to 2 KB or the first complete SSE event) before committing to the streaming response, enabling early detection of upstream auth warnings
- **Added `argo_auth_warning` error code**: New error code added to `ResponseError` literal type for programmatic detection of ARGO authentication issues
- **Extended `validate_user_async()` transport utility**: New async function in `utils/transports.py` that validates a username by sending a lightweight chat request and inspecting the response for authentication warnings
- **Config persistence cleanup**: `save_config()` now uses `to_persistent_dict()` which excludes runtime-derived fields (`mode`, `native_openai_base_url`, `native_anthropic_base_url`). New configs are created with `config_version: "3"`. Config is saved to the user-specified path instead of always defaulting to `~/.config/argoproxy/config.yaml`
- **Removed tqdm progress bar from startup**: URL validation no longer shows a progress bar — replaced with a simple log message. The redundant mode display block at the end of `validate_config()` is also removed (already shown in the banner)
- **Refactored `config.py` into `config/` subpackage**: Split the ~1000-line monolithic config module into `model.py` (ArgoConfig dataclass), `io.py` (load/save/migrate), `validation.py` (user/port/URL checks), and `interactive.py` (user prompts and `create_config`)
- **Refactored `cli.py` into `cli/` subpackage**: Split the ~1050-line monolithic CLI module into `parser.py` (argparse construction), `display.py` (banner and version check), and `handlers.py` (subcommand handlers)

## v3.0.0b7 (2026-03-23)

### Fixed

- **Orphaned tool_calls cause 400 on strict upstreams**: When a tool call is interrupted (e.g. user cancels mid-execution in Claude Code), the `tool_calls` entry remains in conversation history without a matching `role: "tool"` response. OpenAI and Anthropic APIs strictly reject this. Now fixed via `fix_orphaned_tool_calls()` from llm-rosetta — applied in both passthrough and cross-format paths for **all three strict-pairing providers** (OpenAI Chat, OpenAI Responses, Anthropic) (#82)
- **Missing `user` field in cross-format requests**: Cross-format IR round-trips produce a fresh request body that drops the `user` field, causing upstream auth/tracking to lose the user identity. Now injected automatically in both streaming and non-streaming conversion paths
- **Google GenAI SDK auth via `x-goog-api-key` header**: The Google GenAI SDK (used by Gemini CLI) sends API keys via the `x-goog-api-key` header, which was not extracted by `_build_upstream_headers()`. Now supported alongside `Authorization: Bearer`, `x-api-key`, and `?key=` query parameter
- **aiohttp 3.12 startup crash**: `TCPConnector.__init__()` no longer accepts `tcp_nodelay` (removed upstream in aiohttp 3.12). Removed the parameter from `OptimizedHTTPSession`

### Changed

- **Bumped llm-rosetta to v0.2.5**: Picks up full-stack Google GenAI camelCase support, cross-format image passthrough fixes, tool_call_id reconciliation, `input_schema` type default for parameterless tools, and built-in tool handling ([Oaklight/llm-rosetta v0.2.4–v0.2.5](https://github.com/Oaklight/llm-rosetta/releases/tag/v0.2.5))
- **Refactored `dispatch.py`**: Merged 4 identical SSE formatters into 2, extracted `_write_sse_chunks()` / `_ensure_user_field()` helpers, defined `_STREAMING_HEADERS` constant, added `Callable` type hint to `_SSE_FORMATTERS`
- **Modernized typing imports**: Replaced `typing.List`, `Dict`, `Tuple`, `Set` with Python 3.10+ built-in generics via ruff UP006 (525 auto-fixes across 31 files); removed `typing_extensions.Literal` in favor of `typing.Literal`
- **Added ruff and ty configuration**: `pyproject.toml` now includes `[tool.ruff]` (target-version py310, select E/F/UP, ignore UP007/E501) and `[tool.ty]` (python-version 3.10, unresolved-import ignore) sections
- **Fixed 35 ty type-check diagnostics**: Corrected `AbstractResolver.resolve` override signature, narrowed Optional types with assert guards and cast(), added missing Union members to return type annotations, fixed `dict[str, str]` → `dict[str, Any]` for log entries
- **Cleaned up `performance.py`**: Removed `optimize_event_loop()` (no-op defaults), fake tqdm progress bar, `inspect.signature` feature check, CPU-based connection scaling; simplified to fixed defaults with env var overrides (-80 lines)

## v3.0.0b6 (2026-03-22)

### Changed

- **Bumped llm-rosetta to v0.2.3**: Picks up tool schema sanitization across all converters (#80), `$ref`/`$defs` resolution (#80), streaming tool call argument accumulation fixes (#81), and `sanitize_schema` extraction to shared base module (#66)
- **Updated `sanitize_schema` import path**: `dispatch.py` now imports `sanitize_schema` from `llm_rosetta.converters.base.tools` instead of `llm_rosetta.converters.openai_chat.tool_ops` (follows upstream refactoring in Oaklight/llm-rosetta#66)

## v3.0.0b5 (2026-03-22)

### Fixed

- **Same-format passthrough tool schema sanitization**: Added `_sanitize_tool_schemas()` to sanitize tool parameter schemas in the passthrough path (when `source_provider == target_provider`). Upstreams like Vertex AI reject unsupported JSON Schema keywords even in passthrough mode (#76)
- **Stream termination fallback**: Added fallback in `_convert_streaming()` — when the upstream stream ends without sending a `StreamEndEvent` trigger (empty-choices chunk), synthesize termination events (`message_delta`, `message_stop`) so the client receives a complete Anthropic SSE event sequence (#79)
- **Bumped llm-rosetta to v0.2.2**: Picks up Anthropic `content_block_stop` fix and upstream preflight chunk handling ([Oaklight/llm-rosetta#77](https://github.com/Oaklight/llm-rosetta/releases/tag/v0.2.2))

## v3.0.0b4 (2026-03-21)

Initial v3 beta release — complete architecture rewrite.

### Major Features

- **Universal API Gateway (llm-rosetta)**: Transformed argo-proxy from a single-format ARGO gateway proxy into a universal API translator. All 4 client API formats are now supported — users can talk to any upstream model using any client format:

    | Client Format | Endpoint |
    |---|---|
    | OpenAI Chat Completions | `POST /v1/chat/completions` |
    | OpenAI Responses API | `POST /v1/responses` |
    | Anthropic Messages | `POST /v1/messages` |
    | Google GenAI | `POST /v1beta/models/{model}:generateContent` |

- **Smart Upstream Routing**: Claude models are automatically routed to the native Anthropic endpoint (avoiding tool call leakage on OpenAI-compat), while all other models (GPT, Gemini) go to the native OpenAI Chat endpoint.

- **Same-Format Passthrough**: When the client format matches the upstream format, requests and responses are piped through without conversion for maximum performance and fidelity.

- **Cross-Format Conversion**: When formats differ (e.g., Anthropic client + GPT model, or OpenAI client + Claude model), [llm-rosetta](https://github.com/Oaklight/llm-rosetta) handles bidirectional conversion via its Intermediate Representation (IR), for both streaming and non-streaming requests.

### New Features

- **Universal Dispatch Module** (`endpoints/dispatch.py`): Central entry point for all API requests with model resolution, format detection, image preprocessing, auth header translation, and error handling.

- **Cross-Format Auth Header Translation**: Automatic conversion between `x-api-key` (Anthropic) and `Authorization: Bearer` (OpenAI) headers when routing across formats.

- **Flexible Model Name Resolution**: Enhanced `_model_lookup_candidates()` to accept all common model name formats:
    - Anthropic dash format: `claude-sonnet-4-6`
    - Argo dot format: `argo:claude-sonnet-4.6`
    - Internal IDs: `claudesonnet46`
    - Anthropic model IDs with dates: `claude-sonnet-4-6-20250514`

- **Native Upstream Model List**: Model registry now fetches from the native OpenAI `/v1/models` endpoint instead of the legacy ARGO models API.

- **CLI Subcommands**: Restructured CLI with hierarchical subcommands:
    - `argo-proxy serve` — start the server (default, backward compatible)
    - `argo-proxy config {edit,validate,show,migrate}` — manage configuration
    - `argo-proxy logs collect` — collect diagnostic logs
    - `argo-proxy update {check,install}` — check for and install updates from PyPI (supports `--pre` for pre-release)
    - `argo-proxy models` — list all available upstream models with their aliases, grouped by type (Chat/Embedding) and provider, with `--json` output support
    - `--no-banner` flag to suppress ASCII banner

- **Simplified Base URL Configuration**: Only `argo_base_url` is needed — `native_openai_base_url` and `native_anthropic_base_url` are automatically derived. Explicit overrides are still supported and trailing slashes are normalized.

- **Config Migration** (`argo-proxy config migrate`): Automatic migration of v1/v2 config files to v3 format with `.bak` backup.

- **Mode-Aware Config Display**: `argo-proxy config validate` and `config show` now display native endpoint URLs and `mode: universal` in v3 mode, or legacy ARGO gateway URLs in legacy mode.

- **Native Endpoint Connectivity Check**: URL validation at startup tests the native OpenAI `/v1/models` endpoint (GET) in universal mode, instead of the legacy ARGO chat/embedding POST endpoints.

### Breaking Changes

- **Native endpoints are now default**: `use_native_openai` and `use_native_anthropic` config keys are deprecated and ignored. Native upstream routing is always active.
- **Legacy mode is opt-in**: Use `--legacy-argo` flag or `use_legacy_argo: true` in config to enable the old ARGO gateway pipeline.
- **Removed `--native-openai` / `--native-anthropic` CLI flags**: No longer needed since native mode is the default.
- **Legacy endpoints moved to `_legacy/`**: `chat.py`, `completions.py`, `embed.py`, `responses.py`, `native_anthropic.py` relocated to `endpoints/_legacy/`.

### Deprecations

- `tool_calls/handler.py`, `tool_calls/output_handle.py` — replaced by llm-rosetta converters
- `types/chat_completion.py`, `types/completions.py`, `types/embedding.py`, `types/responses.py` — replaced by llm-rosetta IR types
- `tool_calls/converters.py` — removed entirely (unused)

### Dependencies

- Added `llm-rosetta` as a core dependency for cross-format conversion

### Documentation

- Comprehensive v3 documentation rewrite covering all pages
- New **CLI Tools Guide** with configuration instructions for Claude Code, Codex CLI, Aider, Gemini CLI, OpenCode, and generic SDK usage
- Updated endpoint docs with universal routing logic and all 4 API formats
- Rewrote CLI reference for subcommand-based interface
- Rewrote configuration guide for v3 format (`argo_base_url`, modes, migration)
- Simplified native passthrough pages with v3 notes pointing to new docs

## v2.8.9 (2026-03-21)

### Bug Fixes

- **Leaked Tool Parser JSON Literals**: Fixed `ast.literal_eval` failures when Claude emits JSON-style `false`/`true`/`null` instead of Python's `False`/`True`/`None` in leaked tool calls. Added word-boundary-aware regex repair strategy. ([#70](https://github.com/Oaklight/argo-proxy/pull/70), contributed by @mvictoras)

## v2.8.8.post1 (2026-03-07)

### Bug Fixes

- **Native Endpoint Model Passthrough**: Fixed model name resolution on native endpoints (`/v1/messages` and native OpenAI passthrough) incorrectly falling back to the default model (`gpt-4o`) when encountering unrecognized model names. Added `as_is` parameter to `resolve_model_name()` so that native passthrough endpoints forward the caller's original model name to the upstream API unchanged. ([#68](https://github.com/Oaklight/argo-proxy/pull/68), fixes [#67](https://github.com/Oaklight/argo-proxy/issues/67))

## v2.8.8 (2026-03-05)

### Bug Fixes

- **Native Anthropic Model Resolution**: Fixed model name resolution on the native Anthropic endpoint (`/v1/messages`) to resolve bare model names (e.g., `claude-4.6-sonnet`) the same way as all other endpoints. Previously, only `argo:`-prefixed names were resolved, causing bare names to be forwarded as-is to the upstream API, resulting in 400 errors.

### Features

- **Configurable Connection Test Timeout**: Added `connection_test_timeout` configuration option (default: 5 seconds) to control the per-URL timeout during startup connectivity validation. Previously hardcoded at 2 seconds, which was insufficient for high-latency connections such as layered SSH tunnels. Configurable via `config.yaml`.

## v2.8.7.post1 (2026-02-22)

### Bug Fixes

- **Unclosed aiohttp Connector**: Fixed `connector_owner` logic in `get_upstream_model_list_async()` and `validate_api_async()` that caused "Unclosed connector" warnings during startup. When no custom DNS resolver was provided, `connector_owner=False` was incorrectly set, preventing the auto-created `TCPConnector` from being closed with the session.

## v2.8.7 (2026-02-22)

### Features

- **Flexible Model Name Resolution**: Improve model name resolution flexibility - support slash separator, case-insensitive matching, and automatic `argo:` prefix handling ([#65](https://github.com/Oaklight/argo-proxy/pull/65), contributed by @keceli)
- **DNS Resolution Overrides** (@michel2323): Custom DNS resolver (`StaticOverrideResolver`) implementing `aiohttp.abc.AbstractResolver`, similar to `curl --resolve`. Maps specific `host:port` combinations to IP addresses, enabling access to Argo API through SSH tunnels while preserving TLS certificate validation. Configured via `resolve_overrides` in `config.yaml`.
- **Skip URL Validation** (@michel2323): New `skip_url_validation` config option (also via `SKIP_URL_VALIDATION` env var) to skip startup connectivity checks — useful for non-interactive environments (CI/CD, containers) where network may be unavailable.

### Refactoring

- **urllib → aiohttp Migration**: Migrated `validate_api_async` and `get_upstream_model_list` from synchronous `urllib.request` to native async `aiohttp.ClientSession`, with support for `resolve_overrides` parameter for custom DNS resolution.

### Documentation

- **Model Naming Guide**: Rewrite models page as naming scheme guide
- **CLI Docs Link**: Add model naming docs link to CLI startup prompt
- **DNS Resolution Overrides**: Added [DNS Resolution Overrides](https://argo-proxy.readthedocs.io/en/latest/usage/advanced/dns-resolution/) documentation page

### Bug Fixes

- **CLI Verbose Flag Override**: CLI `--verbose`/`--quiet` flags now properly override the `verbose` setting in `config.yaml` (#64)
- **Leaked tool parsing**: Replaced quote-aware brace counting with a more robust candidate-end-position + repair strategy approach for parsing leaked Claude tool calls. This handles edge cases with nested quotes, escaped characters, and malformed output more reliably. (Contributed by [n-getty](https://github.com/n-getty))

## v2.8.6 (2026-02-18)

### Features

- **Model List Refresh Endpoint**: Added `POST /refresh` endpoint to reload the model list from upstream without restarting the instance
    - Returns before/after model statistics for easy comparison
    - Useful for picking up newly added upstream models without downtime

## v2.8.5 (2026-02-15)

### Bug Fixes

- **Native Anthropic Tool Validation** (@caidao22): Fixed incorrect input format for tool validation on native Anthropic endpoint (#62)
    - Added `input_format` parameter to `handle_tools`/`handle_tools_native` to correctly parse tools arriving via the native Anthropic endpoint
    - Allowed `ToolChoice._handle_anthropic` to accept string shorthand values (`auto`, `any`, `none`)
    - Short-circuit tool conversion when input format already matches target model type

## v2.8.4 (2026-02-14)

### Refactor

- **Base URL Consolidation**: Refactored URL configuration to use a single `argo_base_url` as the root for all endpoint URLs
    - Introduced `argo_base_url` configuration field — all endpoint URLs (chat, stream, embed, models, native OpenAI) are now derived from this single base URL
    - Simplified `_argo_dev_base` and `_argo_prod_base` to root URLs (e.g., `https://apps-dev.inside.anl.gov/argoapi`) instead of full API paths
    - Individual endpoint URLs (`argo_url`, `argo_stream_url`, etc.) can still override the derived values for backward compatibility
    - Added `config_version` field for tracking configuration format; legacy configs without this field will log a migration hint
    - Updated `config.sample.yaml` with the new recommended configuration format

### Features

- **Native Anthropic Passthrough Mode**: Added `--native-anthropic` CLI flag and `use_native_anthropic` configuration option for Anthropic-compatible API passthrough, similar to the existing native OpenAI passthrough
    - Exposes `/v1/messages` endpoint for direct Anthropic API compatibility
    - Supports both streaming and non-streaming message requests
    - Added `native_anthropic_base_url` configuration for customizing the upstream Anthropic endpoint
    - URL is derived from `argo_base_url` by default for consistency with other endpoints

### Improvements

- **Examples Directory Reorganization**: Restructured examples into `anthropic/`, `openai/`, and `argo/` subdirectories
    - Each provider directory contains `sdk_based/` and `rest_based/` subdirectories
    - Added Anthropic function calling examples (SDK and REST)
    - Added Anthropic image comprehension examples with base64 encoding
    - Unified API key handling across all examples using `API_KEY` environment variable

## v2.8.3 (2026-02-08)

### Features

- **Improved Claude Leaked Tool Call Parsing**: Added new robust parser for extracting leaked tool calls from Claude model responses
    - New `leaked_tool_parser` module with quote-aware brace counting for accurate dict boundary detection
    - Handle Anthropic content array format (mixed text+tool_use blocks)
    - Extract ALL leaked tool calls, not just the first one
    - Proper handling of braces inside strings (code snippets)
    - Support for escaped quotes in tool arguments
    - Added comprehensive unit tests (24 tests)

- **Attack Logging Module**: Added dedicated security logging for malicious HTTP requests
    - Create `attack_logger.py` module for security logging
    - Log concise warning messages with attack type and source IP
    - Save detailed attack logs to `{config_dir}/attack_logs/` directory
    - Classify attacks: struts2_ognl, directory_traversal, ssti_probe, etc.
    - Store logs as compressed JSONL files organized by date

### Bug Fixes

- **Streaming UTF-8 Handling**: Fixed incomplete UTF-8 sequences in streaming responses
    - Add `StreamDecoder` utility class to safely decode UTF-8 byte streams where multi-byte characters may be split across network packets
    - Update chat, completions, and responses endpoints to use StreamDecoder
    - Fixes intermittent `ValueError: 'utf-8' codec can't decode byte` errors

## v2.8.2 (2026-01-31)

### Refactor

- **Logging System Overhaul**: Replaced loguru with standard library logging for better compatibility; centralized request logging utilities with improved formatting and log levels

### Bug Fixes

- **Large Image Payload Support**: Increased aiohttp client_max_size to 100MB to handle large image uploads

- **Token Counting Accuracy** (@Neil Getty): Fixed missing token counts for tool-related content
    - Added token counting for `tool_calls` and `tools` definitions
    - Improved recursive text extraction for nested content
    - Fixed `count_tokens` to handle None values gracefully

- **Claude Max Tokens Fix**: Fixed 500 upstream errors caused by excessive max_tokens in non-streaming tool call requests
    - Enforced max_tokens limit for Claude models to prevent issues with clients (like OpenCode) requesting 32k+ tokens with large tool definitions

### Improvements

- Centralized pseudo_stream handling and improved logging consistency across endpoints
- Improved upstream error handling across all endpoints with better error messages and recovery

## v2.8.1 (2026-01-24)

### Features

- **Leaked Tool Call Detection and Collection**: Added comprehensive leaked tool call debugging features
  - Added `--enable-leaked-tool-fix` CLI flag to enable AST-based leaked tool call detection and automatic fixing
  - Added `--collect-leaked-logs` CLI flag to collect all leaked tool call logs into timestamped tar.gz archive
  - Implemented automatic log directory management with compression when exceeding 50MB threshold
  - Enhanced ToolInterceptor to support request data logging and conditional leaked tool fixing
  - Added comprehensive logging and user guidance for sharing collected logs with maintainers

- **Streaming Completions Support**: Added full streaming support for legacy completions endpoint
  - Implemented pseudo-streaming and real streaming handlers for completions endpoint
  - Added usage chunk generation for completions API type
  - Integrated token counting for accurate usage reporting in streaming mode
  - Refactored transform functions to support both sync and async OpenAI compatibility

- **Streaming Usage Stats** (@Neil Getty): Implemented streaming usage statistics for pseudo stream responses in chat completions endpoint
  - Accumulate total response content during pseudo chunk generation
  - Calculate completion tokens using `count_tokens_async` function
  - Send usage statistics chunk at end of stream with prompt/completion/total tokens
  - Maintain compatibility with existing streaming infrastructure using SSE

### Bug Fixes

- **Consistent Chunk IDs**: Ensured consistent chunk IDs across streaming responses
  - Added chunk_id parameter to transform_chat_completions_streaming_async function
  - Generated shared ID for all chunks in a stream to maintain consistency
  - Passed shared chunk_id to all streaming chunks including tool calls and usage
  - Ensured only first chunk gets role: assistant by tracking is_first_chunk state

- **Role Field Handling**: Fixed None value handling for role field in chat completion types
  - Made role field optional to prevent validation errors when None is provided
  - Maintained default value of "assistant" for backward compatibility

- **First Chunk Handling**: Improved first chunk handling in streaming responses
  - Added is_first_chunk parameter to include assistant role in initial delta
  - Fixed tool calls handling in streaming transformation
  - Collected total response content for accurate token counting

- **Claude Tool Calls** (@Neil Getty): Fixed tool calls handling in pseudo stream responses
  - Set `finish_reason` to "tool_calls" when tool calls are present
  - Added robust parsing for leaked tool calls in Claude text content using `ast.literal_eval`
  - Implemented balanced dictionary detection to extract tool calls from text
  - Clean up text content by removing leaked tool call strings

### Refactor

- **Usage Counting**: Unified usage calculation logic across all endpoints
  - Extracted usage calculation logic into shared `calculate_completion_tokens_async` function
  - Created unified `create_usage` factory function for different API types
  - Implemented `generate_usage_chunk` for streaming responses
  - Removed duplicate token counting code from chat, completions, embed, and responses endpoints
  - Standardized usage object creation across all API formats (chat_completion, completion, response, embedding)

- **Development Scripts**: Migrated OpenAI example scripts to use environment variables
  - Updated scripts to load environment variables from .env files
  - Improved configuration management and flexibility

### Enhancements

- **Tool Call Examples**: Enhanced OpenAI chat completions example with tool call support
  - Added TOOL_CALL environment variable to switch between regular chat and tool call modes
  - Implemented tool call payload with get_stock_price function example
  - Maintained backward compatibility with existing message-based chat functionality

- **Test Results**: Added OpenAI function call streaming test results for comparison
  - Created new test result files for OpenAI function call chunk streaming
  - Enabled comparison between OpenAI and local streaming implementations

### Maintenance

- **Documentation Cleanup**: Removed legacy Sphinx and ReadTheDocs documentation system
  - Completely removed the legacy documentation system built with Sphinx and configured for ReadTheDocs
  - Deleted entire `docs/` directory including Sphinx configuration, source files, and build scripts
  - Simplified build process and overall maintenance

- **Project Documentation**: Updated project name and badge formatting in README

## v2.8.0 (2026-01-02)

### Major Features

- **Gemini Native Function Calling**: Added full native function calling support for Google Gemini models
- **Model Statistics Enhancement**: Enhanced model registry with detailed family breakdown and alias counting
- **Comprehensive Test Suite**: Added complete test coverage for all API endpoints

### New Features

- **Gemini Function Calling**:

    - Native tool calling support for Google/Gemini models in chat completions
    - Google-specific tool call format conversion and processing
    - Parallel to sequential tool call conversion for Gemini API compatibility
    - Tool call ID generation and argument serialization for Google format
    - Enhanced tool choice handling with proper string/dict conversion

- **Model Registry Enhancements**:

    - Added `get_model_stats()` method for detailed model statistics
    - Model family classification (OpenAI, Anthropic, Google, unknown)
    - Comprehensive model registry display with family breakdown
    - Chat and embedding model statistics with alias counts
    - Tree-structured logging for better readability

- **Testing Infrastructure**:
    - Complete test suite for chat completions, embeddings, and function calling
    - Tests for streaming, temperature control, conversation context
    - Function calling tests for single and multiple tool scenarios
    - Legacy completions endpoint testing with various parameters

### Bug Fixes

- **Embedding Index**: Fixed embedding index assignment to use sequential numbering instead of hardcoded 0

### Improvements

- **Tool Call Processing**: Enhanced tool call conversion between OpenAI and Google formats
- **Development Scripts**: Added comprehensive Gemini function calling examples and test scripts
- **Model Display**: Improved startup model registry display with family breakdown

## v2.7.10 (2026-01-02)

### Major Features

- **Gemini Native Function Calling**: Added full native function calling support for Google Gemini models
- **Model Statistics Enhancement**: Enhanced model registry with detailed family breakdown and alias counting
- **Comprehensive Test Suite**: Added complete test coverage for all API endpoints

### New Features

- **Gemini Function Calling**:

    - Native tool calling support for Google/Gemini models in chat completions
    - Google-specific tool call format conversion and processing
    - Parallel to sequential tool call conversion for Gemini API compatibility
    - Tool call ID generation and argument serialization for Google format
    - Enhanced tool choice handling with proper string/dict conversion

- **Model Registry Enhancements**:

    - Added `get_model_stats()` method for detailed model statistics
    - Model family classification (OpenAI, Anthropic, Google, unknown)
    - Comprehensive model registry display with family breakdown
    - Chat and embedding model statistics with alias counts
    - Tree-structured logging for better readability

- **Testing Infrastructure**:
    - Complete test suite for chat completions, embeddings, and function calling
    - Tests for streaming, temperature control, conversation context
    - Function calling tests for single and multiple tool scenarios
    - Legacy completions endpoint testing with various parameters

### Bug Fixes

- **Model Fetching**: Enhanced error handling in model fetching with detailed logging for HTTP, URL, JSON, and unknown errors
- **API Compatibility**: Added support for both old and new API formats in Model class with backward compatibility
- **Network Reliability**: Added request timeouts and improved error recovery with fallback to built-in model list
- **Embedding Index**: Fixed embedding index assignment to use sequential numbering instead of hardcoded 0

### Improvements

- **Error Handling**: Improved error logging with detailed HTTP, URL, and JSON error messages
- **API Format Detection**: Added automatic detection and logging of API format versions
- **Tool Call Processing**: Enhanced tool call conversion between OpenAI and Google formats
- **Development Scripts**: Added comprehensive Gemini function calling examples and test scripts

## v2.7.9 (2025-12-14)

### Major Features

- **Native OpenAI Passthrough Mode**: Added complete native OpenAI endpoint passthrough functionality
- **Dynamic Version Configuration**: Updated build system to use dynamic version configuration from `argoproxy.__version__`
- **Enhanced Startup Experience**: Added ASCII banner with version information and styled model registry display

### New Features

- **Native OpenAI Mode**:

    - Added `use_native_openai` configuration flag and `--native-openai` CLI option
    - Implemented pure passthrough for chat/completions, completions, and embeddings endpoints
    - Added support for model name mapping even in native mode (argo:gpt-4o aliases)
    - Integrated tool call processing for native OpenAI mode with model family detection
    - Added image processing support with automatic URL download and base64 conversion

- **Startup Enhancements**:

    - Added ASCII banner for Argo Proxy with version information
    - Implemented styled model registry display with model count
    - Added startup banner with update availability check
    - Enhanced configuration mode logging with visual indicators

- **Tool Call Improvements**:
    - Added streaming response handling with data prefix parsing in function calling examples
    - Implemented [DONE] message detection for stream termination
    - Added environment variable support for stream control in examples

### Improvements

- **Configuration Management**:

    - Added native OpenAI mode warnings and status indicators
    - Improved mode logging logic to properly handle native vs standard mode
    - Enhanced logging consistency across modules with standardized formatting

- **Documentation**:

    - Added comprehensive native OpenAI passthrough documentation
    - Updated feature comparison tables and endpoint availability information
    - Added tool call processing documentation with model compatibility matrix
    - Included troubleshooting section with common error messages and solutions

- **Build System**:
    - Migrated from static to dynamic version configuration
    - Updated pyproject.toml to read version from `argoproxy.__version__` attribute

### Bug Fixes

- Fixed streaming response handling in function calling chat examples
- Improved error handling for non-JSON data in streams
- Enhanced model name resolution formatting for better readability

## v2.7.8 (2025-11-07)

### New Features

- **Image Processing Enhancement**: Added support for JPEG (JPG), PNG, WebP, and GIF image formats
- **Image URL Conversion**: Implemented automatic conversion from image URLs to base64
- **Image Payload Control**: Added `enable_payload_control` configuration option for image payload size and concurrency control
- **Image Format Validation**: Added image format and magic bytes validation functionality

### Improvements

- Improved image processing payload size handling logic
- Optimized image content type preservation in payload
- Enhanced base64 truncation logging functionality
- Added Pillow dependency for image processing support

### Documentation Updates

- Added vision and image input usage examples
- Added comprehensive base64 usage documentation and examples
- Updated version requirement documentation

## v2.7.8a0 (2025-11-05)

### Pre-release Version

- Pre-release testing version for image processing functionality

## v2.7.7 (2025-07-23)

### Major Features

- **Tool Call System Refactor**: Complete rewrite of tool call processing system with multi-provider compatibility
- **Native Tool Support**: Enabled native tool processing for OpenAI and Anthropic models
- **Cross-Provider Conversion**: Implemented tool call format conversion between OpenAI and Anthropic
- **Model-Specific Prompts**: Implemented specific prompt skeletons for different model families

### New Features

- Added `pseudo_stream_override` flag for streaming response control
- Implemented username passthrough functionality
- Added message content normalization logic
- Added user message checks for Gemini and Claude models

### Improvements

- Enhanced tool call serialization handling
- Improved model determination logic
- Optimized input validation and error handling
- Updated streaming mode descriptions and tool call documentation

## v2.7.6 (2025-07-17)

### New Features

- **Real Streaming**: Added `real_stream` functionality for testing
- **Configuration Enhancement**: Added configuration diff display functionality
- **Base URL Configuration**: Support for base URL configuration
- **Network Troubleshooting**: Added network troubleshooting guidance

### Improvements

- Renamed `fake_stream` to `pseudo_stream` for better clarity
- Enhanced server shutdown process
- Improved error handling and streaming logic
- Optimized configuration loading and URL construction

### Documentation Updates

- Updated tool call documentation
- Improved toolregistry documentation with examples and integration instructions
- Added detailed documentation links

## v2.7.5 (2025-07-14)

### Major Features

- **Function Calling Support**: Added function calling functionality to chat completion endpoint
- **Tool Call Framework**: Implemented complete tool call processing framework
- **Multi-Model Support**: Extended support for more chat and embedding models

### Technical Improvements

- Added Pydantic models for response structuring
- Implemented OpenAI compatibility enhancements including usage tracking
- Refactored type system with new completion and usage types

## v2.7.5.post1 (2025-07-14)

### Patch Version

- Fixed minor issues related to function calling
- Improved dependency management

## v2.7.5.alpha1 (2025-06-30)

### Pre-release Version

- Alpha testing version for function calling functionality

## v2.7.4.post2 (2025-06-30)

### Patch Version

- **Tool Call Feature Development**: Extensive tool call related feature development and refactoring
- Added function calling examples and tool choice types
- Implemented tool call templates and conversion functionality
- Enhanced streaming tool call support
- Improved tool call processing logic

## v2.7.4.post1 (2025-06-28)

### Patch Version

- Added model availability timeout input functionality
- Improved URL validation efficiency
- Simplified model availability handling
- Enhanced configuration loading verbosity control
- Temporarily disabled streamchat endpoint

## v2.7.4 (2025-06-27)

### Improvements

- Optimized streaming processing
- Enhanced error handling mechanisms
- Improved configuration management

## v2.7.3 (2025-06-26)

### New Features

- Added multi-entry processing support
- Improved message separation logic
- Added message deduplication and merging functionality

## v2.7.2.post1 (2025-06-26)

### Patch Version

- Removed model-specific transformation functionality
- Simplified chat processing logic

## v2.7.2 (2025-06-25)

### Improvements

- Updated Claude model configuration
- Optimized model pattern matching
- Improved version handling and help formatting

## v2.7.1.post1 (2025-06-20)

### Patch Version

- Fixed embedding endpoint input processing issues
- Improved request data preparation logic

## v2.7.0.post2 (2025-06-17)

### Patch Version

- Fixed case-sensitive header comparison issue in streaming responses
- Updated logger configuration

## v2.7.0.post1 (2025-06-16)

### Patch Version

- Added version check functionality
- Enhanced version endpoint response
- Simplified install command message

## v2.7.0 (2025-06-15)

### Architecture Refactor

- **Response Endpoint**: Added brand new `/v1/responses` endpoint
- **SSE Support**: Implemented Server-Sent Events (SSE) streaming
- **Event-Driven**: Introduced event-driven response workflow
- **Type System**: Complete refactor of type system using Pydantic models

### New Features

- Added streaming and non-streaming response conversion functions
- Implemented response text completion event handling
- Added multiple OpenAI client example scripts

### Improvements

- Optimized import statement organization
- Enhanced endpoint compatibility
- Improved error handling and logging

## v2.6.1 (2025-06-11)

### Improvements

- Updated configuration file search order and usage details
- Improved CLI usage and option formatting
- Removed num-worker parameter

## v2.6.0 (2025-06-11)

### Server Migration

- **Sanic to aiohttp Migration**: Complete rewrite of server implementation
- **Logging System**: Replaced Sanic logger with loguru
- **Async Processing**: Improved async JSON parsing and request handling

### Configuration Improvements

- Removed timeout logic, simplified configuration
- Updated configuration validation and path handling
- Improved API validation workflow

### Documentation Updates

- Updated installation instructions
- Added version badges and installation guide
- Improved timeout documentation and examples

## v2.5.1 (2025-05-30)

### Improvements

- Updated documentation and configuration file search order
- Improved CLI usage instructions
- Optimized editor selection logic

## v2.5.1-alpha (2025-05-30)

### Pre-release Version

- Alpha testing version for v2.5.1

## v2.5.0 (2025-05-29)

### CLI Refactor

- **New CLI Interface**: Replaced Sanic server with CLI interface
- **Configuration Management**: Enhanced configuration handling and validation
- **Editor Integration**: Added `--edit` option to open configuration in editor

### Package Management

- Added Makefile for package management
- Updated pyproject.toml configuration

### Feature Enhancements

- Added version command
- Improved type hints and error handling
- Enhanced log level configuration

## v2.4 (2025-04-20)

### Model Support

- Updated model aliases and Argo tags
- Simplified model availability import and usage
- Unified model mapping architecture

### Improvements

- Enhanced model parsing logic
- Improved model handling compatibility
- Added unified prompt token calculation

## v2.3 (2025-04-06)

### Embedding Feature Enhancement

- Improved OpenAI response structure
- Enhanced prompt data processing
- Added OpenAI compatible response conversion
- Added token counting functionality
- Added tiktoken encoding and tools

## v2.2 (2025-03-31)

### New Features

- Added scripts for syncing GitHub and GitLab repositories
- Centralized API validation logic
- Added API validation functions

### Improvements

- Prevented invalid username selection
- Improved setup instructions and configuration tables
- Enhanced documentation structure and content

## v2.1 (2025-03-12)

### Improvements

- Replaced problematic prompts with new complete stream implementation
- Disabled system message to user message conversion
- Added Argo stream URL to configuration
- Updated models and simplified chat examples

## v2.0 (2025-03-11)

### Major Refactor

- **Project Structure**: Reorganized entire project directory structure
- **Modularization**: Split functionality into independent endpoint modules
- **Type Safety**: Added comprehensive type hints

### New Features

- Added embedding endpoint support
- Implemented model availability checking
- Added status and extra endpoints

### Compatibility

- Improved OpenAI API compatibility
- Added model remapping functionality
- Enhanced error handling

## v1.1 (2025-01-06)

### Improvements

- Added model-specific system message conversion functionality
- Improved o1-preview model handling

## v1.0 (2024-12-29)

### Initial Stable Version

- **Basic Proxy Functionality**: Implemented basic ARGO API proxy
- **OpenAI Compatibility**: Provided OpenAI API format compatibility
- **Chat Completion**: Supported chat completion endpoint
- **Streaming**: Basic streaming response support

### Core Features

- Configuration file support
- Basic logging
- Example scripts
- Model remapping and default settings

## v0.3.0 (2024-12-12)

### Modularization Improvements

- **Completion Module**: Added completion module and enhanced chat routing
- **Compatibility**: Ensured prompts are in list format in proxy_request
- **Refactor**: Separated chat and embedding modules, updated configuration

## v0.2.0 (2024-12-02)

### Infrastructure Improvements

- **API Testing**: Tested API URLs and increased Gunicorn timeout
- **Bug Fixes**: Fixed cases where prompts are lists
- **Docker Optimization**: Optimized Dockerfile, enhanced configuration
- **Configuration Files**: Updated Dockerfile, added config.yaml, modified app.py

## v0.1.0 (2024-12-01)

### Initial Release

- **Response Handling Refactor**: Refactored response handling and added prompt token counting
- **OpenAI Compatibility**: Enhanced proxy OpenAI compatibility and error handling
- **Basic Endpoints**: Added new endpoints
- **Project Initialization**: Initialized gitignore, local build support
- **Core Functionality**: Argo proxy ready, requires VPN connection

---

## Version Notes

- **Major Version**: Indicates major architectural changes or incompatible updates
- **Minor Version**: Indicates new feature additions or important improvements
- **Patch Version**: Indicates bug fixes and minor improvements
- **Suffix Versions**: Such as `.post1`, `.alpha1` etc. indicate patches or pre-release versions

## Contributing

If you find any issues or have suggestions for improvements, please [submit an issue](https://github.com/Oaklight/argo-proxy/issues/new) or [submit a pull request](https://github.com/Oaklight/argo-proxy/compare).
