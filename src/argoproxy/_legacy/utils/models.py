"""Legacy utility functions for ID generation and Claude token limits.

Only used by the v2 ARGO gateway pipeline (--legacy-argo).
"""

import secrets
import string
from typing import Any, Literal, Union

from ...utils.logging import log_warning
from ...utils.models import API_FORMATS, determine_model_family

# Claude models have a max_tokens limit of 21000 for non-streaming requests
CLAUDE_NON_STREAMING_MAX_TOKENS = 21000


def generate_id(
    *,
    mode: Union[API_FORMATS, Literal["general"]] = "general",
) -> str:
    """Return a random identifier.

    Parameters
    ----------
    mode :
        'general'                →  <22-char base62 string> (default)
        'openai'/'openai-chatcompletion' →  call_<22-char base62 string>
        'openai-response'        →  fc_<48-char hex string>
        'anthropic'              →  toolu_<24-char base62 string>

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
        return "".join(secrets.choice(ALPHANUM) for _ in range(22))

    elif mode in ["openai", "openai-chatcompletion"]:
        suffix = "".join(secrets.choice(ALPHANUM) for _ in range(22))
        return f"call_{suffix}"

    elif mode == "openai-response":
        return f"fc_{secrets.token_hex(24)}"

    elif mode == "anthropic":
        suffix = "".join(secrets.choice(ALPHANUM) for _ in range(24))
        return f"toolu_{suffix}"

    elif mode == "google":
        return "".join(secrets.choice(ALPHANUM) for _ in range(16))

    else:
        raise ValueError(f"Unknown mode: {mode!r}")


def apply_claude_max_tokens_limit(
    data: dict[str, Any],
    *,
    is_non_streaming: bool = False,
) -> dict[str, Any]:
    """Apply max_tokens limit for Claude models when using non-streaming mode.

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
