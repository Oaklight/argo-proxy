"""Attack logging module for recording and analyzing malicious HTTP requests.

This module provides functionality to:
1. Log attack attempts with concise warning messages
2. Save detailed attack information to files for analysis
3. Organize logs by date in a dedicated directory
"""

import gzip
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .logging import log_warning

# Module-level logger
logger = logging.getLogger(__name__)

# Attack log directory name (relative to config file location)
ATTACK_LOG_DIR = "attack_logs"


class AttackLogger:
    """Logger for recording malicious HTTP request attempts.

    Attributes:
        log_dir: Directory where attack logs are stored.
        enabled: Whether attack logging is enabled.
    """

    # Known attack patterns for classification
    ATTACK_TYPES = {
        "struts2_ognl": [
            "xwork.MethodAccessor.denyMethodExecution",
            "_memberAccess",
            "allowStaticMethodAccess",
            "org.apache.commons.io.IOUtils",
            "org.apache.struts2.ServletActionContext",
            "java.lang.Runtime",
        ],
        "directory_traversal": [
            "././././",
            "../../../",
            "..%2f",
            "..%5c",
        ],
        "ssti_probe": [
            "${{",
            "${#",
            "{{",
            "%24%7B%7B",
            "%24%7B%23",
        ],
        "sql_injection": [
            "' OR '",
            "1=1",
            "UNION SELECT",
            "--",
        ],
        "xss_probe": [
            "<script>",
            "javascript:",
            "onerror=",
            "onload=",
        ],
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the attack logger.

        Args:
            config_path: Path to the config file. Attack logs will be stored
                in a subdirectory relative to this path.
        """
        self.enabled = True
        self._log_dir: Optional[Path] = None
        self._config_path = config_path

    @property
    def log_dir(self) -> Path:
        """Get or create the attack log directory."""
        if self._log_dir is None:
            if self._config_path:
                base_dir = self._config_path.parent
            else:
                base_dir = Path.cwd()

            self._log_dir = base_dir / ATTACK_LOG_DIR
            self._log_dir.mkdir(parents=True, exist_ok=True)

        return self._log_dir

    def set_config_path(self, config_path: Path) -> None:
        """Update the config path and reset log directory.

        Args:
            config_path: New path to the config file.
        """
        self._config_path = config_path
        self._log_dir = None  # Reset to recalculate on next access

    def classify_attack(self, raw_data: str) -> str:
        """Classify the type of attack based on patterns in the request.

        Args:
            raw_data: Raw request data or error message.

        Returns:
            Attack type classification string.
        """
        raw_lower = raw_data.lower()

        for attack_type, patterns in self.ATTACK_TYPES.items():
            for pattern in patterns:
                if pattern.lower() in raw_lower:
                    return attack_type

        return "unknown"

    def log_attack(
        self,
        remote_ip: str,
        raw_request: str,
        error_type: str,
        error_message: str,
        exc_info: Optional[tuple] = None,
    ) -> None:
        """Log an attack attempt with a concise warning and save details to file.

        Args:
            remote_ip: IP address of the attacker.
            raw_request: Raw HTTP request data.
            error_type: Type of error (e.g., "BadStatusLine", "InvalidURLError").
            error_message: Error message from the parser.
            exc_info: Exception info tuple (type, value, traceback).
        """
        if not self.enabled:
            return

        # Classify the attack
        attack_type = self.classify_attack(raw_request)

        # Log concise warning message
        log_warning(
            f"🛡️ Attack blocked: {attack_type} from {remote_ip} ({error_type})",
            context="security",
        )

        # Prepare detailed log entry
        timestamp = datetime.now()
        log_entry = {
            "timestamp": timestamp.isoformat(),
            "remote_ip": remote_ip,
            "attack_type": attack_type,
            "error_type": error_type,
            "error_message": error_message,
            "raw_request": raw_request[:4096],  # Limit size
        }

        # Add traceback if available
        if exc_info:
            log_entry["traceback"] = "".join(traceback.format_exception(*exc_info))

        # Save to file
        self._save_log_entry(timestamp, log_entry)

    def _save_log_entry(self, timestamp: datetime, entry: dict[str, Any]) -> None:
        """Save a log entry to a date-organized file.

        Args:
            timestamp: Timestamp of the attack.
            entry: Log entry dictionary.
        """
        try:
            # Create date-based filename
            date_str = timestamp.strftime("%Y-%m-%d")
            log_file = self.log_dir / f"attacks_{date_str}.jsonl.gz"

            # Append to gzipped JSONL file
            with gzip.open(log_file, "at", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        except Exception as e:
            # Don't let logging failures affect the main application
            logger.debug(f"Failed to save attack log: {e}")


class AttackFilter(logging.Filter):
    """Logging filter that intercepts attack-related log records.

    This filter catches aiohttp parser errors caused by malicious requests,
    logs them through the AttackLogger, and suppresses the original verbose output.
    """

    # Error patterns that indicate an attack
    ERROR_PATTERNS = [
        "BadStatusLine",
        "InvalidURLError",
        "BadHttpMethod",
        "Expected CRLF after version",
        "Unexpected start char in url",
        "http_exceptions",
    ]

    # Attack payload patterns
    ATTACK_PATTERNS = [
        # Struts2 OGNL
        "xwork.MethodAccessor",
        "_memberAccess",
        "allowStaticMethodAccess",
        "java.lang.Runtime",
        # Directory traversal
        "././././",
        "../../../",
        # SSTI
        "${{",
        "${#",
        "%24%7B",
    ]

    def __init__(self, attack_logger: AttackLogger):
        """Initialize the filter with an attack logger.

        Args:
            attack_logger: AttackLogger instance for recording attacks.
        """
        super().__init__()
        self.attack_logger = attack_logger

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and process attack-related log records.

        Args:
            record: The log record to filter.

        Returns:
            True to allow the record, False to suppress it.
        """
        message = record.getMessage()

        # Get exception text if available
        exc_text = ""
        if record.exc_info:
            exc_text = "".join(traceback.format_exception(*record.exc_info))
        elif record.exc_text:
            exc_text = record.exc_text

        full_text = message + exc_text

        # Check if this is an attack-related error
        is_attack_error = any(p in full_text for p in self.ERROR_PATTERNS)
        has_attack_pattern = any(p in full_text for p in self.ATTACK_PATTERNS)

        if is_attack_error or has_attack_pattern:
            # Extract remote IP from message (format: "Error handling request from X.X.X.X")
            remote_ip = self._extract_ip(message)

            # Extract error type
            error_type = self._extract_error_type(full_text)

            # Log the attack
            self.attack_logger.log_attack(
                remote_ip=remote_ip,
                raw_request=exc_text or message,
                error_type=error_type,
                error_message=message,
                exc_info=record.exc_info,
            )

            # Suppress the original verbose log
            return False

        return True

    def _extract_ip(self, message: str) -> str:
        """Extract IP address from log message.

        Args:
            message: Log message potentially containing an IP.

        Returns:
            Extracted IP address or "unknown".
        """
        import re

        # Pattern for "from X.X.X.X" or just IP address
        ip_pattern = r"(?:from\s+)?(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        match = re.search(ip_pattern, message)
        return match.group(1) if match else "unknown"

    def _extract_error_type(self, text: str) -> str:
        """Extract error type from exception text.

        Args:
            text: Full text including exception info.

        Returns:
            Error type name.
        """
        for pattern in self.ERROR_PATTERNS:
            if pattern in text:
                return pattern
        return "unknown"


# Global attack logger instance
_attack_logger: Optional[AttackLogger] = None


def get_attack_logger() -> AttackLogger:
    """Get the global attack logger instance.

    Returns:
        The global AttackLogger instance.
    """
    global _attack_logger
    if _attack_logger is None:
        _attack_logger = AttackLogger()
    return _attack_logger


def setup_attack_logging(config_path: Optional[Path] = None) -> AttackFilter:
    """Setup attack logging with the given config path.

    Args:
        config_path: Path to the config file for determining log directory.

    Returns:
        AttackFilter instance to be added to loggers.
    """
    attack_logger = get_attack_logger()
    if config_path:
        attack_logger.set_config_path(config_path)

    return AttackFilter(attack_logger)
