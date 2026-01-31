import secrets
import string
from typing import Any, Dict, Literal, Union

from pydantic import ValidationError

from ..types.function_call import ChatCompletionNamedToolChoiceParam
from .logging import log_warning

# Claude models have a max_tokens limit of 21000 for non-streaming requests
CLAUDE_NON_STREAMING_MAX_TOKENS = 21000

API_FORMATS = Literal[
    "openai",  # old default, alias to openai-chatcompletion
    "openai-chatcompletion",  # chat completion
    "openai-response",
    "anthropic",
    "google",
]


def determine_model_family(
    model: str = "gpt4o",
) -> Literal["openai", "anthropic", "google", "unknown"]:
    """
    Determine the model family based on the model name.
    """
    if "gpt" in model:
        return "openai"
    elif "claude" in model:
        return "anthropic"
    elif "gemini" in model:
        return "google"
    else:
        return "unknown"


def generate_id(
    *,
    mode: Union[API_FORMATS, Literal["general"]] = "general",
) -> str:
    """
    Return a random identifier.

    Parameters
    ----------
    mode :
        'general'                →  <22-char base62 string> (default)
        'openai'/'openai-chatcompletion' →  call_<22-char base62 string>
        'openai-response'        →  fc_<48-char hex string>
        'anthropic'              →  toolu_<24-char base62 string>

    chat_len : int
        Length of the suffix for the chat-completion variant.

    Examples
    --------
    >>> generate_id()
    'b9krJaIcuBM4lej3IyI5heVc'

    >>> generate_id(mode='openai')
    'call_b9krJaIcuBM4lej3IyI5heVc'

    >>> generate_id(mode='openai-response')
    'fc_68600a8868248199a436492a47a75e440766032408f75a09'

    >>> generate_id(mode='anthropic')
    'toolu_vrtx_01LiZkD1myhnDz7gcoEe4Y5A'
    """
    ALPHANUM = string.ascii_letters + string.digits
    if mode == "general":
        # Generate 22-char base62 string for general use
        return "".join(secrets.choice(ALPHANUM) for _ in range(22))

    elif mode in ["openai", "openai-chatcompletion"]:
        suffix = "".join(secrets.choice(ALPHANUM) for _ in range(22))
        return f"call_{suffix}"

    elif mode == "openai-response":
        # 24 bytes → 48 hex chars (matches your example)
        return f"fc_{secrets.token_hex(24)}"

    elif mode == "anthropic":
        # Generate 24-char base62 string to match the pattern
        suffix = "".join(secrets.choice(ALPHANUM) for _ in range(24))
        return f"toolu_{suffix}"

    elif mode == "google":
        # Google/Gemini uses simple alphanumeric IDs, similar to general format
        # Generate 16-char base62 string for Google use
        return "".join(secrets.choice(ALPHANUM) for _ in range(16))

    else:
        raise ValueError(f"Unknown mode: {mode!r}")


def apply_claude_max_tokens_limit(
    data: Dict[str, Any],
    *,
    is_non_streaming: bool = False,
) -> Dict[str, Any]:
    """
    Apply max_tokens limit for Claude models when using non-streaming mode.

    Claude models have a max_tokens limit of 21000 for non-streaming requests.
    If the requested max_tokens exceeds this limit, it will be capped.

    Args:
        data: The request data dictionary containing model and max_tokens.
        is_non_streaming: Whether this is a non-streaming request (including pseudo_stream).

    Returns:
        The modified request data with capped max_tokens if applicable.
    """
    if not is_non_streaming:
        return data

    model = data.get("model", "")
    model_family = determine_model_family(model)

    if model_family != "anthropic":
        return data

    max_tokens = data.get("max_tokens")
    if max_tokens is None:
        return data

    if max_tokens > CLAUDE_NON_STREAMING_MAX_TOKENS:
        log_warning(
            f"Claude model '{model}' max_tokens ({max_tokens}) exceeds "
            f"non-streaming limit ({CLAUDE_NON_STREAMING_MAX_TOKENS}). "
            f"Capping to {CLAUDE_NON_STREAMING_MAX_TOKENS}.",
            context="CLAUDE_MAX_TOKENS",
        )
        data["max_tokens"] = CLAUDE_NON_STREAMING_MAX_TOKENS

    return data


def validate_tool_choice(tool_choice: Union[str, Dict[str, Any]]) -> None:
    """Helper function to validate tool_choice parameter.

    Args:
        tool_choice: The tool choice parameter to validate.

    Raises:
        ValueError: If tool_choice is invalid.
    """
    if isinstance(tool_choice, str):
        valid_strings = ["none", "auto", "required"]
        if tool_choice not in valid_strings:
            raise ValueError(
                f"Invalid tool_choice string '{tool_choice}'. "
                f"Must be one of: {', '.join(valid_strings)}"
            )
    elif isinstance(tool_choice, dict):
        try:
            ChatCompletionNamedToolChoiceParam.model_validate(tool_choice, strict=False)
        except ValidationError as e:
            raise ValueError(f"Invalid tool_choice dict structure: {e}")
    else:
        raise ValueError(
            f"Invalid tool_choice type '{type(tool_choice).__name__}'. "
            f"Must be str or dict"
        )
