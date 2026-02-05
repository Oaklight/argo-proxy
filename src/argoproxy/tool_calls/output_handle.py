import gzip
import json
import re
from datetime import datetime
from pathlib import Path
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

from pydantic import ValidationError

from ..config import load_config
from ..types.function_call import (
    ChatCompletionMessageToolCall,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
    Function,
    ResponseFunctionToolCall,
)
from ..utils.logging import log_debug, log_error, log_warning, truncate_string
from ..utils.models import generate_id
from .handler import ToolCall
from .leaked_tool_parser import (
    extract_leaked_tool_calls,
    parse_anthropic_content_array,
)


def _get_leaked_tool_log_dir() -> Path:
    """Get the directory for storing leaked tool call logs.

    Returns the path relative to the config file location.
    """
    config_data, config_path = load_config(verbose=False)

    if config_path:
        # Use config file's directory
        log_dir = config_path.parent / "leaked_tool_calls"
    else:
        # Fallback to current directory
        log_dir = Path.cwd() / "leaked_tool_calls"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _get_log_dir_size(log_dir: Path) -> int:
    """Calculate total size of all files in the log directory.

    Args:
        log_dir: Path to the log directory

    Returns:
        Total size in bytes
    """
    total_size = 0
    for file_path in log_dir.glob("*"):
        if file_path.is_file():
            total_size += file_path.stat().st_size
    return total_size


def _compress_log_files(log_dir: Path) -> None:
    """Compress all uncompressed JSON log files in the directory.

    Args:
        log_dir: Path to the log directory
    """
    try:
        json_files = list(log_dir.glob("leaked_tool_*.json"))
        if not json_files:
            return

        log_warning(
            f"Compressing {len(json_files)} log files in {log_dir}",
            context="output_handle",
        )

        for json_file in json_files:
            try:
                gz_file = json_file.with_suffix(".json.gz")

                # Read and compress
                with open(json_file, "rb") as f_in:
                    with gzip.open(gz_file, "wb", compresslevel=9) as f_out:
                        f_out.write(f_in.read())

                # Remove original file
                json_file.unlink()

            except Exception as e:
                log_error(
                    f"Failed to compress {json_file}: {e}", context="output_handle"
                )

        log_warning(
            f"Compression complete. Compressed {len(json_files)} files.",
            context="output_handle",
        )

    except Exception as e:
        log_error(f"Failed to compress log files: {e}", context="output_handle")


def _log_leaked_tool_case(
    text_content: str,
    leaked_str: str,
    request_data: Optional[Dict[str, Any]] = None,
    response_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a leaked tool call case for analysis.

    Args:
        text_content: The full text content where the leak was found
        leaked_str: The extracted leaked tool call string
        request_data: Optional original request data
        response_data: Optional full response data
    """
    try:
        log_dir = _get_leaked_tool_log_dir()

        # Check if compression is needed (50MB threshold)
        # Rationale: With Claude's 200K context, a single request can be 1-2MB
        # 50MB allows collecting 12-25 large requests or 50-100 normal requests
        # before compression, providing sufficient samples for analysis
        dir_size = _get_log_dir_size(log_dir)
        if dir_size > 50 * 1024 * 1024:  # 50MB in bytes
            log_warning(
                f"Log directory size ({dir_size / 1024 / 1024:.2f}MB) exceeds 50MB, compressing logs...",
                context="output_handle",
            )
            _compress_log_files(log_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_file = log_dir / f"leaked_tool_{timestamp}.json"

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "leaked_tool_string": leaked_str,
            "full_text_content": text_content,
            "context_before": text_content[: text_content.find(leaked_str)]
            if leaked_str in text_content
            else "",
            "context_after": text_content[
                text_content.find(leaked_str) + len(leaked_str) :
            ]
            if leaked_str in text_content
            else "",
        }

        if request_data:
            log_entry["request"] = request_data
        if response_data:
            log_entry["response"] = response_data

        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2, ensure_ascii=False)

        log_warning(
            f"Logged leaked tool call case to: {log_file}", context="output_handle"
        )
    except Exception as e:
        log_error(f"Failed to log leaked tool call case: {e}", context="output_handle")


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
        request_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process response content and extract tool calls.

        Args:
            response_content: Either a string (legacy format) or dict (native format)
            model_family: Model family to determine the processing strategy
            request_data: Optional request data for logging purposes

        Returns:
            Tuple of (list of tool calls or None, text content)
        """
        if isinstance(response_content, str):
            # Legacy prompt-based format
            return self._process_prompt_based(response_content)
        elif isinstance(response_content, dict):
            # Native tool calling format
            return self._process_native(response_content, model_family, request_data)
        else:
            log_warning(
                f"Unexpected response content type: {type(response_content)}",
                context="ToolInterceptor",
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
        request_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process native tool calling responses from different model providers.

        Args:
            response_data: Response data containing content and tool_calls
            model_family: Model family to determine the processing strategy
            request_data: Optional request data for logging purposes

        Returns:
            Tuple of (list of tool calls or None, text content)
        """
        log_warning(" ", context="output_handle")
        log_debug(f"Received response data: {response_data}", context="output_handle")
        log_warning(" ", context="output_handle")

        if model_family == "openai":
            log_warning(
                "[Output Handle] Using [OpenAI] native tool calling format",
                context="output_handle",
            )
            return self._process_openai_native(response_data)
        elif model_family == "anthropic":
            log_warning(
                "[Output Handle] Using [Anthropic] native tool calling format",
                context="output_handle",
            )
            return self._process_anthropic_native(response_data, request_data)
        elif model_family == "google":
            log_warning(
                "[Output Handle] Using [Google] native tool calling format",
                context="output_handle",
            )
            return self._process_google_native(response_data)
        else:
            log_warning(
                f"Unknown model family for model: {model_family}, falling back to OpenAI format",
                context="output_handle",
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
        self,
        response_data: Dict[str, Any],
        request_data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[List[ToolCall]], str]:
        """
        Process Anthropic native tool calling response format.

        Expected in-house gateway format for Anthropic models:
        {
            "response": {
                "content": "I'll get the current stock price..." OR [{"type": "text", ...}, {"type": "tool_use", ...}],
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
            request_data: Optional request data for logging purposes

        Returns:
            Tuple of (list of ToolCall objects or None, text content)
        """
        # Extract response object if present
        response = response_data.get("response", response_data)

        # Handle content - can be string OR array of content blocks
        raw_content = response.get("content", "")
        text_content, content_tool_blocks = parse_anthropic_content_array(raw_content)

        # Get tool calls from response (may be empty)
        claude_tool_calls: List[Dict[str, Any]] = list(
            response.get("tool_calls", []) or []
        )

        # Add any tool_use blocks found in content array
        if content_tool_blocks:
            log_warning(
                f"[Output Handle] Found {len(content_tool_blocks)} tool_use blocks in content array",
                context="output_handle",
            )
            claude_tool_calls.extend(content_tool_blocks)

        log_warning(
            f"[Output Handle] Claude tool calls: {len(claude_tool_calls)} calls",
            context="output_handle",
        )
        log_debug(
            f"[Output Handle] Claude tool calls: {claude_tool_calls}",
            context="output_handle",
        )
        log_warning(
            f"[Output Handle] Claude text content: {truncate_string(text_content, 100)}",
            context="output_handle",
        )

        # Check if leaked tool fix is enabled
        config_data, _ = load_config(verbose=False)
        enable_fix = config_data.enable_leaked_tool_fix if config_data else False

        # Check for leaked tool calls in text content (loop to find ALL)
        if "{'id': 'toolu_" in text_content:
            if enable_fix:
                log_warning(
                    "[LEAKED TOOL FIX ENABLED] Extracting leaked tool calls from text",
                    context="output_handle",
                )
                # Use the new parser to extract all leaked tools
                extracted_tools, cleaned_text = extract_leaked_tool_calls(
                    text_content, claude_tool_calls
                )

                if extracted_tools and len(extracted_tools) > len(claude_tool_calls):
                    # Log the leaked tool case for analysis
                    _log_leaked_tool_case(
                        text_content=text_content,
                        leaked_str=f"[{len(extracted_tools) - len(claude_tool_calls)} leaked tools extracted]",
                        request_data=request_data,
                        response_data=response_data,
                    )
                    claude_tool_calls = extracted_tools
                    text_content = cleaned_text
            else:
                # Just log for analysis without fixing
                log_warning(
                    "[LEAKED TOOL FIX DISABLED] Found potential leaked tool call(s) in text, logged for analysis",
                    context="output_handle",
                )
                # Log the first leaked tool for analysis
                start_idx = text_content.find("{'id': 'toolu_")
                if start_idx != -1:
                    # Find a reasonable end for logging (first 200 chars)
                    preview = text_content[start_idx : start_idx + 200]
                    _log_leaked_tool_case(
                        text_content=text_content,
                        leaked_str=preview,
                        request_data=request_data,
                        response_data=response_data,
                    )

        tool_calls = None
        if claude_tool_calls:
            tool_calls = []
            for claude_tool_call in claude_tool_calls:
                # Use ToolCall.from_entry to convert from Anthropic format
                tool_call = ToolCall.from_entry(
                    claude_tool_call, api_format="anthropic"
                )
                tool_calls.append(tool_call)
            log_warning(
                f"[Output Handle] Converted {len(tool_calls)} ToolCall objects",
                context="output_handle",
            )
            log_debug(
                f"[Output Handle] Converted ToolCall objects: {tool_calls}",
                context="output_handle",
            )

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

        log_warning(
            f"[Output Handle] Google tool calls: {len(tool_calls_data)} calls",
            context="output_handle",
        )
        log_debug(
            f"[Output Handle] Google tool calls: {tool_calls_data}",
            context="output_handle",
        )
        log_warning(
            f"[Output Handle] Google text content: {truncate_string(content, 100)}",
            context="output_handle",
        )

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
            log_warning(
                f"[Output Handle] Converted {len(tool_calls)} ToolCall objects",
                context="output_handle",
            )
            log_debug(
                f"[Output Handle] Converted ToolCall objects: {tool_calls}",
                context="output_handle",
            )

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
