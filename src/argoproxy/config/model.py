"""ArgoConfig dataclass and display helpers."""

import json
from dataclasses import asdict, dataclass, field
from typing import ClassVar


from ..utils.logging import log_info
from ..utils.misc import make_bar

# ARGO API environment URLs
ENVIRONMENTS: dict[str, str] = {
    "prod": "https://apps.inside.anl.gov/argoapi",
    "dev": "https://apps-dev.inside.anl.gov/argoapi",
    "test": "https://apps-test.inside.anl.gov/argoapi",
}


@dataclass
class ArgoConfig:
    """Configuration values with validation and interactive methods."""

    REQUIRED_KEYS: ClassVar[list[str]] = [
        "port",
        "user",
    ]

    ENVIRONMENTS: ClassVar[dict[str, str]] = ENVIRONMENTS

    # Configuration fields with default values
    host: str = "0.0.0.0"  # Default to 0.0.0.0
    port: int = 44497
    user: str = ""
    verbose: bool = True

    _argo_base_url: str = ""  # User-configurable base URL, overrides _argo_dev_base
    _argo_dev_base: str = ENVIRONMENTS["dev"]
    _argo_prod_base: str = ENVIRONMENTS["prod"]

    # Derived fields (to be constructed from base URL if not provided)
    _argo_url: str = ""
    _argo_stream_url: str = ""
    _argo_embedding_url: str = ""
    _argo_model_url: str = ""

    # Native OpenAI endpoint
    _native_openai_base_url: str = ""

    # Native Anthropic endpoint
    _native_anthropic_base_url: str = ""

    # Legacy ARGO gateway (opt-in fallback for v3.0.0)
    _use_legacy_argo: bool = False

    # Config version for migration tracking
    config_version: str = ""

    # CLI flags
    _real_stream: bool = True
    _tool_prompt: bool = False
    _enable_leaked_tool_fix: bool = False
    _dev_mode: bool = False

    # Validation and resolver settings
    _skip_url_validation: bool = False
    _user_validated: bool = False  # Set after upstream user validation passes
    connection_test_timeout: int = 5  # seconds per URL validation request
    resolve_overrides: dict = field(default_factory=dict)

    # Image processing settings
    enable_payload_control: bool = False  # Enable automatic payload size control
    max_payload_size: int = 20  # MB default (total for all images)
    image_timeout: int = 30  # seconds
    concurrent_downloads: int = 10  # parallel downloads

    @property
    def argo_base_url(self) -> str:
        """Get the effective Argo base URL (without trailing path segments)."""
        if self._argo_base_url:
            return self._argo_base_url.rstrip("/")
        return self._argo_dev_base.rstrip("/")

    # chat endpoint
    @property
    def argo_url(self) -> str:
        """Get the Argo chat endpoint URL."""
        if self._argo_url:
            return self._argo_url
        return f"{self.argo_base_url}/api/v1/resource/chat/"

    # stream chat endpoint
    @property
    def argo_stream_url(self) -> str:
        """Get the Argo stream chat endpoint URL."""
        if self._argo_stream_url:
            return self._argo_stream_url
        return f"{self.argo_base_url}/api/v1/resource/streamchat/"

    # embedding endpoint
    @property
    def argo_embedding_url(self) -> str:
        """Get the Argo embedding endpoint URL.

        Uses argo_base_url if explicitly set, otherwise falls back to
        production base URL for backward compatibility.
        """
        if self._argo_embedding_url:
            return self._argo_embedding_url
        if self._argo_base_url:
            return f"{self.argo_base_url}/api/v1/resource/embed/"
        return f"{self._argo_prod_base}/api/v1/resource/embed/"

    @property
    def argo_model_url(self) -> str:
        """Get the Argo models endpoint URL."""
        if self._argo_model_url:
            return self._argo_model_url
        return f"{self.argo_base_url}/api/v1/models/"

    @property
    def argo_message_url(self) -> str:
        """Get the Argo message endpoint URL (Claude native compatible)."""
        return f"{self.argo_base_url}/message/"

    @property
    def pseudo_stream(self):
        if self._real_stream and self._real_stream is True:
            return False
        return True

    @property
    def native_tools(self):
        if self._tool_prompt and self._tool_prompt is True:
            return False
        return True

    @property
    def native_openai_base_url(self) -> str:
        """Get the native OpenAI base URL (without trailing slash).

        This is the base path for OpenAI-compatible endpoints.  Callers
        append specific paths like ``/chat/completions`` or ``/models``.

        If explicitly set, returns the configured value (stripped of
        trailing ``/``).  Otherwise derives from ``argo_base_url``.
        """
        if self._native_openai_base_url:
            return self._native_openai_base_url.rstrip("/")
        return f"{self.argo_base_url}/v1"

    @property
    def use_legacy_argo(self):
        """Check if legacy ARGO gateway mode is enabled (opt-in fallback)."""
        return self._use_legacy_argo

    @property
    def native_anthropic_base_url(self) -> str:
        """Get the native Anthropic base URL.

        This is the base URL for the Anthropic Messages endpoint.
        Callers append ``/v1/messages`` to form the full endpoint URL.

        If explicitly set, returns the configured value (stripped of
        trailing ``/``).  Otherwise derives from ``argo_base_url``.
        """
        if self._native_anthropic_base_url:
            return self._native_anthropic_base_url.rstrip("/")
        return self.argo_base_url

    @property
    def enable_leaked_tool_fix(self):
        """Check if leaked tool call fix is enabled."""
        return self._enable_leaked_tool_fix

    @property
    def dev_mode(self):
        """Check if dev (pure reverse proxy) mode is enabled."""
        return self._dev_mode

    @classmethod
    def from_dict(cls, config_dict: dict):
        """Create ArgoConfig instance from a dictionary."""
        # Map property fields to internal fields if present
        field_map = {
            "argo_base_url": "_argo_base_url",
            "argo_url": "_argo_url",
            "argo_stream_url": "_argo_stream_url",
            "argo_embedding_url": "_argo_embedding_url",
            "real_stream": "_real_stream",
            "native_openai_base_url": "_native_openai_base_url",
            "native_anthropic_base_url": "_native_anthropic_base_url",
            "use_legacy_argo": "_use_legacy_argo",
            "skip_url_validation": "_skip_url_validation",
        }
        valid_fields = {
            k: v for k, v in config_dict.items() if k in cls.__annotations__
        }
        # Add mapped fields
        for config_key, internal_key in field_map.items():
            if config_key in config_dict:
                valid_fields[internal_key] = config_dict[config_key]
        instance = cls(**valid_fields)
        return instance

    def to_persistent_dict(self) -> dict:
        """Return only the fields that should be persisted to config file.

        Excludes runtime-derived fields (mode, native endpoint URLs) that
        are computed from ``argo_base_url`` at load time.  User-configurable
        optional fields are included when they differ from their defaults.
        """
        serialized = asdict(self)
        # Drop private fields
        serialized = {k: v for k, v in serialized.items() if not k.startswith("_")}

        # Add the user-configurable base URL (stored as private field)
        if self._argo_base_url:
            serialized["argo_base_url"] = self.argo_base_url

        # Persist optional flags only when set to non-default values
        if self._use_legacy_argo:
            serialized["use_legacy_argo"] = True
        if self._skip_url_validation:
            serialized["skip_url_validation"] = True

        # Persist native URLs only when explicitly overridden (differ from
        # the values that would be derived from argo_base_url)
        base = self.argo_base_url
        if (
            self._native_openai_base_url
            and self._native_openai_base_url.rstrip("/") != f"{base}/v1"
        ):
            serialized["native_openai_base_url"] = self.native_openai_base_url
        if (
            self._native_anthropic_base_url
            and self._native_anthropic_base_url.rstrip("/") != base
        ):
            serialized["native_anthropic_base_url"] = self.native_anthropic_base_url

        return dict(sorted(serialized.items()))

    def to_dict(self) -> dict:
        """Convert ArgoConfig instance to a dictionary for display.

        In v3 universal mode, exposes native endpoint URLs and mode info.
        In legacy mode, exposes the classic ARGO gateway URLs.
        """
        serialized = self.to_persistent_dict()

        if self.use_legacy_argo:
            # Legacy mode: show ARGO gateway URLs
            serialized["argo_url"] = self.argo_url
            serialized["argo_stream_url"] = self.argo_stream_url
            serialized["argo_embedding_url"] = self.argo_embedding_url
            serialized["mode"] = "legacy"
        else:
            # Universal mode: show native endpoint URLs
            serialized["native_openai_base_url"] = self.native_openai_base_url
            serialized["native_anthropic_base_url"] = self.native_anthropic_base_url
            serialized["mode"] = "universal"

        return dict(sorted(serialized.items()))

    def __str__(self) -> str:
        """Provide a formatted string representation for logger.infoing."""
        return json.dumps(self.to_dict(), indent=4)

    def show(self, message: str | None = None) -> None:
        """Display the current configuration in a formatted manner.

        Args:
            message: Message to display before showing the configuration.
        """
        # Use the __str__ method for formatted output
        _show(str(self), message if message else "Current configuration:")


def _show(body: str, message: str | None = None) -> None:
    """Helper to display a formatted message with a bar."""
    log_info(message if message else "", context="config")
    log_info(make_bar(), context="config")
    log_info(body, context="config")
    log_info(make_bar(), context="config")
