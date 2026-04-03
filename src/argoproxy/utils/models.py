from typing import Literal

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
    """Determine the model family based on the model name."""
    if "gpt" in model:
        return "openai"
    elif "claude" in model:
        return "anthropic"
    elif "gemini" in model:
        return "google"
    else:
        return "unknown"
