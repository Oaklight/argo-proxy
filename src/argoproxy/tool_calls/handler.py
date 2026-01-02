"""
Universal Tool Call Middleware Module

This module provides universal middleware classes for converting tool calls, tool definitions,
and tool choice data between different API formats.

Supported API formats include:
- OpenAI Chat Completions API
- OpenAI Responses API
- Anthropic Claude API
- Google Gemini API (partial support)

Main classes:
- ToolCall: Universal representation of tool call data
- Tool: Universal representation of tool definition data
- ToolChoice: Universal representation of tool choice strategy
- NamedTool: Simple representation of named tools

Usage example:
    # Create tool call from OpenAI format
    tool_call = ToolCall.from_entry(openai_data, api_format="openai-chatcompletion")

    # Convert to Anthropic format
    anthropic_data = tool_call.to_tool_call("anthropic")

    # Serialize to dictionary
    serialized = tool_call.serialize("anthropic")
"""

import json
from typing import Any, Dict, Literal, Union

from pydantic import BaseModel

from ..types.function_call import (
    ChatCompletionMessageToolCall,
    ChatCompletionNamedToolChoiceParam,
    ChatCompletionToolParam,
    Function,
    FunctionDefinition,
    FunctionDefinitionCore,
    FunctionTool,
    ResponseFunctionToolCall,
    ToolChoiceAnyParam,
    ToolChoiceAutoParam,
    ToolChoiceFunctionParam,
    ToolChoiceNoneParam,
    ToolChoiceToolParam,
    ToolParam,
    ToolUseBlock,
)
from ..types.function_call import FunctionCall as GeminiToolCall
from ..types.function_call import FunctionDeclaration as GeminiTool
from ..utils.models import API_FORMATS


class ToolCall(BaseModel):
    """
    Universal tool call middleware class supporting conversion between multiple API formats.

    This class serves as a bridge between different API formats (OpenAI, Anthropic, Google, etc.),
    allowing loading tool call data from any supported format and converting to other formats.

    Attributes:
        id: Unique identifier for the tool call
        name: Name of the function to be called
        arguments: Function arguments stored as JSON string format
    """

    id: str
    """Unique identifier for the tool call"""
    name: str
    """Name of the function to be called"""
    arguments: str
    """Function arguments stored as JSON string format"""

    @classmethod
    def from_entry(
        cls,
        tool_call: Dict[str, Any],
        *,
        api_format: API_FORMATS = "openai-chatcompletion",
    ) -> "ToolCall":
        """
        Create a ToolCall instance from dictionary data in the specified API format.

        Args:
            tool_call: Dictionary containing tool call information
            api_format: API format type, supports openai, openai-response, anthropic, etc.

        Returns:
            ToolCall: Created tool call instance

        Raises:
            ValueError: When API format is not supported
            NotImplementedError: When API format is not yet implemented
        """
        if api_format in ["openai", "openai-chatcompletion"]:
            origin_tool_call = ChatCompletionMessageToolCall.model_validate(tool_call)
            return cls(
                id=origin_tool_call.id,
                name=origin_tool_call.function.name,
                arguments=origin_tool_call.function.arguments,
            )
        elif api_format == "openai-response":
            origin_tool_call = ResponseFunctionToolCall.model_validate(tool_call)
            return cls(
                id=origin_tool_call.call_id,
                name=origin_tool_call.name,
                arguments=origin_tool_call.arguments,
            )
        elif api_format == "anthropic":
            origin_tool_call = ToolUseBlock.model_validate(tool_call)
            arguments_str = (
                json.dumps(origin_tool_call.input)
                if not isinstance(origin_tool_call.input, str)
                else origin_tool_call.input
            )
            return cls(
                id=origin_tool_call.id,
                name=origin_tool_call.name,
                arguments=arguments_str,
            )
        elif api_format == "google":
            # Google/Gemini API format: {"id": None, "args": {...}, "name": "function_name"}
            from ..utils.models import generate_id

            origin_tool_call = GeminiToolCall.model_validate(tool_call)

            # Convert args dict to JSON string
            arguments_str = (
                json.dumps(origin_tool_call.args)
                if not isinstance(origin_tool_call.args, str)
                else origin_tool_call.args
            )

            # Generate ID if None
            tool_call_id = origin_tool_call.id or generate_id(mode="google")

            return cls(
                id=tool_call_id,
                name=origin_tool_call.name,
                arguments=arguments_str,
            )
        else:
            raise ValueError(f"Unsupported API format: {api_format}")

    from_dict = from_entry

    def to_tool_call(
        self, api_format: Union[API_FORMATS, Literal["general"]] = "general"
    ) -> Union[
        "ToolCall",
        ChatCompletionMessageToolCall,
        ResponseFunctionToolCall,
        ToolUseBlock,
    ]:
        if api_format in ["openai", "openai-chatcompletion"]:
            tool_call = ChatCompletionMessageToolCall(
                id=self.id,
                function=Function(
                    name=self.name,
                    arguments=self.arguments,
                ),
            )

        elif api_format == "openai-response":
            tool_call = ResponseFunctionToolCall(
                call_id=self.id,
                name=self.name,
                arguments=self.arguments,
            )

        elif api_format == "anthropic":
            try:
                input_data = (
                    json.loads(self.arguments)
                    if isinstance(self.arguments, str)
                    else self.arguments
                )
            except json.JSONDecodeError:
                input_data = self.arguments

            tool_call = ToolUseBlock(
                id=self.id,
                name=self.name,
                input=input_data,
            )

        elif api_format == "google":
            # Convert to Google/Gemini format
            try:
                args_data = (
                    json.loads(self.arguments)
                    if isinstance(self.arguments, str)
                    else self.arguments
                )
            except json.JSONDecodeError:
                args_data = {}

            # Google format: {"id": "call_id", "name": "function_name", "args": {...}}
            tool_call = GeminiToolCall(
                id=self.id,
                name=self.name,
                args=args_data,
            )

        elif api_format == "general":
            return self
        else:
            raise ValueError(f"Unsupported API format: {api_format}")

        return tool_call

    def serialize(
        self, api_format: Union[API_FORMATS, Literal["general"]] = "general"
    ) -> Dict[str, Any]:
        return self.to_tool_call(api_format).model_dump()

    def __str__(self) -> str:
        return f"ToolCall(id={self.id}, name={self.name}, arguments={self.arguments})"

    def __repr__(self) -> str:
        return self.__str__()


class Tool(BaseModel):
    """
    Universal tool definition middleware class supporting conversion between multiple API formats.

    This class represents tool/function definition information, including name, description, and parameter schema.
    It can load tool definitions from different API formats and convert to other formats.

    Attributes:
        name: Name of the tool/function
        description: Description of the tool/function
        parameters: Parameter schema of the tool/function, usually in JSON Schema format
    """

    name: str
    """Name of the tool/function"""
    description: str
    """Description of the tool/function"""
    parameters: Dict[str, Any]
    """Parameter schema of the tool/function, usually in JSON Schema format"""

    @classmethod
    def from_entry(
        cls, tool: Dict[str, Any], *, api_format: API_FORMATS = "openai-chatcompletion"
    ) -> "Tool":
        if api_format in ["openai", "openai-chatcompletion"]:
            # For OpenAI format, tool should be ChatCompletionToolParam format
            origin_tool = ChatCompletionToolParam.model_validate(tool)
            return Tool(
                name=origin_tool.function.name,
                description=origin_tool.function.description,
                parameters=origin_tool.function.parameters,
            )
        elif api_format == "openai-response":
            origin_tool = FunctionTool.model_validate(tool)
            return Tool(
                name=origin_tool.name,
                description=origin_tool.description,
                parameters=origin_tool.parameters,
            )
        elif api_format == "anthropic":
            origin_tool = ToolParam.model_validate(tool)
            # Ensure input_schema is in dictionary format
            if hasattr(origin_tool.input_schema, "model_dump"):
                parameters = origin_tool.input_schema.model_dump()
            elif isinstance(origin_tool.input_schema, dict):
                parameters = origin_tool.input_schema
            else:
                parameters = dict(origin_tool.input_schema)

            return Tool(
                name=origin_tool.name,
                description=origin_tool.description,
                parameters=parameters,
            )
        elif api_format == "google":
            origin_tool = GeminiTool.model_validate(tool)

            return Tool(
                name=origin_tool.name,
                description=origin_tool.description,
                parameters=origin_tool.parameters,
            )
        else:
            raise ValueError(f"Invalid API format: {api_format}")

    from_dict = from_entry

    def to_tool(
        self, api_format: Union[API_FORMATS, Literal["general"]] = "general"
    ) -> Union[
        "Tool",
        ChatCompletionToolParam,
        FunctionTool,
        ToolParam,
    ]:
        if api_format in ["openai", "openai-chatcompletion"]:
            tool = ChatCompletionToolParam(
                function=FunctionDefinition(
                    name=self.name,
                    description=self.description,
                    parameters=self.parameters,
                )
            )
        elif api_format == "openai-response":
            tool = FunctionTool(
                name=self.name,
                description=self.description,
                parameters=self.parameters,
                strict=False,
            )
        elif api_format == "anthropic":
            tool = ToolParam(
                name=self.name,
                description=self.description,
                input_schema=self.parameters,
            )
        elif api_format == "google":
            # Google/Gemini tool format: {"name": "...", "description": "...", "parameters": {...}}

            tool = GeminiTool(
                name=self.name,
                description=self.description,
                parameters=self.parameters,
            )

        elif api_format == "general":
            tool = self

        else:
            raise ValueError(f"Invalid API format: {api_format}")

        return tool

    def serialize(
        self, api_format: Union[API_FORMATS, Literal["general"]] = "general"
    ) -> Dict[str, Any]:
        return self.to_tool(api_format).model_dump()

    def __str__(self) -> str:
        return f"Tool(name={self.name}, description={self.description}, parameters={self.parameters})"

    def __repr__(self) -> str:
        return self.__str__()


class NamedTool(BaseModel):
    name: str

    def __str__(self) -> str:
        return f"NamedTool(name={self.name})"

    def __repr__(self) -> str:
        return self.__str__()


class ToolChoice(BaseModel):
    """
    Universal tool choice middleware class supporting conversion between multiple API formats.

    This class represents tool choice strategy, which can be string-type choices (like auto, required, none)
    or specify a specific tool name. Supports conversion between different API formats.

    Attributes:
        choice: Tool choice strategy, can be "optional" (auto), "none" (don't use),
               "any" (must use) or NamedTool instance (specific tool)
    """

    choice: Union[Literal["optional", "none", "any"], NamedTool]
    """Tool choice strategy"""

    @staticmethod
    def _str_triage(data: str) -> "ToolChoice":
        if data == "auto":
            return ToolChoice(choice="optional")
        elif data == "required":
            return ToolChoice(choice="any")
        elif data == "none":
            return ToolChoice(choice="none")
        else:
            raise ValueError(f"Invalid tool choice: {data}")

    @classmethod
    def from_entry(
        cls,
        data: Union[str, Dict[str, Any]],
        *,
        api_format: API_FORMATS = "openai-chatcompletion",
    ) -> "ToolChoice":
        """
        Create a ToolChoice instance from data in the specified API format.

        Args:
            data: Tool choice data, can be string or dictionary
            api_format: API format type

        Returns:
            ToolChoice: Created tool choice instance

        Raises:
            ValueError: When data format is invalid or API format is not supported
            NotImplementedError: When API format is not yet implemented
        """
        if api_format in ["openai", "openai-chatcompletion"]:
            return cls._handle_openai_chatcompletion(data)
        elif api_format == "openai-response":
            return cls._handle_openai_response(data)
        elif api_format == "anthropic":
            return cls._handle_anthropic(data)
        elif api_format == "google":
            return cls._handle_google(data)
        else:
            raise ValueError(f"Unsupported API format: {api_format}")

    @classmethod
    def _handle_openai_chatcompletion(
        cls, data: Union[str, Dict[str, Any]]
    ) -> "ToolChoice":
        """Handle OpenAI Chat Completions API format tool_choice"""
        if isinstance(data, str):
            return cls._str_triage(data)
        elif isinstance(data, dict):
            # ChatCompletionNamedToolChoiceParam format: {"type": "function", "function": {"name": "..."}}
            if "function" in data and "name" in data["function"]:
                return cls(choice=NamedTool(name=data["function"]["name"]))
            else:
                raise ValueError(
                    f"Invalid OpenAI chat completion tool choice format: {data}"
                )
        else:
            raise ValueError(f"Invalid tool choice data type: {type(data)}")

    @classmethod
    def _handle_openai_response(cls, data: Union[str, Dict[str, Any]]) -> "ToolChoice":
        """Handle OpenAI Responses API format tool_choice"""
        if isinstance(data, str):
            return cls._str_triage(data)
        elif isinstance(data, dict):
            # ToolChoiceFunctionParam format: {"type": "function", "name": "..."}
            if "name" in data:
                return cls(choice=NamedTool(name=data["name"]))
            else:
                raise ValueError(f"Invalid OpenAI response tool choice format: {data}")
        else:
            raise ValueError(f"Invalid tool choice data type: {type(data)}")

    @classmethod
    def _handle_anthropic(cls, data: Union[str, Dict[str, Any]]) -> "ToolChoice":
        """Handle Anthropic API format tool_choice"""
        if isinstance(data, dict):
            tool_type = data.get("type")
            if tool_type == "auto":
                return cls(choice="optional")
            elif tool_type == "any":
                return cls(choice="any")
            elif tool_type == "none":
                return cls(choice="none")
            elif tool_type == "tool":
                if "name" in data:
                    return cls(choice=NamedTool(name=data["name"]))
                else:
                    raise ValueError(
                        "Anthropic tool choice with type 'tool' must have 'name' field"
                    )
            else:
                raise ValueError(f"Invalid Anthropic tool choice type: {tool_type}")
        else:
            raise ValueError(
                f"Anthropic tool choice must be a dictionary, got: {type(data)}"
            )

    @classmethod
    def _handle_google(cls, data: Union[str, Dict[str, Any]]) -> "ToolChoice":
        """Handle Google/Gemini API format tool_choice"""
        if isinstance(data, str):
            # Google uses different string values, map them to our internal format
            data_upper = data.upper()
            if data_upper == "AUTO":
                return cls(choice="optional")
            elif data_upper == "ANY":
                return cls(choice="any")
            elif data_upper == "NONE":
                return cls(choice="none")
            else:
                # Fallback to standard triage for OpenAI-style strings
                return cls._str_triage(data)
        elif isinstance(data, dict):
            # Google format: {"mode": "AUTO"/"ANY"/"NONE"} or {"mode": "FUNCTION_CALLING", "allowed_function_names": ["name"]}
            mode = data.get("mode", "").upper()
            if mode == "AUTO":
                return cls(choice="optional")
            elif mode == "ANY":
                return cls(choice="any")
            elif mode == "NONE":
                return cls(choice="none")
            elif mode == "FUNCTION_CALLING":
                # Specific function calling mode
                allowed_functions = data.get("allowed_function_names", [])
                if allowed_functions and len(allowed_functions) == 1:
                    return cls(choice=NamedTool(name=allowed_functions[0]))
                else:
                    # Multiple functions allowed, treat as "any"
                    return cls(choice="any")
            else:
                raise ValueError(f"Invalid Google tool choice mode: {mode}")
        else:
            raise ValueError(f"Invalid Google tool choice data type: {type(data)}")

    def to_tool_choice(
        self,
        api_format: Union[API_FORMATS, Literal["general"]] = "general",
    ) -> Union[str, Dict[str, Any], BaseModel, "ToolChoice"]:
        """
        Convert ToolChoice instance to data in the specified API format.

        Args:
            api_format: Target API format

        Returns:
            Converted tool choice data

        Raises:
            ValueError: When tool choice is invalid or API format is not supported
            NotImplementedError: When API format is not yet implemented
        """
        if api_format in ["openai", "openai-chatcompletion"]:
            return self._to_openai_chatcompletion()
        elif api_format == "openai-response":
            return self._to_openai_response()
        elif api_format == "anthropic":
            return self._to_anthropic()
        elif api_format == "google":
            return self._to_google()
        elif api_format == "general":
            return self
        else:
            raise ValueError(f"Invalid API format: {api_format}")

    def _to_openai_chatcompletion(
        self,
    ) -> Union[str, ChatCompletionNamedToolChoiceParam]:
        """Convert to OpenAI Chat Completions API format"""
        if isinstance(self.choice, str):
            if self.choice == "optional":
                return "auto"
            elif self.choice == "any":
                return "required"
            elif self.choice == "none":
                return "none"
            else:
                raise ValueError(f"Invalid tool choice: {self.choice}")
        elif isinstance(self.choice, NamedTool):
            return ChatCompletionNamedToolChoiceParam(
                function=FunctionDefinitionCore(name=self.choice.name)
            )
        else:
            raise ValueError(f"Invalid tool choice type: {type(self.choice)}")

    def _to_openai_response(self) -> Union[str, ToolChoiceFunctionParam]:
        """Convert to OpenAI Responses API format"""
        if isinstance(self.choice, str):
            if self.choice == "optional":
                return "auto"
            elif self.choice == "any":
                return "required"
            elif self.choice == "none":
                return "none"
            else:
                raise ValueError(f"Invalid tool choice: {self.choice}")
        elif isinstance(self.choice, NamedTool):
            return ToolChoiceFunctionParam(name=self.choice.name)
        else:
            raise ValueError(f"Invalid tool choice type: {type(self.choice)}")

    def _to_anthropic(
        self,
    ) -> Union[
        ToolChoiceAutoParam,
        ToolChoiceAnyParam,
        ToolChoiceNoneParam,
        ToolChoiceToolParam,
    ]:
        """Convert to Anthropic API format"""
        if isinstance(self.choice, str):
            if self.choice == "optional":
                return ToolChoiceAutoParam()
            elif self.choice == "any":
                return ToolChoiceAnyParam()
            elif self.choice == "none":
                return ToolChoiceNoneParam()
            else:
                raise ValueError(f"Invalid tool choice: {self.choice}")
        elif isinstance(self.choice, NamedTool):
            return ToolChoiceToolParam(name=self.choice.name)
        else:
            raise ValueError(f"Invalid tool choice type: {type(self.choice)}")

    def _to_google(self) -> Union[str, Dict[str, Any]]:
        """Convert to Google/Gemini API format"""
        if isinstance(self.choice, str):
            if self.choice == "optional":
                return "AUTO"
            elif self.choice == "any":
                return "ANY"
            elif self.choice == "none":
                return "NONE"
            else:
                raise ValueError(f"Invalid tool choice: {self.choice}")
        elif isinstance(self.choice, NamedTool):
            # Google format for specific function
            return {
                "mode": "FUNCTION_CALLING",
                "allowed_function_names": [self.choice.name],
            }
        else:
            raise ValueError(f"Invalid tool choice type: {type(self.choice)}")

    def serialize(
        self,
        api_format: Union[API_FORMATS, Literal["general"]] = "general",
    ) -> Union[Dict[str, Any], str]:
        serialized = self.to_tool_choice(api_format)
        return (
            serialized.model_dump() if hasattr(serialized, "model_dump") else serialized
        )

    def __str__(self):
        return f"ToolChoice(choice={self.choice})"

    def __repr__(self):
        return self.__str__()
