import json
import re
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
    overload,
)

from loguru import logger
from pydantic import ValidationError

from ..types.function_call import (
    ChatCompletionMessageToolCall,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
    Function,
    ResponseFunctionToolCall,
)
from ..utils.models import generate_id
from .handler import ToolCall


class ToolInterceptor:
    """
    Tool interceptor that handles both prompt-based and native tool calling responses.

    This class can process:
    1. Legacy prompt-based responses with <tool_call> tags
    2. Native tool calling responses from different model providers
    """

    def __init__(self):
        pass

    def process(
        self,
        response_content: Union[str, Dict[str, Any]],
        model_family: Literal["openai", "anthropic", "google"] = "openai",
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process response content and extract tool calls.

        Args:
            response_content: Either a string (legacy format) or dict (native format)
            model_family: Model family to determine the processing strategy

        Returns:
            Tuple of (list of tool calls or None, text content)
        """
        if isinstance(response_content, str):
            # Legacy prompt-based format
            return self._process_prompt_based(response_content)
        elif isinstance(response_content, dict):
            # Native tool calling format
            return self._process_native(response_content, model_family)
        else:
            logger.warning(
                f"Unexpected response content type: {type(response_content)}"
            )
            return None, str(response_content)

    def _process_prompt_based(self, text: str) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process prompt-based responses with <tool_call> tags.

        Args:
            text: Text content containing potential <tool_call> tags

        Returns:
            Tuple of (list of ToolCall objects or None, concatenated text from outside tool calls)
        """
        tool_calls = []
        text_parts = []
        last_end = 0

        for match in re.finditer(r"<tool_call>(.*?)</tool_call>", text, re.DOTALL):
            # Add text before this tool call
            if match.start() > last_end:
                text_parts.append(text[last_end : match.start()])

            # Process the tool call
            try:
                tool_call_dict = json.loads(match.group(1).strip())
                # Convert dict to ToolCall object
                tool_call = ToolCall(
                    id=generate_id(mode="general"),
                    name=tool_call_dict.get("name", ""),
                    arguments=json.dumps(tool_call_dict.get("arguments", {}))
                    if isinstance(tool_call_dict.get("arguments"), dict)
                    else str(tool_call_dict.get("arguments", "")),
                )
                tool_calls.append(tool_call)
            except json.JSONDecodeError:
                # On JSON error, include the raw content as text
                text_parts.append(f"<invalid>{match.group(1)}</invalid>")

            last_end = match.end()

        # Add any remaining text after last tool call
        if last_end < len(text):
            text_parts.append(text[last_end:])

        return (
            tool_calls if tool_calls else None,
            "".join(
                text_parts
            ).lstrip(),  # Combine all text parts and strip leading whitespace
        )

    def _process_native(
        self,
        response_data: Dict[str, Any],
        model_family: Literal["openai", "anthropic", "google"] = "openai",
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process native tool calling responses from different model providers.

        Args:
            response_data: Response data containing content and tool_calls
            model: Model name to determine the processing strategy

        Returns:
            Tuple of (list of tool calls or None, text content)
        """
        logger.warning(" ")
        logger.warning(f"Received response data: {response_data}")
        logger.warning(" ")

        if model_family == "openai":
            logger.warning("[Output Handle] Using [OpenAI] native tool calling format")
            return self._process_openai_native(response_data)
        elif model_family == "anthropic":
            logger.warning(
                "[Output Handle] Using [Anthropic] native tool calling format"
            )
            return self._process_anthropic_native(response_data)
        elif model_family == "google":
            logger.warning("[Output Handle] Using [Google] native tool calling format")
            return self._process_google_native(response_data)
        else:
            logger.warning(
                f"Unknown model family for model: {model_family}, falling back to OpenAI format"
            )
            return self._process_openai_native(response_data)

    def _process_openai_native(
        self, response_data: Dict[str, Any]
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process OpenAI native tool calling response format.

        Expected format:
        {
            "content": "text response",
            "tool_calls": [
                {"name": "function_name", "arguments": {...}}
            ]
        }

        Args:
            response_data: OpenAI format response data

        Returns:
            Tuple of (list of ToolCall objects or None, text content)
        """
        content = response_data.get("content", "")
        tool_calls_data = response_data.get("tool_calls", [])

        # Convert tool calls to ToolCall objects
        tool_calls = None
        if tool_calls_data:
            tool_calls = []
            for tool_call_dict in tool_calls_data:
                # Use ToolCall.from_entry to convert from OpenAI format
                tool_call = ToolCall.from_entry(
                    tool_call_dict, api_format="openai-chatcompletion"
                )
                tool_calls.append(tool_call)

        return tool_calls, content

    def _process_anthropic_native(
        self, response_data: Dict[str, Any]
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process Anthropic native tool calling response format.

        Expected in-house gateway format for Anthropic models:
        {
            "response": {
                "content": "I'll get the current stock price...",
                "tool_calls": [
                    {
                        "id": "toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH",
                        "input": {"ticker": "MSFT"},
                        "name": "get_stock_price",
                        "type": "tool_use"
                    }
                ]
            }
        }

        Args:
            response_data: Anthropic format response data

        Returns:
            Tuple of (list of ToolCall objects or None, text content)
        """
        # Extract response object if present
        response = response_data.get("response", response_data)

        # Get text content directly
        text_content = response.get("content", "")

        # Get tool calls array
        claude_tool_calls = response.get("tool_calls", [])

        logger.warning(f"[Output Handle] Claude tool calls: {claude_tool_calls}")
        logger.warning(f"[Output Handle] Claude text content: {text_content}")

        # Convert Claude tool calls to ToolCall objects
        tool_calls = None
        if claude_tool_calls:
            tool_calls = []
            for claude_tool_call in claude_tool_calls:
                # Use ToolCall.from_entry to convert from Anthropic format
                tool_call = ToolCall.from_entry(
                    claude_tool_call, api_format="anthropic"
                )
                tool_calls.append(tool_call)
            logger.warning(f"[Output Handle] Converted ToolCall objects: {tool_calls}")

        return tool_calls, text_content

    def _process_google_native(
        self, response_data: Dict[str, Any]
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process Google native tool calling response format.

        Expected Google/Gemini format:
        {
            "content": "text response",
            "tool_calls": [
                {"id": None, "args": {...}, "name": "function_name"}
            ]
        }

        Args:
            response_data: Google format response data

        Returns:
            Tuple of (list of ToolCall objects or None, text content)
        """
        content = response_data.get("content", "")
        tool_calls_data = response_data.get("tool_calls", [])

        logger.warning(f"[Output Handle] Google tool calls: {tool_calls_data}")
        logger.warning(f"[Output Handle] Google text content: {content}")

        # Convert Google tool calls to ToolCall objects
        tool_calls = None
        if tool_calls_data:
            tool_calls = []
            for i, google_tool_call in enumerate(tool_calls_data):
                # Use ToolCall.from_entry to convert from Google format
                # Generate ID if None
                if google_tool_call.get("id") is None:
                    google_tool_call["id"] = f"call_{i}"

                tool_call = ToolCall.from_entry(google_tool_call, api_format="google")
                tool_calls.append(tool_call)
            logger.warning(f"[Output Handle] Converted ToolCall objects: {tool_calls}")

        return tool_calls, content


def chat_completion_to_response_tool_call(
    chat_tool_call: ChatCompletionMessageToolCall,
) -> ResponseFunctionToolCall:
    """Converts a ChatCompletionMessageToolCall to ResponseFunctionToolCall.

    Args:
        chat_tool_call: The ChatCompletionMessageToolCall to convert.

    Returns:
        ResponseFunctionToolCall with corresponding data.
    """
    return ResponseFunctionToolCall(
        arguments=chat_tool_call.function.arguments,
        call_id=chat_tool_call.id,
        name=chat_tool_call.function.name,
        id=generate_id(mode="openai-response"),
        status="completed",
    )


@overload
def tool_calls_to_openai(
    tool_calls: List[Union[Dict[str, Any], ChatCompletionMessageToolCall, ToolCall]],
    *,
    api_format: Literal["chat_completion"] = "chat_completion",
) -> List[ChatCompletionMessageToolCall]: ...


@overload
def tool_calls_to_openai(
    tool_calls: List[Union[Dict[str, Any], ChatCompletionMessageToolCall, ToolCall]],
    *,
    api_format: Literal["response"],
) -> List[ResponseFunctionToolCall]: ...


def tool_calls_to_openai(
    tool_calls: List[Union[Dict[str, Any], ChatCompletionMessageToolCall, ToolCall]],
    *,
    api_format: Literal["chat_completion", "response"] = "chat_completion",
) -> List[Union[ChatCompletionMessageToolCall, ResponseFunctionToolCall]]:
    """Converts parsed tool calls to OpenAI API format.

    Args:
        tool_calls: List of parsed tool calls. Can be either dictionaries,
            ChatCompletionMessageToolCall objects, or ToolCall objects.
        api_format: Output format type, either "chat_completion" or "response".
            Defaults to "chat_completion".

    Returns:
        List of tool calls in OpenAI function call object type. The specific type
        depends on the api_format parameter:
        - ChatCompletionMessageToolCall for "chat_completion"
        - ResponseFunctionToolCall for "response"
    """
    openai_tool_calls = []

    for call in tool_calls:
        # Handle ToolCall, dict and ChatCompletionMessageToolCall inputs
        if isinstance(call, ChatCompletionMessageToolCall):
            chat_tool_call = call
        elif isinstance(call, ToolCall):
            # Convert ToolCall to ChatCompletionMessageToolCall
            chat_tool_call = call.to_tool_call("openai-chatcompletion")
        elif isinstance(call, dict):
            # Check if it's already in ChatCompletionMessageToolCall format
            try:
                # Try to parse as ChatCompletionMessageToolCall using Pydantic
                chat_tool_call = ChatCompletionMessageToolCall.model_validate(call)
            except (ValidationError, TypeError):
                # Legacy format - create from name/arguments
                arguments = json.dumps(call.get("arguments", ""))
                name = call.get("name", "")
                chat_tool_call = ChatCompletionMessageToolCall(
                    id=generate_id(mode="openai-chatcompletion"),
                    function=Function(name=name, arguments=arguments),
                )
        else:
            raise ValueError(f"Unsupported tool call type: {type(call)}")

        if api_format == "chat_completion":
            openai_tool_calls.append(chat_tool_call)
        else:
            # Convert to ResponseFunctionToolCall using helper function
            response_tool_call = chat_completion_to_response_tool_call(chat_tool_call)
            openai_tool_calls.append(response_tool_call)

    return openai_tool_calls


def tool_calls_to_openai_stream(
    tool_call: Union[Dict[str, Any], ChatCompletionMessageToolCall, ToolCall],
    *,
    tc_index: int = 0,
    api_format: Literal["chat_completion", "response"] = "chat_completion",
) -> ChoiceDeltaToolCall:
    """
    Converts a tool call to OpenAI-compatible tool call objects for streaming.

    Args:
        tool_call: Single tool call to convert. Can be either a dictionary,
            ChatCompletionMessageToolCall object, or ToolCall object.
        tc_index: The index of the tool call.
        api_format: The format to convert the tool calls to. Can be "chat_completion" or "response".

    Returns:
        An OpenAI-compatible stream tool call object.
    """

    # Handle ToolCall, dict and ChatCompletionMessageToolCall inputs
    if isinstance(tool_call, ChatCompletionMessageToolCall):
        chat_tool_call = tool_call
    elif isinstance(tool_call, ToolCall):
        # Convert ToolCall to ChatCompletionMessageToolCall
        chat_tool_call = tool_call.to_tool_call("openai-chatcompletion")
    elif isinstance(tool_call, dict):
        # Check if it's already in ChatCompletionMessageToolCall format
        try:
            # Try to parse as ChatCompletionMessageToolCall using Pydantic
            chat_tool_call = ChatCompletionMessageToolCall.model_validate(tool_call)
        except (ValidationError, TypeError):
            # Legacy format - create from name/arguments
            arguments = json.dumps(tool_call.get("arguments", ""))
            name = tool_call.get("name", "")
            chat_tool_call = ChatCompletionMessageToolCall(
                id=generate_id(mode="openai-chatcompletion"),
                function=Function(
                    name=name,
                    arguments=arguments,
                ),
            )
    else:
        raise ValueError(f"Unsupported tool call type: {type(tool_call)}")

    if api_format == "chat_completion":
        tool_call_obj = ChoiceDeltaToolCall(
            id=chat_tool_call.id,
            function=ChoiceDeltaToolCallFunction(
                name=chat_tool_call.function.name,
                arguments=chat_tool_call.function.arguments,
            ),
            index=tc_index,
        )
    else:
        # TODO: Implement response format
        raise NotImplementedError("response format is not implemented yet.")

    return tool_call_obj
