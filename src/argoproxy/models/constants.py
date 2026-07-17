"""Model constants, default lists, patterns, and classification helpers."""

import fnmatch
from typing import Any


def flatten_mapping(mapping: dict[str, Any]) -> dict[str, str]:
    flat = {}
    for model, aliases in mapping.items():
        if isinstance(aliases, str):
            flat[aliases] = model
        else:
            for alias in aliases:
                flat[alias] = model
    return flat


# Default models fallback — kept in sync with the live /v1/models endpoint.
_DEFAULT_CHAT_MODELS = flatten_mapping(
    {
        # openai – gpt-4o (legacy, still served)
        "gpt4o": "argo:gpt-4o",
        # openai – o-series reasoning
        "gpto1": ["argo:gpt-o1", "argo:o1"],
        "gpto3mini": ["argo:gpt-o3-mini", "argo:o3-mini"],
        "gpto3": ["argo:gpt-o3", "argo:o3"],
        "gpto4mini": ["argo:gpt-o4-mini", "argo:o4-mini"],
        # openai – gpt-4.1 family
        "gpt41": "argo:gpt-4.1",
        "gpt41mini": "argo:gpt-4.1-mini",
        "gpt41nano": "argo:gpt-4.1-nano",
        # openai – gpt-5 family
        "gpt5": "argo:gpt-5",
        "gpt5mini": "argo:gpt-5-mini",
        "gpt5nano": "argo:gpt-5-nano",
        "gpt51": "argo:gpt-5.1",
        "gpt52": "argo:gpt-5.2",
        "gpt54": "argo:gpt-5.4",
        "gpt54nano": "argo:gpt-5.4-nano",
        "gpt55": "argo:gpt-5.5",
        # gemini
        "gemini25pro": "argo:gemini-2.5-pro",
        "gemini25flash": "argo:gemini-2.5-flash",
        "gemini35flash": "argo:gemini-3.5-flash",
        "gemini31flashlite": "argo:gemini-3.1-flash-lite",
        # claude – opus
        "claudeopus47": ["argo:claude-4.7-opus", "argo:claude-opus-4.7"],
        "claudeopus46": ["argo:claude-4.6-opus", "argo:claude-opus-4.6"],
        "claudeopus45": ["argo:claude-4.5-opus", "argo:claude-opus-4.5"],
        "claudeopus41": ["argo:claude-4.1-opus", "argo:claude-opus-4.1"],
        # claude – sonnet
        "claudesonnet46": ["argo:claude-4.6-sonnet", "argo:claude-sonnet-4.6"],
        "claudesonnet45": ["argo:claude-4.5-sonnet", "argo:claude-sonnet-4.5"],
        # claude – haiku
        "claudehaiku45": ["argo:claude-4.5-haiku", "argo:claude-haiku-4.5"],
    }
)

_EMBED_MODELS = flatten_mapping(
    {
        "ada002": "argo:text-embedding-ada-002",
        "v3small": "argo:text-embedding-3-small",
        "v3large": "argo:text-embedding-3-large",
    }
)


def filter_model_by_patterns(
    model_dict: dict[str, str], patterns: set[str]
) -> list[str]:
    """Filter model_dict values (model_id) by given fnmatch patterns,
    returning both the model_name (key) and model_id (value) for matches."""
    matching = set()
    for model_name, model_id in model_dict.items():
        if any(fnmatch.fnmatch(model_id, pattern) for pattern in patterns):
            matching.add(model_name)
            matching.add(model_id)
    return sorted(matching)


# any models that unable to handle system prompt (o1-mini / o1-preview retired)
NO_SYS_MSG_PATTERNS: set[str] = set()

NO_SYS_MSG_MODELS = filter_model_by_patterns(
    _DEFAULT_CHAT_MODELS,
    NO_SYS_MSG_PATTERNS,
)


# any models that only able to handle single system prompt and no system prompt at all
OPTION_2_INPUT_PATTERNS: set[str] = set()

OPTION_2_INPUT_MODELS = filter_model_by_patterns(
    _DEFAULT_CHAT_MODELS,
    OPTION_2_INPUT_PATTERNS,
)

# any models that supports native tool call
NATIVE_TOOL_CALL_PATTERNS: set[str] = {
    "*o1",
    "*o3*",
    "*o4*",
}

NATIVE_TOOL_CALL_MODELS = filter_model_by_patterns(
    _DEFAULT_CHAT_MODELS,
    NATIVE_TOOL_CALL_PATTERNS,
)

TIKTOKEN_ENCODING_PREFIX_MAPPING = {
    "gpt5": "o200k_base",  # gpt-5 family
    "gpto": "o200k_base",  # o-series
    "gpt4o": "o200k_base",  # gpt-4o
    "gpt41": "o200k_base",  # gpt-4.1 family
    # this order need to be preserved to correctly parse mapping
    "gpt4": "cl100k_base",  # gpt-4 series (legacy fallback)
    "ada002": "cl100k_base",  # embedding
    "v3": "cl100k_base",  # embedding
}

# --- Provider detection patterns ---

GPT_O_PATTERN = "gpto*"
CLAUDE_PATTERN = "claude*"
GEMINI_PATTERN = "gemini*"

ANTHROPIC_CODENAMES = ("claude", "sonnet", "opus", "haiku", "fable")


def _is_anthropic_model(model_id: str) -> bool:
    model_lower = model_id.lower()
    return any(name in model_lower for name in ANTHROPIC_CODENAMES)


def classify_model_family(model_id: str) -> str:
    """Classify a model by its provider family based on model ID patterns."""
    if (
        fnmatch.fnmatch(model_id, "gpt*")
        or fnmatch.fnmatch(model_id, GPT_O_PATTERN)
        or fnmatch.fnmatch(model_id, "ada*")
        or fnmatch.fnmatch(model_id, "v3*")
        or fnmatch.fnmatch(model_id, "*embedding*")
    ):
        return "openai"

    if _is_anthropic_model(model_id):
        return "anthropic"

    if fnmatch.fnmatch(model_id, GEMINI_PATTERN):
        return "google"

    return "unknown"
