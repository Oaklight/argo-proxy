"""
Logging utilities for argo-proxy.

This module provides utilities for logging request/response data in a clean,
configurable manner using Python's standard logging library with colorized output.
"""

import copy
import json
import logging
import sys
from typing import Any, Dict, List, Optional


# ANSI color codes for terminal output
class Colors:
    """ANSI color codes for terminal colorization."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright foreground colors
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


# Level-specific colors (matching loguru style)
LEVEL_COLORS = {
    logging.DEBUG: Colors.BLUE,
    logging.INFO: Colors.BRIGHT_WHITE,
    logging.WARNING: Colors.YELLOW,
    logging.ERROR: Colors.RED,
    logging.CRITICAL: Colors.BRIGHT_RED + Colors.BOLD,
}

# Level name colors (for the level indicator)
LEVEL_NAME_COLORS = {
    logging.DEBUG: Colors.CYAN,
    logging.INFO: Colors.GREEN,
    logging.WARNING: Colors.YELLOW,
    logging.ERROR: Colors.RED,
    logging.CRITICAL: Colors.BRIGHT_RED + Colors.BOLD,
}

# Level name formatting (padded for alignment, matching loguru)
LEVEL_NAMES = {
    logging.DEBUG: "DEBUG   ",
    logging.INFO: "INFO    ",
    logging.WARNING: "WARNING ",
    logging.ERROR: "ERROR   ",
    logging.CRITICAL: "CRITICAL",
}


def _supports_color() -> bool:
    """Check if the terminal supports color output."""
    # Check for NO_COLOR environment variable (https://no-color.org/)
    import os

    if os.environ.get("NO_COLOR"):
        return False

    # Check if stdout is a TTY
    if not hasattr(sys.stdout, "isatty"):
        return False

    if not sys.stdout.isatty():
        return False

    # Check for TERM environment variable
    term = os.environ.get("TERM", "")
    if term == "dumb":
        return False

    return True


class ColoredFormatter(logging.Formatter):
    """
    A custom formatter that adds colors to log output.

    Provides a clean, readable format with timestamp and colored level indicators.
    """

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        use_colors: bool = True,
    ):
        """
        Initialize the colored formatter.

        Args:
            fmt: Log message format string.
            datefmt: Date format string.
            use_colors: Whether to use ANSI colors in output.
        """
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and _supports_color()

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colors matching loguru style."""
        # Create a copy to avoid modifying the original record
        record = logging.makeLogRecord(record.__dict__)

        # Get timestamp
        timestamp = self.formatTime(record, self.datefmt)

        # Get level name and colors
        level_name = LEVEL_NAMES.get(record.levelno, "UNKNOWN ")
        level_name_color = LEVEL_NAME_COLORS.get(record.levelno, Colors.WHITE)
        message_color = LEVEL_COLORS.get(record.levelno, Colors.WHITE)

        # Build the formatted message (loguru style: timestamp | level | message)
        if self.use_colors:
            formatted = (
                f"{Colors.GREEN}{timestamp}{Colors.RESET} | "
                f"{level_name_color}{Colors.BOLD}{level_name}{Colors.RESET} | "
                f"{message_color}{record.getMessage()}{Colors.RESET}"
            )
        else:
            formatted = f"{timestamp} | {level_name} | {record.getMessage()}"

        # Handle exception info
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                if self.use_colors:
                    formatted += f"\n{Colors.RED}{record.exc_text}{Colors.RESET}"
                else:
                    formatted += f"\n{record.exc_text}"

        return formatted


# Module-level state
_handler: Optional[logging.Handler] = None

# Create and configure the logger instance once at module load time
# This avoids the overhead of calling get_logger() on every log call
_logger: logging.Logger = logging.getLogger("argoproxy")
_logger.setLevel(logging.DEBUG)
# Prevent propagation to root logger to avoid duplicate logs
_logger.propagate = False


def get_logger() -> logging.Logger:
    """
    Get the configured logger instance.

    Note: For performance, prefer using the module-level log_* functions
    (log_info, log_error, etc.) which use a cached logger reference.

    Returns:
        The configured logger for argo-proxy.
    """
    return _logger


def setup_logging(verbose: bool = False, use_colors: bool = True) -> logging.Logger:
    """
    Setup logging with the specified configuration.

    Args:
        verbose: If True, set log level to DEBUG; otherwise INFO.
        use_colors: Whether to use colored output.

    Returns:
        The configured logger instance.
    """
    global _handler

    logger = get_logger()

    # Remove existing handler if present
    if _handler is not None:
        logger.removeHandler(_handler)

    # Create new handler
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Create formatter with timestamp format matching loguru style
    formatter = ColoredFormatter(
        datefmt="%Y-%m-%d %H:%M:%S.%f",
        use_colors=use_colors,
    )

    # Override formatTime to include milliseconds
    def format_time_with_millis(
        record: logging.LogRecord, datefmt: Optional[str] = None
    ) -> str:
        import datetime

        ct = datetime.datetime.fromtimestamp(record.created)
        return ct.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(record.msecs):03d}"

    formatter.formatTime = format_time_with_millis  # type: ignore

    _handler.setFormatter(formatter)
    logger.addHandler(_handler)

    return logger


def truncate_string(s: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to max_length with suffix.

    Args:
        s: The string to truncate.
        max_length: Maximum length before truncation.
        suffix: Suffix to append when truncated.

    Returns:
        Truncated string with remaining character count.
    """
    if len(s) <= max_length:
        return s
    remaining = len(s) - max_length
    return f"{s[:max_length]}{suffix}[{remaining} more chars]"


def truncate_base64(data_url: str, max_length: int = 100) -> str:
    """
    Truncates base64 data URLs for cleaner logging.

    Args:
        data_url: The data URL containing base64 content.
        max_length: Maximum length to show before truncation.

    Returns:
        Truncated string with placeholder for readability.
    """
    if not data_url.startswith("data:"):
        return data_url

    # Split into header and data parts
    if ";base64," in data_url:
        header, base64_data = data_url.split(";base64,", 1)
        if len(base64_data) > max_length:
            truncated = base64_data[:max_length]
            remaining_chars = len(base64_data) - max_length
            return f"{header};base64,{truncated}...[{remaining_chars} more chars]"

    return data_url


def sanitize_request_data(
    data: Dict[str, Any],
    *,
    max_base64_length: int = 100,
    max_content_length: int = 500,
    max_tool_desc_length: int = 100,
    truncate_tools: bool = True,
    truncate_messages: bool = True,
) -> Dict[str, Any]:
    """
    Sanitizes request data for logging by truncating long content.

    Args:
        data: The request data dictionary.
        max_base64_length: Maximum length to show for base64 content.
        max_content_length: Maximum length to show for message content.
        max_tool_desc_length: Maximum length to show for tool descriptions.
        truncate_tools: Whether to truncate tool definitions.
        truncate_messages: Whether to truncate message content.

    Returns:
        Sanitized data dictionary with truncated content for cleaner logging.
    """
    # Deep copy to avoid modifying original data
    sanitized = copy.deepcopy(data)

    # Process messages if they exist
    if (
        truncate_messages
        and "messages" in sanitized
        and isinstance(sanitized["messages"], list)
    ):
        for message in sanitized["messages"]:
            if isinstance(message, dict) and "content" in message:
                content = message["content"]

                # Process string content (truncate long system prompts, etc.)
                if isinstance(content, str) and len(content) > max_content_length:
                    message["content"] = truncate_string(content, max_content_length)

                # Process list-type content (multimodal messages)
                elif isinstance(content, list):
                    for content_part in content:
                        if isinstance(content_part, dict):
                            # Handle image URLs
                            if (
                                content_part.get("type") == "image_url"
                                and "image_url" in content_part
                                and "url" in content_part["image_url"]
                            ):
                                url = content_part["image_url"]["url"]
                                if url.startswith("data:"):
                                    content_part["image_url"]["url"] = truncate_base64(
                                        url, max_base64_length
                                    )
                            # Handle text content
                            elif (
                                content_part.get("type") == "text"
                                and "text" in content_part
                                and isinstance(content_part["text"], str)
                                and len(content_part["text"]) > max_content_length
                            ):
                                content_part["text"] = truncate_string(
                                    content_part["text"], max_content_length
                                )

    # Process tools if they exist and truncation is enabled
    if truncate_tools and "tools" in sanitized and isinstance(sanitized["tools"], list):
        tool_count = len(sanitized["tools"])
        # Replace tools with a summary
        sanitized["tools"] = f"[{tool_count} tools defined - truncated for logging]"

    return sanitized


def create_request_summary(data: Dict[str, Any]) -> str:
    """
    Creates a concise one-line summary of a request for logging.

    Args:
        data: The request data dictionary.

    Returns:
        A concise summary string.
    """
    summary_parts = []

    # Model
    if "model" in data:
        summary_parts.append(f"model={data['model']}")

    # Message count
    if "messages" in data and isinstance(data["messages"], list):
        msg_count = len(data["messages"])
        summary_parts.append(f"messages={msg_count}")

    # Tools
    if "tools" in data and isinstance(data["tools"], list):
        tool_count = len(data["tools"])
        summary_parts.append(f"tools={tool_count}")

    # Stream
    if "stream" in data:
        summary_parts.append(f"stream={data['stream']}")

    # Max tokens
    if "max_tokens" in data:
        summary_parts.append(f"max_tokens={data['max_tokens']}")

    # User
    if "user" in data:
        summary_parts.append(f"user={data['user']}")

    return ", ".join(summary_parts)


def log_request(
    data: Dict[str, Any],
    label: str = "REQUEST",
    *,
    show_summary: bool = True,
    show_full: bool = False,
    sanitize: bool = True,
    max_content_length: int = 500,
    truncate_tools: bool = True,
) -> None:
    """
    Log a request with configurable verbosity.

    Args:
        data: The request data dictionary.
        label: Label for the log entry (e.g., "ORIGINAL", "CONVERTED").
        show_summary: Whether to show a one-line summary.
        show_full: Whether to show the full request data.
        sanitize: Whether to sanitize the data before logging.
        max_content_length: Maximum content length when sanitizing.
        truncate_tools: Whether to truncate tools when sanitizing.
    """
    if show_summary:
        summary = create_request_summary(data)
        _logger.info(f"[{label}] {summary}")

    if show_full:
        if sanitize:
            log_data = sanitize_request_data(
                data,
                max_content_length=max_content_length,
                truncate_tools=truncate_tools,
            )
        else:
            log_data = data

        _logger.debug(_make_bar(f"[{label}]"))
        _logger.debug(json.dumps(log_data, indent=4, ensure_ascii=False))
        _logger.debug(_make_bar())


def log_original_request(
    data: Dict[str, Any],
    *,
    verbose: bool = False,
    max_content_length: int = 500,
) -> None:
    """
    Log the original request before any transformation.

    Args:
        data: The original request data.
        verbose: Whether to show full request details.
        max_content_length: Maximum content length when sanitizing.
    """
    log_request(
        data,
        label="ORIGINAL",
        show_summary=True,
        show_full=verbose,
        max_content_length=max_content_length,
    )


def log_converted_request(
    data: Dict[str, Any],
    *,
    verbose: bool = False,
    max_content_length: int = 500,
) -> None:
    """
    Log the converted request after transformation.

    Args:
        data: The converted request data.
        verbose: Whether to show full request details.
        max_content_length: Maximum content length when sanitizing.
    """
    log_request(
        data,
        label="CONVERTED",
        show_summary=True,
        show_full=verbose,
        max_content_length=max_content_length,
    )


def log_request_diff(
    original: Dict[str, Any],
    converted: Dict[str, Any],
    *,
    verbose: bool = False,
) -> None:
    """
    Log the difference between original and converted requests.

    This is useful for debugging to see what transformations were applied.

    Args:
        original: The original request data.
        converted: The converted request data.
        verbose: Whether to show detailed diff.
    """
    # Create summaries
    original_summary = create_request_summary(original)
    converted_summary = create_request_summary(converted)

    # Log summaries
    _logger.info(f"[ORIGINAL]  {original_summary}")
    _logger.info(f"[CONVERTED] {converted_summary}")

    # Highlight key differences
    diffs: List[str] = []

    # Model change
    orig_model = original.get("model", "")
    conv_model = converted.get("model", "")
    if orig_model != conv_model:
        diffs.append(f"model: {orig_model} -> {conv_model}")

    # Tools change
    orig_tools = len(original.get("tools", []))
    conv_tools = len(converted.get("tools", []))
    if orig_tools != conv_tools:
        diffs.append(f"tools: {orig_tools} -> {conv_tools}")

    # User added
    if "user" not in original and "user" in converted:
        diffs.append(f"user: added ({converted['user']})")

    if diffs:
        _logger.info(f"[CHANGES] {', '.join(diffs)}")


def log_upstream_error(
    status_code: int,
    error_text: str,
    *,
    endpoint: str = "unknown",
    is_streaming: bool = False,
) -> None:
    """
    Log an upstream API error in a consistent format.

    Args:
        status_code: The HTTP status code from the upstream response.
        error_text: The error text/body from the upstream response.
        endpoint: The endpoint name (e.g., "chat", "embed", "response", "native_openai").
        is_streaming: Whether this was a streaming request.
    """
    request_type = "streaming" if is_streaming else "non-streaming"
    _logger.error(
        f"[UPSTREAM ERROR] endpoint={endpoint}, type={request_type}, "
        f"status={status_code}, error={error_text}"
    )


def log_warning(message: str, *, context: str = "") -> None:
    """
    Log a warning message in a consistent format.

    Args:
        message: The warning message to log.
        context: Optional context information (e.g., function name, module).
    """
    if context:
        _logger.warning(f"[{context}] {message}")
    else:
        _logger.warning(message)


def log_error(message: str, *, context: str = "") -> None:
    """
    Log an error message in a consistent format.

    Args:
        message: The error message to log.
        context: Optional context information (e.g., function name, module).
    """
    if context:
        _logger.error(f"[{context}] {message}")
    else:
        _logger.error(message)


def log_info(message: str, *, context: str = "") -> None:
    """
    Log an info message in a consistent format.

    Args:
        message: The info message to log.
        context: Optional context information (e.g., function name, module).
    """
    if context:
        _logger.info(f"[{context}] {message}")
    else:
        _logger.info(message)


def log_debug(message: str, *, context: str = "") -> None:
    """
    Log a debug message in a consistent format.

    Args:
        message: The debug message to log.
        context: Optional context information (e.g., function name, module).
    """
    if context:
        _logger.debug(f"[{context}] {message}")
    else:
        _logger.debug(message)


def _make_bar(message: str = "", bar_length: int = 40) -> str:
    """
    Create a visual separator bar for log output.

    Args:
        message: Optional message to embed in the bar.
        bar_length: Total length of the bar.

    Returns:
        A formatted bar string.
    """
    message = " " + message.strip() + " "
    message = message.strip()
    dash_length = (bar_length - len(message)) // 2
    return "-" * dash_length + message + "-" * dash_length


# Initialize logging with default settings on module import
setup_logging()
