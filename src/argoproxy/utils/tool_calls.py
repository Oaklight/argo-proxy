"""Utility functions for tool call message reordering.

Some upstream gateways (e.g. ARGO) reject requests that contain parallel tool
calls (multiple ``tool_calls`` in a single assistant message) for certain model
families.  The functions in this module convert parallel tool calls into
sequential assistant+tool message pairs so that every assistant message contains
exactly one tool call followed by its corresponding tool result.

The reordering operates on **OpenAI Chat Completion** message format, which is
also the target format used by argo-proxy when routing Gemini requests through
the ARGO gateway.
"""

from __future__ import annotations

from typing import Any

from .logging import log_debug, log_error, log_warning


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


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
    """Collect consecutive tool result messages starting from *start_index*.

    Args:
        messages: List of all messages.
        start_index: Index to start collecting from.

    Returns:
        A ``(tool_results, next_index)`` tuple where *next_index* points to the
        first message after the collected tool results.
    """
    tool_results: list[dict[str, Any]] = []
    j = start_index
    while j < len(messages) and messages[j].get("role") == "tool":
        tool_results.append(messages[j])
        j += 1
    return tool_results, j


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _create_tool_result_mapping(
    tool_results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Create a mapping from ``tool_call_id`` to tool result for O(1) lookup."""
    mapping: dict[str, dict[str, Any]] = {}
    for result in tool_results:
        tool_call_id = result.get("tool_call_id")
        if tool_call_id:
            mapping[tool_call_id] = result
    return mapping


def _find_matching_tool_result(
    tool_call: dict[str, Any],
    tool_result_map: dict[str, dict[str, Any]],
    tool_results: list[dict[str, Any]],
    index: int,
) -> tuple[dict[str, Any] | None, str]:
    """Find the matching tool result for a given tool call.

    Tries ID-based matching first; falls back to positional matching.

    Args:
        tool_call: The tool call to find a match for.
        tool_result_map: Mapping of ``tool_call_id`` to tool result.
        tool_results: Ordered list of all tool results (positional fallback).
        index: Position index for fallback matching.

    Returns:
        A ``(result, match_type)`` tuple where *match_type* is ``"id"``,
        ``"position"``, or ``"none"``.
    """
    tool_call_id = tool_call.get("id")

    # Try ID matching first
    if tool_call_id and tool_call_id in tool_result_map:
        log_debug(
            f"[Reorder] Found matching result for tool_call_id: {tool_call_id}",
            context="tool_calls",
        )
        return tool_result_map[tool_call_id], "id"

    # Fallback to positional matching
    if index < len(tool_results):
        log_debug(
            f"[Reorder] Using positional matching for tool call {index + 1}",
            context="tool_calls",
        )
        return tool_results[index], "position"

    # No match found
    log_error(
        f"[Reorder] No corresponding result found for tool call {index + 1}",
        context="tool_calls",
    )
    return None, "none"


def _verify_id_alignment(
    tool_call: dict[str, Any], tool_result: dict[str, Any]
) -> None:
    """Log a warning when tool call and result IDs don't match."""
    tool_call_id = tool_call.get("id")
    result_tool_call_id = tool_result.get("tool_call_id")

    if tool_call_id and result_tool_call_id and tool_call_id != result_tool_call_id:
        log_debug(
            f"[Reorder] ID mismatch: tool_call_id={tool_call_id}, "
            f"result_tool_call_id={result_tool_call_id}",
            context="tool_calls",
        )


# ---------------------------------------------------------------------------
# Core reordering
# ---------------------------------------------------------------------------


def _create_sequential_pairs(
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
    base_content: str,
) -> list[dict[str, Any]]:
    """Convert parallel tool calls into sequential call-result pairs.

    Args:
        tool_calls: List of tool calls from the assistant message.
        tool_results: List of corresponding tool results.
        base_content: Original content from the assistant message.

    Returns:
        List of alternating assistant and tool messages.
    """
    sequential: list[dict[str, Any]] = []
    result_map = _create_tool_result_mapping(tool_results)

    for idx, tool_call in enumerate(tool_calls):
        result, match_type = _find_matching_tool_result(
            tool_call, result_map, tool_results, idx
        )
        if result is None:
            continue

        _verify_id_alignment(tool_call, result)

        # Create individual assistant message with a single tool call
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": base_content if idx == 0 else "",
            "tool_calls": [tool_call],
        }
        sequential.append(assistant_msg)
        sequential.append(result)

        log_debug(
            f"[Reorder] Created call-result pair {idx + 1}/{len(tool_calls)} "
            f"(ID: {tool_call.get('id')} -> {result.get('tool_call_id')}, "
            f"match: {match_type})",
            context="tool_calls",
        )

    return sequential


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reorder_parallel_tool_calls(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reorder parallel tool calls into sequential call-result pairs.

    Transforms messages like::

        [user, assistant(tool_call_1, tool_call_2), tool_result_1, tool_result_2]

    into::

        [user, assistant(tool_call_1), tool_result_1,
               assistant(tool_call_2), tool_result_2]

    Messages that do not contain parallel tool calls are passed through
    unchanged.

    Args:
        messages: List of message dictionaries (OpenAI Chat format).

    Returns:
        Transformed message list with sequential tool calls.
    """
    transformed: list[dict[str, Any]] = []
    i = 0

    while i < len(messages):
        message = messages[i]

        if is_parallel_tool_call_message(message):
            n_calls = len(message["tool_calls"])
            log_warning(
                f"[Reorder] Found assistant message with {n_calls} parallel tool calls",
                context="tool_calls",
            )

            tool_results, next_index = collect_tool_results(messages, i + 1)

            if len(tool_results) != n_calls:
                log_warning(
                    f"[Reorder] Mismatch: {n_calls} tool calls but "
                    f"{len(tool_results)} tool results — skipping reorder",
                    context="tool_calls",
                )
                transformed.append(message)
                i += 1
                continue

            pairs = _create_sequential_pairs(
                message["tool_calls"],
                tool_results,
                message.get("content", "") or "",
            )
            transformed.extend(pairs)

            log_warning(
                f"[Reorder] Converted {n_calls} parallel tool calls "
                f"to {len(pairs) // 2} sequential pairs",
                context="tool_calls",
            )

            i = next_index
        else:
            transformed.append(message)
            i += 1

    if len(transformed) != len(messages):
        log_warning(
            f"[Reorder] Transformed {len(messages)} messages "
            f"into {len(transformed)} messages",
            context="tool_calls",
        )

    return transformed
