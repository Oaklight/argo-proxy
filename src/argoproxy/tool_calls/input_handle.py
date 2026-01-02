"""
input_handle.py
---------------

Tool call input handling module for converting between different LLM provider formats.

This module provides functionality for:
1. Prompt-based tool handling (for models without native tool support)
2. Native tool format conversion between providers (OpenAI, Anthropic, Google)
3. Validation and error handling

Usage
=====
>>> from argoproxy.tool_calls.input_handle import handle_tools
>>> processed_data = handle_tools(request_data, native_tools=True)
"""

import json
from typing import Any, Dict, List, Literal, Optional, Union

from loguru import logger
from pydantic import ValidationError

from ..utils.models import determine_model_family
from .tool_prompts import get_prompt_skeleton

# ======================================================================
# TYPE ALIASES
# ======================================================================

Tools = List[Dict[str, Any]]
ToolChoice = Union[str, Dict[str, Any], None]

# ======================================================================
# PROMPT-BASED TOOL HANDLING
# ======================================================================


def build_tool_prompt(
    tools: Tools,
    tool_choice: ToolChoice = None,
    *,
    parallel_tool_calls: bool = False,
    json_indent: Optional[int] = None,
    model_family: Literal["openai", "anthropic", "google"] = "openai",
) -> str:
    """
    Return a system-prompt string embedding `tools`, `tool_choice`
    and `parallel_tool_calls`.

    Parameters
    ----------
    tools : list[dict]
        The exact array you would pass to the OpenAI API.
    tool_choice : str | dict | None
        "none", "auto", or an object with "name", etc.
    parallel_tool_calls : bool
        Whether multiple tool calls may be returned in one turn.
    json_indent : int | None
        Pretty-print indentation for embedded JSON blobs. Defaults to None for most compact output.

    Returns
    -------
    str
        A fully formatted system prompt.
    """
    # Dump JSON with stable key order for readability
    tools_json = json.dumps(tools, indent=json_indent, ensure_ascii=False)
    tool_choice_json = json.dumps(
        tool_choice if tool_choice is not None else "none",
        indent=json_indent,
        ensure_ascii=False,
    )
    parallel_flag = "true" if parallel_tool_calls else "false"

    PROMPT_SKELETON = get_prompt_skeleton(model_family)
    return PROMPT_SKELETON.format(
        tools_json=tools_json,
        tool_choice_json=tool_choice_json,
        parallel_flag=parallel_flag,
    )


def handle_tools_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process input data containing tool calls using prompt-based approach.

    This function will:
    1. Check if input data contains tool-related fields (tools, tool_choice, parallel_tool_calls)
    2. If present, generate tool call system prompt and add it to system messages
    3. Return processed data

    Parameters
    ----------
    data : dict
        Dictionary containing request data, may include:
        - tools: List of tool definitions
        - tool_choice: Tool selection preference
        - parallel_tool_calls: Whether to allow parallel tool calls
        - messages: Message list
        - system: System message

    Returns
    -------
    dict
        Processed data dictionary
    """
    # Check if there are tool-related fields
    tools = data.get("tools")
    if not tools:
        return data

    # Get tool call related parameters
    tool_choice = data.get("tool_choice")
    parallel_tool_calls = data.get("parallel_tool_calls", False)

    # Generate tool call prompt
    tool_prompt = build_tool_prompt(
        tools=tools, tool_choice=tool_choice, parallel_tool_calls=parallel_tool_calls
    )

    # Add tool prompt to system messages
    if "messages" in data:
        # Handle messages format
        messages = data["messages"]

        # Find existing system message
        system_msg_found = False
        for _, msg in enumerate(messages):
            if msg.get("role") == "system":
                # Add tool prompt to existing system message
                existing_content = msg.get("content", "")
                msg["content"] = f"{existing_content}\n\n{tool_prompt}".strip()
                system_msg_found = True
                break

        # If no system message found, add one at the beginning
        if not system_msg_found:
            system_message = {"role": "system", "content": tool_prompt}
            messages.insert(0, system_message)

    elif "system" in data:
        # Handle direct system field
        existing_system = data["system"]
        if isinstance(existing_system, str):
            data["system"] = f"{existing_system}\n\n{tool_prompt}".strip()
        elif isinstance(existing_system, list):
            data["system"] = existing_system + [tool_prompt]
    else:
        # If no system message, create one
        data["system"] = tool_prompt

    # Remove original tool-related fields as they've been converted to prompts
    data.pop("tools", None)
    data.pop("tool_choice", None)
    data.pop("parallel_tool_calls", None)

    return data


# ======================================================================
# GOOGLE/GEMINI SPECIFIC HANDLING
# ======================================================================


def handle_google_parallel_tool_calls(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Handle Google/Gemini's parallel tool calls by converting them to sequential format.

    Gemini API requires that the number of function response parts equals the number
    of function call parts. To solve this, we convert parallel tool calls into
    individual call-result pairs.

    Transforms:
    [user_msg, assistant_msg_with_multiple_tool_calls, tool_result1, tool_result2]

    Into:
    [user_msg, assistant_msg_with_tool_call1, tool_result1, assistant_msg_with_tool_call2, tool_result2]

    Args:
        messages: List of message dictionaries

    Returns:
        List of transformed message dictionaries with sequential tool calls
    """
    from .google_helpers import (
        collect_tool_results,
        create_sequential_call_result_pairs,
        is_parallel_tool_call_message,
    )

    transformed_messages = []
    i = 0

    while i < len(messages):
        message = messages[i]

        if is_parallel_tool_call_message(message):
            logger.warning(
                f"[Google Sequential] Found assistant message with {len(message['tool_calls'])} parallel tool calls"
            )

            # Collect consecutive tool result messages
            tool_results, next_index = collect_tool_results(messages, i + 1)

            # Validate tool calls and results count match
            if len(tool_results) != len(message["tool_calls"]):
                logger.warning(
                    f"[Google Sequential] Mismatch: {len(message['tool_calls'])} tool calls but {len(tool_results)} tool results"
                )
                # Fallback: keep original structure
                transformed_messages.append(message)
                i += 1
                continue

            # Convert to sequential call-result pairs
            sequential_pairs = create_sequential_call_result_pairs(
                message["tool_calls"], tool_results, message.get("content", "")
            )

            transformed_messages.extend(sequential_pairs)

            logger.warning(
                f"[Google Sequential] Converted {len(message['tool_calls'])} parallel tool calls to {len(sequential_pairs) // 2} sequential pairs"
            )

            # Skip the original tool result messages
            i = next_index
        else:
            # Keep other messages as-is
            transformed_messages.append(message)
            i += 1

    logger.warning(
        f"[Google Sequential] Transformed {len(messages)} messages into {len(transformed_messages)} messages"
    )
    return transformed_messages


# ======================================================================
# VALIDATION FUNCTIONS
# ======================================================================


def handle_tools_native(data: Dict[str, Any]) -> Dict[str, Any]:
    """Handles tool calls by converting them to the appropriate format for the target model.

    Uses middleware classes from handler.py to process tool-related parameters in the request data
    and converts them from OpenAI format to the native format required by the target model
    (OpenAI, Anthropic, or Google). Also handles tool_calls in messages for different model families.

    Args:
        data: Request data dictionary containing model parameters. May include:
            - tools: List of tool definitions in OpenAI format
            - tool_choice: Tool choice parameter ("auto", "none", "required", or dict)
            - parallel_tool_calls: Whether to enable parallel tool calls (removed for now)
            - model: Model identifier used to determine the target format
            - messages: List of messages that may contain tool_calls

    Returns:
        Modified request data with tools and tool_calls converted to the appropriate format for the
        target model. If no tools are present, returns the original data unchanged.

    Note:
        - Uses middleware classes Tool, ToolChoice, and ToolCall from handler.py
        - parallel_tool_calls parameter is currently removed and not implemented
        - Tool conversion is performed based on the model family detected from the model name
        - OpenAI format tools are passed through unchanged for OpenAI models
        - Converts tool_calls in messages between different API formats
    """
    from .handler import Tool, ToolCall, ToolChoice

    # Check if there are tool-related fields
    tools = data.get("tools")
    messages = data.get("messages", [])

    # Determine target model family
    model_type = determine_model_family(data.get("model", "gpt4o"))

    # Process tools if present
    if tools:
        # Get tool call related parameters
        tool_choice = data.get("tool_choice", "auto")

        # Remove parallel_tool_calls from data for now
        # TODO: Implement parallel tool calls handling later
        parallel_tool_calls = data.pop("parallel_tool_calls", False)

        try:
            # Convert tools using middleware classes
            converted_tools = []
            for tool_dict in tools:
                # Validate and convert each tool using Tool middleware
                tool_obj = Tool.from_entry(
                    tool_dict, api_format="openai-chatcompletion"
                )

                if model_type == "openai":
                    # Keep OpenAI format
                    converted_tools.append(tool_obj.serialize("openai-chatcompletion"))
                elif model_type == "anthropic":
                    # Convert to Anthropic format
                    converted_tools.append(tool_obj.serialize("anthropic"))
                elif model_type == "google":
                    # Convert to Google format (when implemented)
                    converted_tools.append(tool_obj.serialize("google"))
                else:
                    # Default to OpenAI format
                    converted_tools.append(tool_obj.serialize("openai-chatcompletion"))

            # Convert tool_choice using ToolChoice middleware
            if tool_choice is not None:
                tool_choice_obj = ToolChoice.from_entry(
                    tool_choice, api_format="openai-chatcompletion"
                )

                if model_type == "openai":
                    converted_tool_choice = tool_choice_obj.serialize(
                        "openai-chatcompletion"
                    )
                elif model_type == "anthropic":
                    converted_tool_choice = tool_choice_obj.serialize("anthropic")
                elif model_type == "google":
                    converted_tool_choice = tool_choice_obj.serialize("google")
                else:
                    converted_tool_choice = tool_choice_obj.serialize(
                        "openai-chatcompletion"
                    )
            else:
                converted_tool_choice = None

            data["tools"] = converted_tools
            data["tool_choice"] = converted_tool_choice

            logger.warning(
                f"[Input Handle] {model_type.title()} model detected, converted tools"
            )
            logger.warning(f"[Input Handle] Converted tools: {converted_tools}")
            logger.warning(
                f"[Input Handle] Converted tool_choice: {converted_tool_choice}"
            )

        except (ValueError, ValidationError) as e:
            logger.error(f"[Input Handle] Tool validation/conversion failed: {e}")
            raise ValueError(f"Tool validation/conversion failed: {e}")

    # Process tool_calls and tool messages if present
    if messages:
        # Special handling for Google/Gemini models: convert parallel tool calls to sequential format
        if model_type == "google":
            messages = handle_google_parallel_tool_calls(messages)

        converted_messages = []
        for message in messages:
            converted_message = message.copy()

            # Check if message contains tool_calls (assistant messages)
            if "tool_calls" in message and message["tool_calls"]:
                try:
                    if model_type == "openai":
                        # Keep OpenAI format with tool_calls field
                        converted_tool_calls = []
                        for tool_call_dict in message["tool_calls"]:
                            tool_call_obj = ToolCall.from_entry(
                                tool_call_dict, api_format="openai-chatcompletion"
                            )
                            converted_tool_calls.append(
                                tool_call_obj.serialize("openai-chatcompletion")
                            )
                        converted_message["tool_calls"] = converted_tool_calls
                        logger.warning(
                            f"[Input Handle] Converted tool_calls in message: {converted_tool_calls}"
                        )

                    elif model_type == "anthropic":
                        # For Anthropic, convert tool_calls to content array format
                        content_blocks = []

                        # Add text content if present
                        if message.get("content", ""):
                            content_blocks.append(
                                {"type": "text", "text": message["content"]}
                            )

                        # Convert tool_calls to tool_use blocks in content
                        for tool_call_dict in message["tool_calls"]:
                            tool_call_obj = ToolCall.from_entry(
                                tool_call_dict, api_format="openai-chatcompletion"
                            )
                            anthropic_tool_call = tool_call_obj.serialize("anthropic")
                            content_blocks.append(anthropic_tool_call)

                        # Replace tool_calls with content array
                        converted_message["content"] = content_blocks
                        converted_message.pop(
                            "tool_calls", None
                        )  # Remove tool_calls field
                        logger.warning(
                            f"[Input Handle] Converted tool_calls to Anthropic content format: {content_blocks}"
                        )

                    elif model_type == "google":
                        # For Google/Gemini, convert tool_calls to Google format
                        converted_tool_calls = []
                        for tool_call_dict in message["tool_calls"]:
                            tool_call_obj = ToolCall.from_entry(
                                tool_call_dict, api_format="openai-chatcompletion"
                            )
                            converted_tool_calls.append(
                                tool_call_obj.serialize("google")
                            )
                        converted_message["tool_calls"] = converted_tool_calls
                        logger.warning(
                            f"[Input Handle] Converted tool_calls in message: {converted_tool_calls}"
                        )

                    else:
                        # Default to OpenAI format
                        converted_tool_calls = []
                        for tool_call_dict in message["tool_calls"]:
                            tool_call_obj = ToolCall.from_entry(
                                tool_call_dict, api_format="openai-chatcompletion"
                            )
                            converted_tool_calls.append(
                                tool_call_obj.serialize("openai-chatcompletion")
                            )
                        converted_message["tool_calls"] = converted_tool_calls
                        logger.warning(
                            f"[Input Handle] Converted tool_calls in message: {converted_tool_calls}"
                        )

                except (ValueError, ValidationError) as e:
                    logger.error(
                        f"[Input Handle] Tool call conversion failed in message: {e}"
                    )
                    # Keep original tool_calls if conversion fails
                    pass

            # Check if message is a tool result message (role: tool)
            elif message.get("role") == "tool":
                if model_type == "anthropic":
                    # For Anthropic, tool results should be in user messages with tool_result content
                    # Convert OpenAI tool message format to Anthropic format
                    tool_call_id = message.get("tool_call_id")
                    content = message.get("content", "")

                    # Create Anthropic-style tool result message
                    converted_message = {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call_id,
                                "content": content,
                            }
                        ],
                    }
                    logger.warning(
                        f"[Input Handle] Converted tool message to Anthropic format: {converted_message}"
                    )
                elif model_type == "google":
                    # For Google/Gemini, keep tool messages in OpenAI format
                    # The upstream API expects OpenAI-style tool messages
                    logger.warning(
                        "[Input Handle] Keeping Google tool result in OpenAI format"
                    )
                # For OpenAI, keep the original format

            converted_messages.append(converted_message)

        data["messages"] = converted_messages

    return data


# ======================================================================
# MAIN ENTRY POINT
# ======================================================================


def handle_tools(data: Dict[str, Any], *, native_tools: bool = True) -> Dict[str, Any]:
    """
    Process input data containing tool calls with fallback strategy.

    This function will:
    1. If native_tools=True: attempt native tool handling (handle_tools_native)
    2. If native handling validation fails or native_tools=False: fallback to prompt-based handling (handle_tools_prompt)
    3. Return processed data

    Parameters
    ----------
    data : dict
        Dictionary containing request data, may include:
        - tools: List of tool definitions
        - tool_choice: Tool selection preference
        - parallel_tool_calls: Whether to allow parallel tool calls
        - messages: Message list
        - system: System message
        - model: Model identifier
    native_tools : bool, optional
        Whether to use native tools or prompt-based tools, by default True

    Returns
    -------
    dict
        Processed data dictionary
    """
    # Check if there are tool-related fields
    tools = data.get("tools")
    if not tools:
        return data

    if native_tools:
        try:
            # First attempt: try native tool handling
            return handle_tools_native(data)
        except (ValueError, ValidationError, NotImplementedError) as e:
            # Fallback: use prompt-based handling if native handling fails
            # This handles validation errors, unsupported model types, or unimplemented conversions
            logger.warning(
                f"Native tool handling failed, falling back to prompt-based: {e}"
            )
            return handle_tools_prompt(data)
    else:
        # Directly use prompt-based handling when native_tools=False
        return handle_tools_prompt(data)


# ======================================================================
# EXAMPLE USAGE
# ======================================================================

if __name__ == "__main__":  # pragma: no cover
    # --- 1. Define tools exactly as you would for the OpenAI API ------------
    tools_example = [
        {
            "name": "get_weather",
            "description": "Get the current weather in a given city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
                "required": ["location"],
            },
        },
        {
            "name": "news_headlines",
            "description": "Fetch top news headlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["politics", "technology", "sports"],
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["category"],
            },
        },
    ]

    # --- 2. (Optional) choose preferred tool or "auto"/"none" --------------
    tool_choice_example = "auto"  # could also be {"name": "get_weather"} or "none"

    # --- 3. Build the prompt ------------------------------------------------
    prompt = build_tool_prompt(
        tools_example,
        tool_choice_example,
        parallel_tool_calls=True,
    )

    print("=== Direct Tool Prompt Building ===")
    print(prompt)
    print("\n" + "=" * 50 + "\n")

    # --- 4. Demonstrate handle_tools function --------------------------------
    print("=== Demonstrate handle_tools Function ===")

    # Example input data (similar to OpenAI API request)
    input_data = {
        "messages": [
            {"role": "user", "content": "What's the weather like in Beijing today?"}
        ],
        "tools": tools_example,
        "tool_choice": tool_choice_example,
        "parallel_tool_calls": True,
    }

    print("Original input data:")
    print(json.dumps(input_data, indent=2, ensure_ascii=False))

    # Process tool calls
    processed_data = handle_tools(input_data.copy())

    print("\nProcessed data:")
    print(json.dumps(processed_data, indent=2, ensure_ascii=False))
