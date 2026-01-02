"""
converters.py
-------------

Type conversion module for tool calls between different LLM provider formats.

This module provides conversion functions between OpenAI, Anthropic (Claude),
and Google (Gemini) tool call formats. It handles:

1. Tool definitions (tools parameter)
2. Tool choice specifications (tool_choice parameter)
3. Tool call results (tool_calls in responses)

Usage
=====
>>> from argoproxy.tool_calls.converters import OpenAIToClaudeConverter
>>> converter = OpenAIToClaudeConverter()
>>> claude_tools = converter.convert_tools(openai_tools)
>>> claude_tool_choice = converter.convert_tool_choice(openai_tool_choice)
>>> claude_tool_calls = converter.convert_tool_calls(openai_tool_calls)
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from ..types.function_call import (
    ChatCompletionMessageToolCall,  # OpenAIToolCall,
    ChatCompletionNamedToolChoiceParam,  # OpenAIToolChoiceFunction,
    ChatCompletionToolChoiceOptionParam,  # OpenAIToolChoice,
    # openai types
    ChatCompletionToolParam,  # OpenAITool,
    ToolChoiceAnyParam,  # AnthropicToolChoiceAny,
    ToolChoiceAutoParam,  # AnthropicToolChoiceAuto,
    ToolChoiceNoneParam,  # AnthropicToolChoiceNone,
    ToolChoiceToolParam,  # AnthropicToolChoiceTool,
    # anthropic types
    # claude types
    ToolParam,  # AnthropicTool,  # ClaudeTool,
)
from ..types.function_call import (
    ToolChoiceParam as ClaudeToolChoice,
)
from ..types.function_call import (
    ToolParam as ClaudeTool,
)
from ..types.function_call import (
    ToolUseBlock as ClaudeToolCall,
)

# ======================================================================
# BASE CONVERTER INTERFACE
# ======================================================================


class ToolConverter(ABC):
    """Abstract base class for tool format converters."""

    @abstractmethod
    def convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools from source format to target format."""
        pass

    @abstractmethod
    def convert_tool_choice(
        self, tool_choice: Union[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Convert tool_choice from source format to target format."""
        pass

    @abstractmethod
    def convert_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tool_calls from source format to target format."""
        pass


# ======================================================================
# OPENAI TO Any CONVERTER
# ======================================================================


class OpenAIConverter(ToolConverter):
    def _read_tools(self, tools: List[Dict[str, Any]]) -> List[ChatCompletionToolParam]:
        # assume tools are valid in OpenAI format
        return [ChatCompletionToolParam.model_validate(tool) for tool in tools]

    def _read_tool_choice(
        self, tool_choice: Union[str, Dict[str, Any]]
    ) -> ChatCompletionToolChoiceOptionParam:
        if isinstance(tool_choice, str):
            return tool_choice
        else:
            return ChatCompletionNamedToolChoiceParam.model_validate(tool_choice)

    def _read_tool_calls(
        self, tool_calls: List[Dict[str, Any]]
    ) -> List[ChatCompletionMessageToolCall]:
        return [
            ChatCompletionMessageToolCall.model_validate(tool_call)
            for tool_call in tool_calls
        ]

    def convert_tools(
        self,
        tools: List[Dict[str, Any]],
        target_format: Literal["anthropic", "google"],
    ) -> List[Dict[str, Any]]:
        openai_tools = self._read_tools(tools)

        if target_format == "anthropic":
            anthropic_tools = []

            for tool in openai_tools:
                new_tool = ToolParam(
                    name=tool.function.name,
                    description=tool.function.description,
                    input_schema=tool.function.parameters,
                )
                anthropic_tools.append(new_tool.model_dump())

            return anthropic_tools

        elif target_format == "google":
            # TODO: implement Google tool conversion
            pass
        else:
            raise ValueError(f"Unsupported target format: {target_format}")

    def convert_tool_choice(
        self,
        tool_choice: Union[str, Dict[str, Any]],
        *,
        target_format: Literal["anthropic", "google"],
    ) -> Optional[Dict[str, Any]]:
        openai_tool_choice = self._read_tool_choice(tool_choice)

        if target_format == "anthropic":
            if openai_tool_choice == "auto":
                return ToolChoiceAutoParam().model_dump()
            elif openai_tool_choice == "none":
                return ToolChoiceNoneParam().model_dump()
            elif openai_tool_choice == "required":
                return ToolChoiceAnyParam().model_dump()
            elif isinstance(openai_tool_choice, dict):
                return ToolChoiceToolParam(
                    name=openai_tool_choice["function"]["name"]
                ).model_dump()


class OpenAIToClaudeConverter(ToolConverter):
    """Converter for OpenAI to Anthropic Claude tool formats."""

    def convert_tools(self, openai_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert OpenAI tools format to Claude tools format.

        Args:
            openai_tools: List of OpenAI tool definitions

        Returns:
            List of Claude tool definitions as dictionaries
        """
        claude_tools = []

        for tool in openai_tools:
            if tool.get("type") == "function":
                function = tool.get("function", {})

                claude_tool = ClaudeTool(
                    name=function.get("name", ""),
                    description=function.get("description", ""),
                    input_schema=function.get("parameters", {}),
                )
                claude_tools.append(claude_tool.model_dump())

        return claude_tools

    def convert_tool_choice(
        self, openai_tool_choice: Union[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Convert OpenAI tool_choice format to Claude tool_choice format.

        Args:
            openai_tool_choice: OpenAI tool choice specification

        Returns:
            Claude tool choice specification as dictionary
        """
        if openai_tool_choice is None:
            return None

        # Handle string values
        if isinstance(openai_tool_choice, str):
            if openai_tool_choice == "none":
                from ..types.function_call import ToolChoiceNoneParam

                return ToolChoiceNoneParam().model_dump()
            elif openai_tool_choice == "auto":
                from ..types.function_call import ToolChoiceAutoParam

                return ToolChoiceAutoParam(disable_parallel_tool_use=False).model_dump()
            elif openai_tool_choice == "required":
                from ..types.function_call import ToolChoiceAnyParam

                return ToolChoiceAnyParam(disable_parallel_tool_use=False).model_dump()

        # Handle dict values (specific function selection)
        elif isinstance(openai_tool_choice, dict):
            if openai_tool_choice.get("type") == "function":
                function_name = openai_tool_choice.get("function", {}).get("name")
                if function_name:
                    from ..types.function_call import ToolChoiceToolParam

                    return ToolChoiceToolParam(
                        name=function_name, disable_parallel_tool_use=False
                    ).model_dump()

        # Default fallback
        from ..types.function_call import ToolChoiceAutoParam

        return ToolChoiceAutoParam(disable_parallel_tool_use=False).model_dump()

    def convert_tool_calls(
        self, openai_tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert OpenAI tool_calls format to Claude tool_calls format.

        Args:
            openai_tool_calls: List of OpenAI tool call elements

        Returns:
            List of Claude tool call elements as dictionaries
        """
        claude_tool_calls = []

        for tool_call in openai_tool_calls:
            if tool_call.get("type") == "function":
                function = tool_call.get("function", {})

                # Parse arguments from JSON string to object
                arguments_str = function.get("arguments", "{}")
                try:
                    arguments_obj = (
                        json.loads(arguments_str)
                        if isinstance(arguments_str, str)
                        else arguments_str
                    )
                except json.JSONDecodeError:
                    arguments_obj = {}

                claude_tool_call = ClaudeToolCall(
                    id=tool_call.get("id", ""),
                    name=function.get("name", ""),
                    input=arguments_obj,
                )
                claude_tool_calls.append(claude_tool_call.model_dump())

        return claude_tool_calls

    def convert_tools_and_choice(
        self,
        tools: List[Dict[str, Any]],
        tool_choice: Union[str, Dict[str, Any]] = "auto",
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Convenience method to convert both tools and tool_choice together.

        Args:
            tools: List of OpenAI tool definitions
            tool_choice: OpenAI tool choice specification

        Returns:
            Tuple of (claude_tools, claude_tool_choice)
        """
        claude_tools = self.convert_tools(tools)
        claude_tool_choice = self.convert_tool_choice(tool_choice)
        return claude_tools, claude_tool_choice


# ======================================================================
# CLAUDE TO OPENAI CONVERTER
# ======================================================================


class ClaudeToOpenAIConverter(ToolConverter):
    """Converter for Anthropic Claude to OpenAI tool formats."""

    def convert_tools(self, claude_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert Claude tools format to OpenAI tools format.

        Args:
            claude_tools: List of Claude tool definitions

        Returns:
            List of OpenAI tool definitions as dictionaries
        """
        openai_tools = []

        for tool in claude_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            }
            openai_tools.append(openai_tool)

        return openai_tools

    def convert_tool_choice(
        self, claude_tool_choice: Union[str, Dict[str, Any]]
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """
        Convert Claude tool_choice format to OpenAI tool_choice format.

        Args:
            claude_tool_choice: Claude tool choice specification

        Returns:
            OpenAI tool choice specification
        """
        if claude_tool_choice is None:
            return None

        # Handle dict values (Claude format)
        if isinstance(claude_tool_choice, dict):
            choice_type = claude_tool_choice.get("type")

            if choice_type == "auto":
                return "auto"
            elif choice_type == "none":
                return "none"
            elif choice_type == "any":
                return "required"
            elif choice_type == "tool":
                tool_name = claude_tool_choice.get("name")
                if tool_name:
                    return {"type": "function", "function": {"name": tool_name}}

        # Handle string values (fallback)
        elif isinstance(claude_tool_choice, str):
            if claude_tool_choice in ["auto", "none", "required"]:
                return claude_tool_choice

        # Default fallback
        return "auto"

    def convert_tool_calls(
        self, claude_tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert Claude tool_calls format to OpenAI tool_calls format.

        Args:
            claude_tool_calls: List of Claude tool call elements

        Returns:
            List of OpenAI tool call elements as dictionaries
        """
        openai_tool_calls = []

        for tool_call in claude_tool_calls:
            # Handle both Claude ToolUseBlock format and dict format
            if tool_call.get("type") == "tool_use" or "name" in tool_call:
                # Convert arguments from object to JSON string
                input_data = tool_call.get("input", {})
                arguments_str = (
                    json.dumps(input_data)
                    if isinstance(input_data, dict)
                    else str(input_data)
                )

                openai_tool_call = {
                    "id": tool_call.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tool_call.get("name", ""),
                        "arguments": arguments_str,
                    },
                }
                openai_tool_calls.append(openai_tool_call)

        return openai_tool_calls

    def convert_tools_and_choice(
        self,
        tools: List[Dict[str, Any]],
        tool_choice: Union[str, Dict[str, Any]] = "auto",
    ) -> Tuple[List[Dict[str, Any]], Optional[Union[str, Dict[str, Any]]]]:
        """
        Convenience method to convert both tools and tool_choice together.

        Args:
            tools: List of Claude tool definitions
            tool_choice: Claude tool choice specification

        Returns:
            Tuple of (openai_tools, openai_tool_choice)
        """
        openai_tools = self.convert_tools(tools)
        openai_tool_choice = self.convert_tool_choice(tool_choice)
        return openai_tools, openai_tool_choice


# ======================================================================
# OPENAI TO GOOGLE CONVERTER
# ======================================================================


class OpenAIToGoogleConverter(ToolConverter):
    """Converter for OpenAI to Google Gemini tool formats."""

    def convert_tools(self, openai_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert OpenAI tools format to Google tools format.

        Args:
            openai_tools: List of OpenAI tool definitions

        Returns:
            List of Google tool definitions as dictionaries
        """
        google_tools = []

        for tool in openai_tools:
            if tool.get("type") == "function":
                function = tool.get("function", {})

                # Google/Gemini tool format: {"name": "...", "description": "...", "parameters": {...}}
                google_tool = {
                    "name": function.get("name", ""),
                    "description": function.get("description", ""),
                    "parameters": function.get("parameters", {}),
                }
                google_tools.append(google_tool)

        return google_tools

    def convert_tool_choice(
        self, openai_tool_choice: Union[str, Dict[str, Any]]
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """
        Convert OpenAI tool_choice format to Google tool_choice format.

        Args:
            openai_tool_choice: OpenAI tool choice specification

        Returns:
            Google tool choice specification as string or dictionary
        """
        if openai_tool_choice is None:
            return None

        # Handle string values
        if isinstance(openai_tool_choice, str):
            if openai_tool_choice == "none":
                return "NONE"
            elif openai_tool_choice == "auto":
                return "AUTO"
            elif openai_tool_choice == "required":
                return "ANY"

        # Handle dict values (specific function selection)
        elif isinstance(openai_tool_choice, dict):
            if openai_tool_choice.get("type") == "function":
                function_name = openai_tool_choice.get("function", {}).get("name")
                if function_name:
                    return {
                        "mode": "FUNCTION_CALLING",
                        "allowed_function_names": [function_name],
                    }

        # Default fallback
        return "AUTO"

    def convert_tool_calls(
        self, openai_tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert OpenAI tool_calls format to Google tool_calls format.

        Args:
            openai_tool_calls: List of OpenAI tool call elements

        Returns:
            List of Google tool call elements as dictionaries
        """
        google_tool_calls = []

        for tool_call in openai_tool_calls:
            if tool_call.get("type") == "function":
                function = tool_call.get("function", {})

                # Parse arguments from JSON string to object
                arguments_str = function.get("arguments", "{}")
                try:
                    arguments_obj = (
                        json.loads(arguments_str)
                        if isinstance(arguments_str, str)
                        else arguments_str
                    )
                except json.JSONDecodeError:
                    arguments_obj = {}

                # Google format: {"id": "call_id", "name": "function_name", "args": {...}}
                google_tool_call = {
                    "id": tool_call.get("id"),
                    "name": function.get("name", ""),
                    "args": arguments_obj,
                }
                google_tool_calls.append(google_tool_call)

        return google_tool_calls

    def convert_tools_and_choice(
        self,
        tools: List[Dict[str, Any]],
        tool_choice: Union[str, Dict[str, Any]] = "auto",
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Convenience method to convert both tools and tool_choice together.

        Args:
            tools: List of OpenAI tool definitions
            tool_choice: OpenAI tool choice specification

        Returns:
            Tuple of (google_tools, google_tool_choice)

        Note:
            TODO: Implement Google/Gemini conversion
        """
        raise NotImplementedError("Google/Gemini conversion not yet implemented")


# ======================================================================
# CONVERTER FACTORY
# ======================================================================


class ConverterFactory:
    """Factory class for creating appropriate converters based on source and target model families."""

    _converters = {
        ("openai", "anthropic"): OpenAIToClaudeConverter,
        ("openai", "google"): OpenAIToGoogleConverter,
        ("anthropic", "openai"): ClaudeToOpenAIConverter,
    }

    @classmethod
    def get_converter(cls, source_family: str, target_family: str) -> ToolConverter:
        """
        Get the appropriate converter for the source and target model families.

        Args:
            source_family: Source model family ("openai", "anthropic", "google")
            target_family: Target model family ("openai", "anthropic", "google")

        Returns:
            Appropriate converter instance

        Raises:
            ValueError: If conversion path is not supported
        """
        converter_key = (source_family, target_family)

        if converter_key not in cls._converters:
            supported = ", ".join([f"{s}->{t}" for s, t in cls._converters.keys()])
            raise ValueError(
                f"Unsupported conversion: {source_family} -> {target_family}. "
                f"Supported conversions: {supported}"
            )

        converter_class = cls._converters[converter_key]
        return converter_class()

    @classmethod
    def get_converter_legacy(cls, target_model_family: str) -> ToolConverter:
        """
        Legacy method for backward compatibility. Assumes OpenAI as source.

        Args:
            target_model_family: Target model family ("anthropic", "google", etc.)

        Returns:
            Appropriate converter instance

        Raises:
            ValueError: If target model family is not supported
        """
        return cls.get_converter("openai", target_model_family)

    @classmethod
    def register_converter(
        cls,
        source_family: str,
        target_family: str,
        converter_class: type[ToolConverter],
    ) -> None:
        """
        Register a new converter for a conversion path.

        Args:
            source_family: Source model family identifier
            target_family: Target model family identifier
            converter_class: Converter class to register
        """
        cls._converters[(source_family, target_family)] = converter_class

    @classmethod
    def list_supported_conversions(cls) -> List[Tuple[str, str]]:
        """
        List all supported conversion paths.

        Returns:
            List of (source_family, target_family) tuples
        """
        return list(cls._converters.keys())

    @classmethod
    def list_supported_families(cls) -> List[str]:
        """
        List all supported model families (both source and target).

        Returns:
            List of unique model family names
        """
        families = set()
        for source, target in cls._converters.keys():
            families.add(source)
            families.add(target)
        return sorted(list(families))


# ======================================================================
# CONVENIENCE FUNCTIONS
# ======================================================================


def convert_openai_to_claude(
    tools: List[Dict[str, Any]],
    tool_choice: Union[str, Dict[str, Any]] = "auto",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to convert OpenAI format to Claude format.

    Args:
        tools: List of OpenAI tool definitions
        tool_choice: OpenAI tool choice specification
        tool_calls: Optional list of OpenAI tool call elements

    Returns:
        Dictionary containing converted Claude format data
    """
    converter = OpenAIToClaudeConverter()

    result = {
        "tools": converter.convert_tools(tools),
        "tool_choice": converter.convert_tool_choice(tool_choice),
    }

    if tool_calls is not None:
        result["tool_calls"] = converter.convert_tool_calls(tool_calls)

    return result


def convert_claude_to_openai(
    tools: List[Dict[str, Any]],
    tool_choice: Union[str, Dict[str, Any]] = "auto",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to convert Claude format to OpenAI format.

    Args:
        tools: List of Claude tool definitions
        tool_choice: Claude tool choice specification
        tool_calls: Optional list of Claude tool call elements

    Returns:
        Dictionary containing converted OpenAI format data
    """
    converter = ClaudeToOpenAIConverter()

    result = {
        "tools": converter.convert_tools(tools),
        "tool_choice": converter.convert_tool_choice(tool_choice),
    }

    if tool_calls is not None:
        result["tool_calls"] = converter.convert_tool_calls(tool_calls)

    return result


def convert_openai_to_google(
    tools: List[Dict[str, Any]],
    tool_choice: Union[str, Dict[str, Any]] = "auto",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to convert OpenAI format to Google format.

    Args:
        tools: List of OpenAI tool definitions
        tool_choice: OpenAI tool choice specification
        tool_calls: Optional list of OpenAI tool call elements

    Returns:
        Dictionary containing converted Google format data

    Note:
        TODO: Implement Google/Gemini conversion
    """
    converter = OpenAIToGoogleConverter()

    result = {
        "tools": converter.convert_tools(tools),
        "tool_choice": converter.convert_tool_choice(tool_choice),
    }

    if tool_calls is not None:
        result["tool_calls"] = converter.convert_tool_calls(tool_calls)

    return result
