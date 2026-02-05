"""
Tests for the leaked tool parser module.
"""

from argoproxy.tool_calls.leaked_tool_parser import (
    LeakedToolCall,
    LeakedToolParser,
    extract_leaked_tool_calls,
    parse_anthropic_content_array,
)


class TestLeakedToolParser:
    """Tests for LeakedToolParser class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = LeakedToolParser()

    def test_find_balanced_dict_end_simple(self):
        """Test finding end of a simple dictionary."""
        text = "{'id': 'toolu_123', 'name': 'test'}"
        end_idx, error = self.parser.find_balanced_dict_end(text, 0)
        assert error is None
        assert end_idx == len(text)

    def test_find_balanced_dict_end_nested(self):
        """Test finding end of a nested dictionary."""
        text = "{'id': 'toolu_123', 'input': {'key': 'value'}}"
        end_idx, error = self.parser.find_balanced_dict_end(text, 0)
        assert error is None
        assert end_idx == len(text)

    def test_find_balanced_dict_end_with_braces_in_string(self):
        """Test handling braces inside strings."""
        text = "{'id': 'toolu_123', 'input': {'code': 'def foo(): { return 1 }'}}"
        end_idx, error = self.parser.find_balanced_dict_end(text, 0)
        assert error is None
        assert end_idx == len(text)

    def test_find_balanced_dict_end_with_escaped_quotes(self):
        """Test handling escaped quotes."""
        text = r"{'id': 'toolu_123', 'input': {'text': 'He said \"hello\"'}}"
        end_idx, error = self.parser.find_balanced_dict_end(text, 0)
        assert error is None
        assert end_idx == len(text)

    def test_find_balanced_dict_end_unbalanced(self):
        """Test handling unbalanced braces."""
        text = "{'id': 'toolu_123', 'input': {'key': 'value'"
        end_idx, error = self.parser.find_balanced_dict_end(text, 0)
        assert end_idx == -1
        assert error is not None

    def test_find_balanced_dict_end_with_prefix(self):
        """Test finding dict end with text before it."""
        text = "Some text before {'id': 'toolu_123', 'name': 'test'} and after"
        start_idx = text.find("{")
        end_idx, error = self.parser.find_balanced_dict_end(text, start_idx)
        assert error is None
        assert text[start_idx:end_idx] == "{'id': 'toolu_123', 'name': 'test'}"

    def test_extract_single_leaked_tool(self):
        """Test extracting a single leaked tool call."""
        text = "{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {'query': 'test'}, 'name': 'search', 'type': 'tool_use'}"
        leaked_tool = self.parser.extract_single_leaked_tool(text, 0)

        assert leaked_tool is not None
        assert leaked_tool.id == "toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH"
        assert leaked_tool.name == "search"
        assert leaked_tool.input == {"query": "test"}
        assert leaked_tool.type == "tool_use"

    def test_extract_single_leaked_tool_invalid_id(self):
        """Test that invalid tool IDs are rejected."""
        text = "{'id': 'invalid_123', 'name': 'test'}"
        leaked_tool = self.parser.extract_single_leaked_tool(text, 0)
        assert leaked_tool is None

    def test_extract_all_leaked_tools_single(self):
        """Test extracting a single leaked tool from text."""
        text = "Let me search for that.{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {'query': 'test'}, 'name': 'search', 'type': 'tool_use'}"
        leaked_tools, cleaned_text = self.parser.extract_all_leaked_tools(text)

        assert len(leaked_tools) == 1
        assert leaked_tools[0].name == "search"
        assert cleaned_text == "Let me search for that."

    def test_extract_all_leaked_tools_multiple(self):
        """Test extracting multiple leaked tools from text."""
        text = (
            "First tool{'id': 'toolu_vrtx_01AAA', 'input': {}, 'name': 'tool1', 'type': 'tool_use'}"
            "Second tool{'id': 'toolu_vrtx_01BBB', 'input': {}, 'name': 'tool2', 'type': 'tool_use'}"
        )
        leaked_tools, cleaned_text = self.parser.extract_all_leaked_tools(text)

        assert len(leaked_tools) == 2
        assert leaked_tools[0].name == "tool1"
        assert leaked_tools[1].name == "tool2"
        assert cleaned_text == "First toolSecond tool"

    def test_extract_all_leaked_tools_none(self):
        """Test when no leaked tools are present."""
        text = "This is just regular text without any tool calls."
        leaked_tools, cleaned_text = self.parser.extract_all_leaked_tools(text)

        assert len(leaked_tools) == 0
        assert cleaned_text == text

    def test_extract_all_leaked_tools_with_code_braces(self):
        """Test handling code with braces in tool input."""
        text = "{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {'code': 'function test() { return { a: 1 }; }'}, 'name': 'execute', 'type': 'tool_use'}"
        leaked_tools, cleaned_text = self.parser.extract_all_leaked_tools(text)

        assert len(leaked_tools) == 1
        assert leaked_tools[0].name == "execute"
        assert "function test()" in leaked_tools[0].input["code"]

    def test_to_anthropic_format(self):
        """Test converting LeakedToolCall to Anthropic format."""
        leaked_tool = LeakedToolCall(
            id="toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH",
            name="search",
            input={"query": "test"},
            type="tool_use",
        )
        result = self.parser.to_anthropic_format(leaked_tool)

        assert result == {
            "id": "toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH",
            "name": "search",
            "input": {"query": "test"},
            "type": "tool_use",
        }


class TestParseAnthropicContentArray:
    """Tests for parse_anthropic_content_array function."""

    def test_string_content(self):
        """Test parsing simple string content."""
        text, tools = parse_anthropic_content_array("Hello, world!")
        assert text == "Hello, world!"
        assert tools == []

    def test_empty_content(self):
        """Test parsing empty content."""
        text, tools = parse_anthropic_content_array("")
        assert text == ""
        assert tools == []

    def test_none_content(self):
        """Test parsing None content."""
        text, tools = parse_anthropic_content_array(None)
        assert text == ""
        assert tools == []

    def test_array_with_text_only(self):
        """Test parsing array with only text blocks."""
        content = [
            {"type": "text", "text": "Hello, "},
            {"type": "text", "text": "world!"},
        ]
        text, tools = parse_anthropic_content_array(content)
        assert text == "Hello, world!"
        assert tools == []

    def test_array_with_tool_use_only(self):
        """Test parsing array with only tool_use blocks."""
        content = [
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "search",
                "input": {"query": "test"},
            }
        ]
        text, tools = parse_anthropic_content_array(content)
        assert text == ""
        assert len(tools) == 1
        assert tools[0]["name"] == "search"

    def test_array_with_mixed_content(self):
        """Test parsing array with mixed text and tool_use blocks."""
        content = [
            {"type": "text", "text": "Let me search for that."},
            {
                "type": "tool_use",
                "id": "toolu_123",
                "name": "search",
                "input": {"query": "test"},
            },
        ]
        text, tools = parse_anthropic_content_array(content)
        assert text == "Let me search for that."
        assert len(tools) == 1
        assert tools[0]["name"] == "search"

    def test_array_with_string_elements(self):
        """Test parsing array with string elements."""
        content = ["Hello, ", "world!"]
        text, tools = parse_anthropic_content_array(content)
        assert text == "Hello, world!"
        assert tools == []


class TestExtractLeakedToolCalls:
    """Tests for extract_leaked_tool_calls function."""

    def test_extract_with_no_existing_tools(self):
        """Test extracting leaked tools with no existing tool calls."""
        text = "{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {'query': 'test'}, 'name': 'search', 'type': 'tool_use'}"
        tools, cleaned = extract_leaked_tool_calls(text)

        assert len(tools) == 1
        assert tools[0]["name"] == "search"
        assert cleaned == ""

    def test_extract_with_existing_tools(self):
        """Test extracting leaked tools with existing tool calls."""
        text = "{'id': 'toolu_vrtx_01BBB', 'input': {}, 'name': 'tool2', 'type': 'tool_use'}"
        existing = [
            {"id": "toolu_vrtx_01AAA", "name": "tool1", "input": {}, "type": "tool_use"}
        ]
        tools, cleaned = extract_leaked_tool_calls(text, existing)

        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"  # Existing tool first
        assert tools[1]["name"] == "tool2"  # Leaked tool second

    def test_extract_no_leaked_tools(self):
        """Test when no leaked tools are present."""
        text = "This is just regular text."
        tools, cleaned = extract_leaked_tool_calls(text)

        assert len(tools) == 0
        assert cleaned == text

    def test_extract_preserves_text_around_tools(self):
        """Test that text around leaked tools is preserved."""
        text = "Before{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {}, 'name': 'test', 'type': 'tool_use'}After"
        tools, cleaned = extract_leaked_tool_calls(text)

        assert len(tools) == 1
        assert cleaned == "BeforeAfter"
