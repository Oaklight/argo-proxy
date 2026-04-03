"""
google_helpers.py
-----------------

Helper functions for Google/Gemini tool call processing.
This module contains utility functions to support the conversion of parallel
tool calls to sequential format for Gemini API compatibility.
"""

from typing import Any, Union

from ...utils.logging import log_debug, log_error


def is_parallel_tool_call_message(message: dict[str, Any]) -> bool:
    """Check if a message contains multiple tool calls (parallel tool calls)."""
    return bool(
        message.get("role") == "assistant"
        and message.get("tool_calls")
        and len(message["tool_calls"]) > 1
    )


def collect_tool_results(
    messages: list[dict[str, Any]], start_index: int
) -> tuple[list[dict[str, Any]], int]:
    """
    Collect consecutive tool result messages starting from start_index.

    Args:
        messages: List of all messages
        start_index: Index to start collecting from

    Returns:
        tuple: (list of tool result messages, next index after tool results)
    """
    tool_results = []
    j = start_index
    while j < len(messages) and messages[j].get("role") == "tool":
        tool_results.append(messages[j])
        j += 1
    return tool_results, j


def create_tool_result_mapping(
    tool_results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Create a mapping from tool_call_id to tool_result for efficient lookup."""
    tool_result_map = {}
    for tool_result in tool_results:
        tool_call_id = tool_result.get("tool_call_id")
        if tool_call_id:
            tool_result_map[tool_call_id] = tool_result
    return tool_result_map


def find_matching_tool_result(
    tool_call: dict[str, Any],
    tool_result_map: dict[str, dict[str, Any]],
    tool_results: list[dict[str, Any]],
    index: int,
) -> tuple[Union[dict[str, Any], None], str]:
    """
    Find the matching tool result for a given tool call.

    Args:
        tool_call: The tool call to find a match for
        tool_result_map: Mapping of tool_call_id to tool_result
        tool_results: List of all tool results (for positional fallback)
        index: Position index for fallback matching

    Returns:
        tuple: (matching tool result or None, match type: "id" or "position")
    """
    tool_call_id = tool_call.get("id")

    # Try ID matching first
    if tool_call_id and tool_call_id in tool_result_map:
        log_debug(
            f"[Google Sequential] Found matching result for tool_call_id: {tool_call_id}",
            context="google_helpers",
        )
        return tool_result_map[tool_call_id], "id"

    # Fallback to positional matching
    if index < len(tool_results):
        log_debug(
            f"[Google Sequential] Using positional matching for tool call {index + 1}",
            context="google_helpers",
        )
        return tool_results[index], "position"

    # No match found
    log_error(
        f"[Google Sequential] No corresponding result found for tool call {index + 1}",
        context="google_helpers",
    )
    return None, "none"


def verify_id_alignment(tool_call: dict[str, Any], tool_result: dict[str, Any]) -> None:
    """Verify that tool call and result IDs are aligned and log any mismatches."""
    tool_call_id = tool_call.get("id")
    result_tool_call_id = tool_result.get("tool_call_id")

    if tool_call_id and result_tool_call_id and tool_call_id != result_tool_call_id:
        log_debug(
            f"[Google Sequential] ID mismatch: tool_call_id={tool_call_id}, "
            f"result_tool_call_id={result_tool_call_id}",
            context="google_helpers",
        )


def create_sequential_call_result_pairs(
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    base_content: str,
) -> list[dict[str, Any]]:
    """
    Convert parallel tool calls into sequential call-result pairs.

    Args:
        tool_calls: List of tool calls from the assistant message
        tool_results: List of corresponding tool results
        base_content: Original content from the assistant message

    Returns:
        List of alternating assistant and tool messages
    """
    sequential_messages = []
    tool_result_map = create_tool_result_mapping(tool_results)

    for idx, tool_call in enumerate(tool_calls):
        # Find matching tool result
        corresponding_result, match_type = find_matching_tool_result(
            tool_call, tool_result_map, tool_results, idx
        )

        if corresponding_result is None:
            continue

        # Verify ID alignment
        verify_id_alignment(tool_call, corresponding_result)

        # Create individual assistant message with single tool call
        individual_assistant_msg = {
            "role": "assistant",
            "content": base_content
            if idx == 0
            else "",  # Only include content in first message
            "tool_calls": [tool_call],
        }
        sequential_messages.append(individual_assistant_msg)

        # Add corresponding tool result
        sequential_messages.append(corresponding_result)

        # Log the creation
        tool_call_id = tool_call.get("id")
        result_tool_call_id = corresponding_result.get("tool_call_id")
        log_debug(
            f"[Google Sequential] Created call-result pair {idx + 1}/{len(tool_calls)} "
            f"(ID: {tool_call_id} -> {result_tool_call_id}, match: {match_type})",
            context="google_helpers",
        )

    return sequential_messages
