"""Model registry, classification, and upstream communication."""

from .constants import (
    ANTHROPIC_CODENAMES,
    CLAUDE_PATTERN,
    GEMINI_PATTERN,
    GPT_O_PATTERN,
    NATIVE_TOOL_CALL_MODELS,
    NATIVE_TOOL_CALL_PATTERNS,
    NO_SYS_MSG_MODELS,
    NO_SYS_MSG_PATTERNS,
    OPTION_2_INPUT_MODELS,
    OPTION_2_INPUT_PATTERNS,
    TIKTOKEN_ENCODING_PREFIX_MAPPING,
    _DEFAULT_CHAT_MODELS,
    _EMBED_MODELS,
    _is_anthropic_model,
    classify_model_family,
    filter_model_by_patterns,
    flatten_mapping,
)
from .registry import ModelRegistry, OpenAIModel
from .upstream import Model, produce_argo_model_list

__all__ = [
    "ANTHROPIC_CODENAMES",
    "CLAUDE_PATTERN",
    "GEMINI_PATTERN",
    "GPT_O_PATTERN",
    "NATIVE_TOOL_CALL_MODELS",
    "NATIVE_TOOL_CALL_PATTERNS",
    "NO_SYS_MSG_MODELS",
    "NO_SYS_MSG_PATTERNS",
    "OPTION_2_INPUT_MODELS",
    "OPTION_2_INPUT_PATTERNS",
    "TIKTOKEN_ENCODING_PREFIX_MAPPING",
    "Model",
    "ModelRegistry",
    "OpenAIModel",
    "_DEFAULT_CHAT_MODELS",
    "_EMBED_MODELS",
    "_is_anthropic_model",
    "classify_model_family",
    "filter_model_by_patterns",
    "flatten_mapping",
    "produce_argo_model_list",
]
