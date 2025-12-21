# Changelog

This page records the major version changes and important feature updates of the Argo Proxy project.

## v2.7.10 (2025-12-21)

### Bug Fixes

- **Model Fetching**: Enhanced error handling in model fetching with detailed logging for HTTP, URL, JSON, and unknown errors
- **API Compatibility**: Added support for both old and new API formats in Model class with backward compatibility
- **Network Reliability**: Added request timeouts and improved error recovery with fallback to built-in model list

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
