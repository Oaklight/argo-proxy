# Vision and Image Input

Argo-proxy provides comprehensive support for vision models and image input processing, enabling you to send images to AI models that support visual understanding.

```note
This feature is only available in version 2.7.8 and above.
```

## Table of Contents

- [Overview](#overview)
- [Supported Image Formats](#supported-image-formats)
- [Key Features](#key-features)
- [Basic Usage Examples](#basic-usage-examples)
  - [Image Chat with URLs](#image-chat-with-urls)
  - [Image Chat with Base64](#image-chat-with-base64)
  - [OpenAI Client Usage](#openai-client-usage)
  - [Multiple Images](#multiple-images)
- [Base64 Usage](#base64-usage)
  - [When to Use Base64](#when-to-use-base64)
  - [Base64 Data URL Format](#base64-data-url-format)
  - [Best Practices for Base64](#best-practices-for-base64)
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

The vision feature provides comprehensive support for image inputs in chat completions, supporting both base64-encoded images and HTTP/HTTPS image URLs. You can:

- **Use HTTP/HTTPS URLs**: Argo-proxy automatically downloads and converts them to base64 format for compatibility with AI models
- **Use Base64 Data URLs**: Directly provide base64-encoded images using the standard `data:image/type;base64,data` format
- **Mix Both Formats**: Combine URL and base64 images in the same request

This flexibility allows you to work with both remote images and local files seamlessly, with automatic format handling and optimization.

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

### Image Chat with Base64

For local images or when you need direct control over image data, use base64 encoding:

```python
import base64
import mimetypes
import requests

def file_to_data_url(file_path: str) -> str:
    """Convert a local image file to a data URL with base64 encoding."""
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    with open(file_path, "rb") as f:
        base64_data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{base64_data}"

# Convert local image to base64 data URL
image_data_url = file_to_data_url("path/to/your/image.jpg")

response = requests.post(
    "http://localhost:8000/v1/chat/completions",
    headers={"Authorization": "Bearer your_anl_username"},
    json={
        "model": "argo:gpt-4.1-nano",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
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

#### With URLs

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

#### With Base64

```python
import base64
import mimetypes
from openai import OpenAI

def file_to_data_url(file_path: str) -> str:
    """Convert a local image file to a data URL with base64 encoding."""
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    with open(file_path, "rb") as f:
        base64_data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{base64_data}"

client = OpenAI(
    api_key="your_anl_username",
    base_url="http://localhost:8000/v1"
)

# Convert local image to base64
image_data_url = file_to_data_url("path/to/your/image.jpg")

response = client.chat.completions.create(
    model="argo:gpt-4.1-nano",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analyze this image"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data_url
                    }
                }
            ]
        }
    ],
    max_tokens=300
)
```

### Multiple Images

#### With URLs

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

#### With Base64

```python
import base64
import mimetypes
from pathlib import Path

def file_to_data_url(file_path: str) -> str:
    """Convert a local image file to a data URL with base64 encoding."""
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"

    with open(file_path, "rb") as f:
        base64_data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{base64_data}"

# Convert multiple local images
image_paths = ["image1.jpg", "image2.jpg"]
image_data_urls = [file_to_data_url(path) for path in image_paths]

response = client.chat.completions.create(
    model="argo:gpt-4.1-nano",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Compare these images:"},
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_urls[0]}
                },
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_urls[1]}
                }
            ]
        }
    ],
    max_tokens=500
)
```

## Base64 Usage

### When to Use Base64

Base64 encoding is ideal for:

- **Local Images**: When working with images stored locally on your system
- **Security**: When you don't want to expose image URLs publicly
- **Control**: When you need precise control over image data and processing
- **Offline Processing**: When internet connectivity is limited or unreliable
- **Privacy**: When images contain sensitive information that shouldn't be transmitted via URLs

### Base64 Data URL Format

Argo-proxy supports the standard data URL format for base64-encoded images:

```
data:[<mediatype>][;base64],<data>
```

Examples:

- `data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD...`
- `data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB...`
- `data:image/webp;base64,UklGRiIAAABXRUJQVlA4IBYAAAAw...`

### Best Practices for Base64

#### 1. Proper MIME Type Detection

```python
import mimetypes

def get_image_mime_type(file_path: str) -> str:
    """Get the correct MIME type for an image file."""
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"
```

Some models could still process the base64 encoded image data even if `mime_type` is fixed to `jpeg`. We encourage you to carefully explore and fully test out before making production requests.

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

Some upstream providers have payload size limits. For example, Anthropic's Claude models have a 30MB limit and OpenAI has 50MB in their public facing API service. It's not clear what's the maximum payload size for Argo's OpenAI, Anthropic, and Google models. If you happen to find out, please email me and Matthew Dearing.

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
