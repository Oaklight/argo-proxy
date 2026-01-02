"""
google_helpers.py
-----------------

Helper functions for Google/Gemini tool call processing.
This module contains utility functions to support the conversion of parallel
tool calls to sequential format for Gemini API compatibility, as well as
conversion of Gemini's text-based tool call format to OpenAI format.
"""

import json
import re
from typing import Any, Dict, List, Tuple, Union

from loguru import logger


class GeminiToolCallConverter:
    """Gemini tool call converter

    Converts Gemini model's <tool_call> text format to standard OpenAI tool_calls format.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        # Pattern to match JSON content within <tool_call> tags
        self.tool_call_pattern = re.compile(
            r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL | re.MULTILINE
        )

    def is_gemini_model(self, model_name: str) -> bool:
        """Check if the model is a Gemini model"""
        if not model_name:
            return False

        model_lower = model_name.lower()
        return any(keyword in model_lower for keyword in ["gemini", "bison", "palm"])

    def has_tool_calls_in_content(self, content: str) -> bool:
        """Check if content contains tool call tags"""
        if not content:
            return False
        return bool(self.tool_call_pattern.search(content))

    def extract_tool_calls_from_content(self, content: str) -> List[Dict[str, Any]]:
        """Extract tool calls from content and convert to OpenAI format"""
        if not content:
            return []

        tool_calls = []
        matches = self.tool_call_pattern.findall(content)

        for i, match in enumerate(matches):
            try:
                # Parse JSON content
                tool_data = json.loads(match.strip())

                # Convert to OpenAI format
                tool_call = {
                    "id": f"call_gemini_{i}_{abs(hash(match)) % 100000}",
                    "type": "function",
                    "function": {
                        "name": tool_data.get("name", ""),
                        "arguments": json.dumps(tool_data.get("arguments", {})),
                    },
                }
                tool_calls.append(tool_call)

                if self.verbose:
                    logger.debug(
                        f"Converted Gemini tool call: {tool_call['function']['name']}"
                    )

            except json.JSONDecodeError as e:
                if self.verbose:
                    logger.warning(f"Failed to parse Gemini tool call JSON: {e}")
                    logger.warning(f"Raw content: {match}")
                continue
            except Exception as e:
                if self.verbose:
                    logger.warning(f"Error processing Gemini tool call: {e}")
                continue

        return tool_calls

    def remove_tool_call_tags(self, content: str) -> str:
        """Remove tool call tags from content, preserving other text"""
        if not content:
            return ""
        return self.tool_call_pattern.sub("", content).strip()

    def convert_response_data(
        self, response_data: Dict[str, Any], model_name: str = ""
    ) -> Dict[str, Any]:
        """Convert Gemini tool call format in response data

        Args:
            response_data: Original response data dictionary
            model_name: Model name, used to determine if conversion is needed

        Returns:
            Converted response data
        """
        # Check if conversion is needed
        if not self.is_gemini_model(model_name):
            return response_data

        if not response_data.get("choices"):
            return response_data

        converted = False

        for choice in response_data["choices"]:
            message = choice.get("message", {})
            content = message.get("content", "")

            # Skip conversion if tool_calls already exist
            if message.get("tool_calls"):
                continue

            # Check if content contains tool calls
            if self.has_tool_calls_in_content(content):
                tool_calls = self.extract_tool_calls_from_content(content)

                if tool_calls:
                    message["tool_calls"] = tool_calls
                    converted = True

                    # Clean tool call tags from content
                    cleaned_content = self.remove_tool_call_tags(content)
                    if cleaned_content:
                        message["content"] = cleaned_content
                    else:
                        # Set to None if no content remains (OpenAI standard)
                        message["content"] = None

                    if self.verbose:
                        logger.info(
                            f"Converted {len(tool_calls)} Gemini tool calls to OpenAI format"
                        )

        if converted and self.verbose:
            logger.info("Successfully converted Gemini response to OpenAI format")

        return response_data


def is_parallel_tool_call_message(message: Dict[str, Any]) -> bool:
    """Check if a message contains multiple tool calls (parallel tool calls)."""
    return (
        message.get("role") == "assistant"
        and message.get("tool_calls")
        and len(message["tool_calls"]) > 1
    )


def collect_tool_results(
    messages: List[Dict[str, Any]], start_index: int
) -> Tuple[List[Dict[str, Any]], int]:
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
    tool_results: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Create a mapping from tool_call_id to tool_result for efficient lookup."""
    tool_result_map = {}
    for tool_result in tool_results:
        tool_call_id = tool_result.get("tool_call_id")
        if tool_call_id:
            tool_result_map[tool_call_id] = tool_result
    return tool_result_map


def find_matching_tool_result(
    tool_call: Dict[str, Any],
    tool_result_map: Dict[str, Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    index: int,
) -> Tuple[Union[Dict[str, Any], None], str]:
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
        logger.warning(
            f"[Google Sequential] Found matching result for tool_call_id: {tool_call_id}"
        )
        return tool_result_map[tool_call_id], "id"

    # Fallback to positional matching
    if index < len(tool_results):
        logger.warning(
            f"[Google Sequential] Using positional matching for tool call {index + 1}"
        )
        return tool_results[index], "position"

    # No match found
    logger.error(
        f"[Google Sequential] No corresponding result found for tool call {index + 1}"
    )
    return None, "none"


def verify_id_alignment(tool_call: Dict[str, Any], tool_result: Dict[str, Any]) -> None:
    """Verify that tool call and result IDs are aligned and log any mismatches."""
    tool_call_id = tool_call.get("id")
    result_tool_call_id = tool_result.get("tool_call_id")

    if tool_call_id and result_tool_call_id and tool_call_id != result_tool_call_id:
        logger.warning(
            f"[Google Sequential] ID mismatch: tool_call_id={tool_call_id}, "
            f"result_tool_call_id={result_tool_call_id}"
        )


def create_sequential_call_result_pairs(
    tool_calls: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    base_content: str,
) -> List[Dict[str, Any]]:
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
        logger.warning(
            f"[Google Sequential] Created call-result pair {idx + 1}/{len(tool_calls)} "
            f"(ID: {tool_call_id} -> {result_tool_call_id}, match: {match_type})"
        )

    return sequential_messages
