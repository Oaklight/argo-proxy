from typing import Any


def deduplicate_and_concatenate(messages: list[str]) -> str:
    """
    Removes duplicates and concatenates messages with double newline separation.

    Args:
        messages (List[str]): List of message strings.

    Returns:
        str: Deduplicated, concatenated string.
    """
    return "\n\n".join(dict.fromkeys(messages)).strip()


def handle_multiple_entries_prompt(data: dict[str, Any]) -> dict[str, Any]:
    """
    Deduplicates and merges 'system' and 'prompt' lists into single strings.

    Args:
        data (Dict[str, Any]): Dictionary with 'system' and 'prompt' keys.

    Returns:
        Dict[str, Any]: Updated dictionary with merged entries.
    """

    if "system" in data:
        if isinstance(data["system"], list):
            data["system"] = deduplicate_and_concatenate(data["system"])

    if "prompt" in data:
        if isinstance(data["prompt"], list):
            data["prompt"] = [deduplicate_and_concatenate(data["prompt"])]

    return data


def handle_option_2_input(data: dict[str, Any]) -> dict[str, Any]:
    """
    Segregates messages into 'system' and 'prompt' based on roles.

    Args:
        data (Dict[str, Any]): Dictionary with 'messages' list.

    Returns:
        Dict[str, Any]: Data split into 'system' and 'prompt'.
    """
    if "messages" in data:
        system_messages = [
            msg["content"]
            for msg in data["messages"]
            if msg["role"] in ("system", "developer")
        ]
        data["system"] = system_messages

        prompt_messages = []
        for msg in data["messages"]:
            if msg["role"] in ("user", "assistant"):
                content = msg["content"]
                if isinstance(content, list):
                    texts = [
                        part["text"].strip()
                        for part in content
                        if part.get("type") == "text"
                    ]
                    prefixed_texts = [
                        f"{msg['role']}: {text.strip()}" for text in texts
                    ]
                    prompt_messages.extend(prefixed_texts)
                else:
                    prompt_messages.append(f"{msg['role']}: {content.strip()}")

        data["prompt"] = prompt_messages
        del data["messages"]

    return data


def handle_no_sys_msg(data: dict[str, Any]) -> dict[str, Any]:
    """
    Changes 'system' messages to 'user' and merges into 'prompt'.

    Args:
        data (Dict[str, Any]): Dictionary with 'messages' list.

    Returns:
        Dict[str, Any]: Updated dictionary without 'system'.
    """
    if "messages" in data:
        for message in data["messages"]:
            if message["role"] == "system":
                message["role"] = "user"
    if "system" in data:
        data["prompt"] = (
            [data["system"]] + data["prompt"]
            if isinstance(data["system"], str)
            else data["system"] + data["prompt"]
        )
        del data["system"]

    return data


def normalize_system_message_content(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalizes content field for system/developer role messages.

    Converts List[Dict] content to a single string for system/developer roles.

    Args:
        messages: List of message dictionaries.

    Returns:
        The modified messages list with normalized content.

    Example:
        Input message:
        [{
            "role": "system",
            "content": [{"type": "text", "text": "You are a helpful assistant"}]
        }]

        Output message:
        [{
            "role": "system",
            "content": "You are a helpful assistant"
        }]
    """
    for message in messages:
        # Skip if not system/developer role or content is not a list
        if (
            message.get("role") not in ("system", "developer")
            or "content" not in message
            or not isinstance(message["content"], list)
        ):
            continue

        # Extract text from content parts
        text_parts = [
            str(part["text"])
            for part in message["content"]
            if isinstance(part, dict) and part.get("type") == "text" and "text" in part
        ]

        # Update content
        message["content"] = (
            "\n\n".join(text_parts).strip() if text_parts else str(message["content"])
        )

    return messages


def ensure_user_message_exists(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ensures at least one user message exists in the messages list.

    If no user messages are found, adds a void user message to maintain
    proper conversation flow for models that require user input.

    Args:
        messages: List of message dictionaries.

    Returns:
        List[Dict[str, Any]]: Messages list with at least one user message.

    Example:
        Input (no user messages):
        [{"role": "system", "content": "You are helpful"}]

        Output:
        [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": ""}
        ]
    """
    # Check if any user messages exist
    has_user_message = any(message.get("role") == "user" for message in messages)

    # If no user messages found, append a void user message
    if not has_user_message:
        messages.append(
            {
                "role": "user",
                "content": "[continue]",
            }
        )

    return messages


def scrutinize_message_entries(data: dict[str, Any]) -> dict[str, Any]:
    """
    Scrutinizes and normalizes message entries, ensuring proper content formatting.

    This function:
    1. Converts List[Dict] content to strings for system/developer role messages (Claude models only)
    2. Ensures standalone system/prompt fields are properly cast to strings

    Args:
        data (Dict[str, Any]): Dictionary containing message data.

    Returns:
        Dict[str, Any]: Updated dictionary with normalized content.

    Example:
        Input:
        {
            "model": "claude-3-sonnet",
            "messages": [{
                "role": "system",
                "content": [{"type": "text", "text": "You are a helpful assistant"}]
            }],
            "system": ["Additional system prompt"],
            "prompt": 42
        }

        Output:
        {
            "model": "claude-3-sonnet",
            "messages": [{
                "role": "system",
                "content": "You are a helpful assistant"
            }],
            "system": ["Additional system prompt"],
            "prompt": "42"
        }
    """
    # Only normalize system/developer messages for Claude models
    if "claude" in data["model"] or "gemini" in data["model"]:
        # Process messages array
        if "messages" in data:
            data["messages"] = ensure_user_message_exists(data["messages"])
    if "gemini" in data["model"]:
        # Process messages array
        if "messages" in data:
            data["messages"] = normalize_system_message_content(data["messages"])

    # Handle standalone system/prompt fields
    for field in ("system", "prompt"):
        if field in data:
            if isinstance(data[field], list):
                data[field] = [str(item) for item in data[field]]
            else:
                data[field] = str(data[field])

    return data
