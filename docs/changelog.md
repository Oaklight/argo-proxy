# Changelog

This page records the major version changes and important feature updates of the Argo Proxy project.

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
