# Vision and Image Input

Argo-proxy provides comprehensive support for vision models and image input processing, enabling you to send images to AI models that support visual understanding.

## Table of Contents

- [Overview](#overview)
- [Supported Image Formats](#supported-image-formats)
- [Key Features](#key-features)
- [Basic Usage Examples](#basic-usage-examples)
  - [Image Chat with URLs](#image-chat-with-urls)
  - [OpenAI Client Usage](#openai-client-usage)
  - [Multiple Images](#multiple-images)
- [Configuration](#configuration)
  - [Image Processing Settings](#image-processing-settings)
  - [Payload Compression](#payload-compression)
    - [How Payload Compression Works](#how-payload-compression-works)
    - [Configuration Options](#configuration-options)
    - [Enabling Payload Compression](#enabling-payload-compression)
    - [When to Use Payload Compression](#when-to-use-payload-compression)
    - [Quality vs Size Trade-offs](#quality-vs-size-trade-offs)
  - [Content Type Handling](#content-type-handling)
- [Examples](#examples)

## Overview

The vision feature automatically processes image inputs in chat completions, supporting both base64-encoded images and HTTP/HTTPS image URLs. When you provide image URLs, argo-proxy automatically downloads and converts them to base64 format for compatibility with AI models.

## Supported Image Formats

- **PNG** (.png)
- **JPEG** (.jpg, .jpeg)
- **WebP** (.webp)
- **GIF** (.gif, non-animated only)

## Key Features

- Automatic URL processing with parallel downloads
- Image format validation and size limits
- Memory efficient processing without temporary files
- Clean logging with base64 content truncation
- Intelligent payload compression with format conversion
- Automatic content type correction for processed images

## Basic Usage Examples

### Image Chat with URLs

Using direct HTTP/HTTPS URLs (automatically processed):

```python
import requests

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer your_anl_username"},
    json={
        "model": "argo:gpt-4.1-nano",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://example.com/image.jpg"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }
)
```

### OpenAI Client Usage

```python
from openai import OpenAI

client = OpenAI(
    api_key="your_anl_username",
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="argo:gpt-4.1-nano",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "https://example.com/image.jpg"
                    }
                }
            ]
        }
    ],
    max_tokens=300
)
```

### Multiple Images

```python
response = client.chat.completions.create(
    model="argo:gpt-4.1-nano",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Compare these images:"},
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image1.jpg"}
                },
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/image2.jpg"}
                }
            ]
        }
    ],
    max_tokens=500
)
```

## Configuration

### Image Processing Settings

Configure image processing in your config file:

```yaml
# config.yaml
enable_payload_control: false # Enable automatic payload size control
max_payload_size: 20 # MB default (total for all images)
image_timeout: 30 # seconds
concurrent_downloads: 10 # parallel downloads
```

### Payload Compression

Argo-proxy includes intelligent payload compression to ensure compatibility with AI models that have strict size limits (like Claude models). When enabled, it automatically reduces image quality and converts formats to stay within payload limits.

#### How Payload Compression Works

1. **Size Detection**: Calculates total payload size of all images in a request
2. **Automatic Compression**: If payload exceeds the limit, reduces image quality proportionally
3. **Format Conversion**: Converts images to more efficient formats:
   - PNG → JPEG (with transparency handling)
   - GIF → JPEG
   - WebP → WebP (quality reduced)
   - JPEG → JPEG (quality reduced)
4. **Content Type Correction**: Automatically updates MIME types when formats are converted

#### Configuration Options

| Setting                  | Default | Description                                     |
| ------------------------ | ------- | ----------------------------------------------- |
| `enable_payload_control` | `false` | Enable/disable automatic payload compression    |
| `max_payload_size`       | `20`    | Maximum total payload size in MB for all images |
| `image_timeout`          | `30`    | Timeout in seconds for downloading images       |
| `concurrent_downloads`   | `10`    | Maximum parallel image downloads                |

#### Enabling Payload Compression

To enable payload compression, set `enable_payload_control: true` in your config:

```yaml
# config.yaml
enable_payload_control: true
max_payload_size: 15 # Reduce to 15MB for stricter limits
```

#### When to Use Payload Compression

- **Large Images**: When working with high-resolution images. In some case, a single image could take up to more than 20 MB.
- **Multiple Images**: When sending multiple images in a single request. All upstream providers have number of images limit and payload total size limit in single request.
- **Network Constraints**: When bandwidth is limited

#### Quality vs Size Trade-offs

The compression algorithm intelligently balances quality and size:

- **JPEG Quality**: Ranges from 85% (minimal compression) to 15% (maximum compression)
- **PNG Conversion**: PNGs with transparency are converted to JPEG with white backgrounds
- **Progressive Compression**: Quality is reduced proportionally based on how much the payload exceeds the limit

### Content Type Handling

**Important**: Argo-proxy automatically corrects content types when images are converted during compression. This fixes compatibility issues with models like Claude that strictly validate image format headers.

- Original PNG with `image/png` → Converted to JPEG with `image/jpeg`
- Original GIF with `image/gif` → Converted to JPEG with `image/jpeg`
- JPEG and WebP maintain their original content types unless converted

## Examples

Complete working examples are available in the repository:

- `examples/raw_requests/image_chat_base64.py` - Basic image chat with base64
- `examples/raw_requests/image_chat_direct_urls.py` - Image chat with URLs
- `examples/openai_client/image_chat_base64.py` - OpenAI client with base64
- `examples/openai_client/image_chat_direct_urls.py` - OpenAI client with URLs
- `examples/openai_client/image_chat_huge_image.py` - OpenAI client with a very large image (> 20MB)

For more advanced usage and troubleshooting, see the [Examples](../examples/index.md) section.
