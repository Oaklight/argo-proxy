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
    in the text response as Python dict-like strings. It uses a candidate-end
    position strategy with progressive parsing and repair heuristics to handle
    malformed strings (e.g., unescaped newlines, double-escaped quotes, extra
    closing braces).
    """

    # Pattern to detect the start of a leaked tool call
    LEAKED_TOOL_PATTERN = re.compile(r"\{'id':\s*'toolu_")

    def __init__(self):
        pass

    @staticmethod
    def _try_parse_candidate(candidate_str: str) -> Optional[Dict[str, Any]]:
        """
        Try to parse a candidate string as a Python dict literal.

        First attempts a direct ``ast.literal_eval``.  If that fails, applies
        a series of repair strategies to handle common malformations produced
        by Claude models.

        Repair strategies:
            1. Fix unescaped newlines (``\\n`` → ``\\\\n``).
            2. Fix double-escaped single quotes (``\\\\'`` → ``\\'``).
            3. Combination of strategies 1 + 2.
            4. Fix extra closing braces before ``'name'``/``'type'`` keys.
            5. Combination of strategies 1 + 4.

        Args:
            candidate_str: The raw candidate string to parse.

        Returns:
            Parsed dict if successful and contains required keys, else None.
        """
        # Direct attempt
        try:
            result = ast.literal_eval(candidate_str)
            if isinstance(result, dict) and "id" in result and "name" in result:
                return result
        except (ValueError, SyntaxError):
            pass

        # Build repair candidates
        s1 = re.sub(r"(?<!\\)\\n", r"\\\\n", candidate_str)
        s2 = candidate_str.replace(r"\\'", r"\'")
        s3 = s1.replace(r"\\'", r"\'")
        s4 = re.sub(
            r"\}\},[ \n\r]*?('name'|\"name\"|'type'|\"type\")",
            r"}, \1",
            candidate_str,
        )
        s5 = re.sub(
            r"\}\},[ \n\r]*?('name'|\"name\"|'type'|\"type\")",
            r"}, \1",
            s1,
        )

        for repaired_str in (s1, s2, s3, s4, s5):
            try:
                result = ast.literal_eval(repaired_str)
                if isinstance(result, dict) and "id" in result and "name" in result:
                    return result
            except (ValueError, SyntaxError):
                continue

        return None

    def extract_single_leaked_tool(
        self, text: str, start_idx: int
    ) -> Optional[LeakedToolCall]:
        """
        Extract a single leaked tool call starting at the given index.

        Uses a candidate-end strategy: finds all ``}`` positions after
        ``start_idx``, then tries to parse progressively longer substrings
        until a valid tool-call dict is obtained (with repair fallbacks).

        Args:
            text: The text containing the leaked tool call.
            start_idx: The starting index of the tool call (pointing to ``{``).

        Returns:
            LeakedToolCall object if successful, None otherwise.
        """
        tail = text[start_idx:]
        candidate_ends = [m.start() + 1 for m in re.finditer(r"}", tail)]

        if not candidate_ends:
            log_warning(
                "No closing brace found after leaked tool start",
                context="LeakedToolParser",
            )
            return None

        for end_rel in candidate_ends:
            candidate_str = tail[:end_rel]
            leaked_dict = self._try_parse_candidate(candidate_str)

            if leaked_dict is None:
                continue

            # Validate tool ID format
            tool_id = leaked_dict.get("id", "")
            if not isinstance(tool_id, str) or not tool_id.startswith("toolu_"):
                log_warning(
                    f"Invalid tool ID format: {tool_id}",
                    context="LeakedToolParser",
                )
                continue

            end_idx = start_idx + end_rel
            log_debug(
                f"Parsed leaked tool at [{start_idx}:{end_idx}]: "
                f"{candidate_str[:50]}...",
                context="LeakedToolParser",
            )

            return LeakedToolCall(
                id=tool_id,
                name=leaked_dict.get("name", ""),
                input=leaked_dict.get("input", {}),
                type=leaked_dict.get("type", "tool_use"),
                raw_string=candidate_str,
                start_index=start_idx,
                end_index=end_idx,
            )

        log_warning(
            f"Failed to parse leaked tool string after trying "
            f"{len(candidate_ends)} candidate endings",
            context="LeakedToolParser",
        )
        log_debug(
            f"Leaked string start was: {tail[:200]}...",
            context="LeakedToolParser",
        )
        return None

    def extract_all_leaked_tools(self, text: str) -> Tuple[List[LeakedToolCall], str]:
        """
        Extract all leaked tool calls from text and return cleaned text.

        This method finds ALL leaked tool calls in the text, not just the first
        one.  It removes the leaked tool call strings from the text content.
        When a leaked tool pattern cannot be parsed, it logs a warning and
        continues searching for subsequent leaked tools instead of stopping.

        Args:
            text: The text content to search.

        Returns:
            Tuple of (list of LeakedToolCall objects, cleaned text content).
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
                # Couldn't parse this one — skip past the pattern match to
                # avoid an infinite loop and continue searching for more.
                log_warning(
                    "Found unparseable leaked tool pattern, skipping to "
                    "search for more",
                    context="LeakedToolParser",
                )
                cleaned_text = (
                    cleaned_text[:start_idx]
                    + "[UNPARSEABLE_TOOL]"
                    + cleaned_text[match.end() :]
                )

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
