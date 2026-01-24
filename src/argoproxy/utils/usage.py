import json
import uuid
from typing import Any, Dict, List, Literal, Optional, Union

from ..types import CompletionUsage, ResponseUsage, Usage
from .tokens import count_tokens_async


async def calculate_completion_tokens_async(
    content: Optional[str],
    tool_calls: Optional[List[Any]],
    model: str,
    api_format: Literal["chat_completion", "response"] = "chat_completion",
) -> int:
    """Asynchronously calculate completion tokens for content and tool calls.

    Args:
        content: The text content of the completion.
        tool_calls: List of tool calls.
        model: The model name for token counting.
        api_format: The API format, either "chat_completion" or "response".

    Returns:
        Total completion tokens.
    """
    completion_tokens = await count_tokens_async(content, model) if content else 0
    if tool_calls:
        # Convert ToolCall objects to serializable format for token counting
        if tool_calls and len(tool_calls) > 0 and hasattr(tool_calls[0], "serialize"):
            # tool_calls is a list of ToolCall objects
            serialize_mode = (
                "openai-chatcompletion"
                if api_format == "chat_completion"
                else "openai-response"
            )
            serializable_tool_calls = [
                tc.serialize(serialize_mode) for tc in tool_calls
            ]
        else:
            # tool_calls is already a list of dicts
            serializable_tool_calls = tool_calls

        tool_tokens = await count_tokens_async(
            json.dumps(serializable_tool_calls), model
        )
        completion_tokens += tool_tokens
    return completion_tokens


def create_usage(
    prompt_tokens: int,
    completion_tokens: int,
    api_type: Literal["chat_completion", "completion", "response", "embedding"],
) -> Union[CompletionUsage, ResponseUsage, Usage]:
    """Create a usage object based on the API type.

    Args:
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.
        api_type: The type of API.

    Returns:
        A usage object (CompletionUsage, ResponseUsage, or Usage).
    """
    total_tokens = prompt_tokens + completion_tokens

    if api_type in ("chat_completion", "completion"):
        return CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    elif api_type == "response":
        return ResponseUsage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
    elif api_type == "embedding":
        return Usage(
            prompt_tokens=prompt_tokens,
            total_tokens=prompt_tokens,
        )
    else:
        raise ValueError(f"Unsupported api_type: {api_type}")


def generate_usage_chunk(
    prompt_tokens: int,
    completion_tokens: int,
    api_type: Literal["chat_completion", "completion", "response"],
    model: str,
    created_timestamp: int,
    chunk_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a usage chunk for streaming responses.

    Args:
        prompt_tokens: Number of input tokens.
        completion_tokens: Number of output tokens.
        api_type: The type of API.
        model: The model name.
        created_timestamp: The creation timestamp.
        chunk_id: Optional ID for the chunk. If not provided, generates a new one.

    Returns:
        A dictionary representing the usage chunk.
    """
    usage = create_usage(prompt_tokens, completion_tokens, api_type)

    if api_type == "chat_completion":
        return {
            "id": chunk_id if chunk_id is not None else str(uuid.uuid4().hex),
            "object": "chat.completion.chunk",
            "created": created_timestamp,
            "model": model,
            "choices": [],
            "usage": usage.model_dump(),
        }
    elif api_type == "completion":
        return {
            "id": chunk_id if chunk_id is not None else str(uuid.uuid4().hex),
            "object": "completion",
            "created": created_timestamp,
            "model": model,
            "choices": [],
            "usage": usage.model_dump(),
        }
    elif api_type == "response":
        # For responses, usage is usually part of ResponseCompletedEvent
        # This function might be less used for 'response' if it's handled differently
        return usage.model_dump()
    else:
        raise ValueError(f"Unsupported api_type for streaming usage chunk: {api_type}")
