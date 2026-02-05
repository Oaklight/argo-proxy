"""
Leaked Tool Call Parser for Claude/Anthropic models.

This module handles the detection and extraction of "leaked" tool calls that appear
in text content instead of being properly structured in the tool_calls array.

This is a known issue with some Claude models where tool calls are sometimes
embedded in the text response as Python dict-like strings instead of being
returned in the proper tool_calls structure.

Example of a leaked tool call in text:
    "Let me search for that.{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {'query': 'test'}, 'name': 'search', 'type': 'tool_use'}"
"""

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logging import log_debug, log_warning


@dataclass
class LeakedToolCall:
    """Represents a leaked tool call extracted from text content."""

    id: str
    name: str
    input: Dict[str, Any]
    type: str = "tool_use"
    raw_string: str = ""
    start_index: int = 0
    end_index: int = 0


class LeakedToolParser:
    """
    Parser for extracting leaked tool calls from text content.

    This parser handles the case where Claude models embed tool calls directly
    in the text response as Python dict-like strings. It uses quote-aware brace
    counting to correctly handle nested structures and strings containing braces.
    """

    # Pattern to detect the start of a leaked tool call
    LEAKED_TOOL_PATTERN = re.compile(r"\{'id':\s*'toolu_")

    def __init__(self):
        pass

    def find_balanced_dict_end(
        self, text: str, start_idx: int
    ) -> Tuple[int, Optional[str]]:
        """
        Find the end index of a balanced dictionary starting at start_idx.

        Uses quote-aware brace counting to handle:
        - Nested dictionaries and lists
        - Strings containing braces (e.g., code snippets)
        - Both single and double quotes

        Args:
            text: The text to search in
            start_idx: The starting index (should point to '{')

        Returns:
            Tuple of (end_index, error_message)
            - end_index is -1 if no balanced end found
            - error_message is None on success
        """
        if start_idx >= len(text) or text[start_idx] != "{":
            return -1, "Start index does not point to '{'"

        balance = 0
        in_string = False
        string_char: Optional[str] = None
        prev_char: Optional[str] = None

        for i, char in enumerate(text[start_idx:], start=start_idx):
            # Track string state (handle both ' and " quotes)
            if char in ('"', "'") and prev_char != "\\":
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None

            # Only count braces when NOT inside a string
            if not in_string:
                if char == "{":
                    balance += 1
                elif char == "}":
                    balance -= 1
                if balance == 0:
                    return i + 1, None

            prev_char = char

        return -1, f"Unbalanced braces: balance={balance}, in_string={in_string}"

    def extract_single_leaked_tool(
        self, text: str, start_idx: int
    ) -> Optional[LeakedToolCall]:
        """
        Extract a single leaked tool call starting at the given index.

        Args:
            text: The text containing the leaked tool call
            start_idx: The starting index of the tool call

        Returns:
            LeakedToolCall object if successful, None otherwise
        """
        end_idx, error = self.find_balanced_dict_end(text, start_idx)

        if end_idx == -1:
            log_warning(
                f"Failed to find balanced dict end: {error}",
                context="LeakedToolParser",
            )
            return None

        leaked_str = text[start_idx:end_idx]

        try:
            # Parse the Python dict-like string
            leaked_dict = ast.literal_eval(leaked_str)

            # Validate required fields
            if not isinstance(leaked_dict, dict):
                log_warning(
                    f"Leaked tool is not a dict: {type(leaked_dict)}",
                    context="LeakedToolParser",
                )
                return None

            tool_id = leaked_dict.get("id", "")
            if not tool_id.startswith("toolu_"):
                log_warning(
                    f"Invalid tool ID format: {tool_id}",
                    context="LeakedToolParser",
                )
                return None

            return LeakedToolCall(
                id=tool_id,
                name=leaked_dict.get("name", ""),
                input=leaked_dict.get("input", {}),
                type=leaked_dict.get("type", "tool_use"),
                raw_string=leaked_str,
                start_index=start_idx,
                end_index=end_idx,
            )

        except (ValueError, SyntaxError) as e:
            log_warning(
                f"Failed to parse leaked tool string: {e}",
                context="LeakedToolParser",
            )
            log_debug(
                f"Leaked string was: {leaked_str[:200]}...",
                context="LeakedToolParser",
            )
            return None

    def extract_all_leaked_tools(self, text: str) -> Tuple[List[LeakedToolCall], str]:
        """
        Extract all leaked tool calls from text and return cleaned text.

        This method finds ALL leaked tool calls in the text, not just the first one.
        It removes the leaked tool call strings from the text content.

        Args:
            text: The text content to search

        Returns:
            Tuple of (list of LeakedToolCall objects, cleaned text content)
        """
        leaked_tools: List[LeakedToolCall] = []
        cleaned_text = text

        # Keep searching for leaked tools until none are found
        while True:
            match = self.LEAKED_TOOL_PATTERN.search(cleaned_text)
            if not match:
                break

            start_idx = match.start()
            leaked_tool = self.extract_single_leaked_tool(cleaned_text, start_idx)

            if leaked_tool:
                leaked_tools.append(leaked_tool)
                # Remove the leaked tool from text
                cleaned_text = (
                    cleaned_text[: leaked_tool.start_index]
                    + cleaned_text[leaked_tool.end_index :]
                )
                log_warning(
                    f"Extracted leaked tool: {leaked_tool.name} (id={leaked_tool.id})",
                    context="LeakedToolParser",
                )
            else:
                # Couldn't parse this one, skip past it to avoid infinite loop
                # Move past the pattern match to continue searching
                cleaned_text = (
                    cleaned_text[:start_idx]
                    + "[UNPARSEABLE_TOOL]"
                    + cleaned_text[match.end() :]
                )
                log_warning(
                    "Found unparseable leaked tool pattern, skipping",
                    context="LeakedToolParser",
                )
                break  # Stop on error to avoid infinite loop

        return leaked_tools, cleaned_text

    def to_anthropic_format(self, leaked_tool: LeakedToolCall) -> Dict[str, Any]:
        """
        Convert a LeakedToolCall to Anthropic tool_use format.

        Args:
            leaked_tool: The LeakedToolCall to convert

        Returns:
            Dict in Anthropic tool_use format
        """
        return {
            "id": leaked_tool.id,
            "name": leaked_tool.name,
            "input": leaked_tool.input,
            "type": leaked_tool.type,
        }


def parse_anthropic_content_array(
    raw_content: Any,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Parse Anthropic content which can be a string OR an array of content blocks.

    Anthropic responses can have content in two formats:
    1. Simple string: "Here is the response..."
    2. Array format: [{"type": "text", "text": "..."}, {"type": "tool_use", ...}]

    This function normalizes both formats and extracts tool_use blocks.

    Args:
        raw_content: The raw content from Anthropic response

    Returns:
        Tuple of (text_content, list of tool_use blocks)
    """
    if isinstance(raw_content, str):
        return raw_content, []

    if not isinstance(raw_content, list):
        return str(raw_content) if raw_content else "", []

    text_parts: List[str] = []
    tool_use_blocks: List[Dict[str, Any]] = []

    for block in raw_content:
        if isinstance(block, dict):
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_use_blocks.append(block)
        elif isinstance(block, str):
            text_parts.append(block)

    return "".join(text_parts), tool_use_blocks


def extract_leaked_tool_calls(
    text_content: str,
    existing_tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Extract leaked tool calls from text content.

    This is the main entry point for leaked tool call extraction.
    It handles the case where Claude embeds tool calls in text content.

    Args:
        text_content: The text content to search for leaked tools
        existing_tool_calls: Optional list of already-extracted tool calls

    Returns:
        Tuple of (combined tool calls list, cleaned text content)
    """
    parser = LeakedToolParser()
    leaked_tools, cleaned_text = parser.extract_all_leaked_tools(text_content)

    # Convert leaked tools to Anthropic format
    leaked_tool_dicts = [parser.to_anthropic_format(lt) for lt in leaked_tools]

    # Combine with existing tool calls
    all_tool_calls = list(existing_tool_calls) if existing_tool_calls else []
    all_tool_calls.extend(leaked_tool_dicts)

    if leaked_tools:
        log_warning(
            f"Extracted {len(leaked_tools)} leaked tool calls from text content",
            context="LeakedToolParser",
        )

    return all_tool_calls, cleaned_text
