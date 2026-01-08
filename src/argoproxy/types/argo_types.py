from typing import Any, Dict, List, Literal, Optional, TypedDict, Union

# ==================== Argo Message Types (TypedDict) ====================


class ArgoContentPartText(TypedDict):
    type: Literal["text"]
    text: str


class ArgoContentPartImage(TypedDict):
    type: Literal["image_url"]
    image_url: str


ArgoContentPart = Union[ArgoContentPartText, ArgoContentPartImage]


class ArgoMessage(TypedDict, total=False):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[ArgoContentPart]]]


# ==================== Argo Tool Call Types ======================

## ======== OpenAI Styled ========

# # request
# data = {
#     "user": "<**ENTER YOUR ANL DOMAIN USERNAME**>",
#     "model": "gpt4o",
#     "messages": [
#         {"role": "system",
#           "content": "You are an LLM-based AI assistant with the name Argo that supports users at Argonne National Lab."},
#         {"role": "user",
#           "content": "What is 8 plus 5?"}
#     ],
#     "stop": [],
#     "temperature": 0.1,
#     "top_p": 0.9,
#     "tools": [
#         {
#             "type": "function",
#             "function": {
#                 "name": "add",
#                 "description": "Add two numbers together.",
#                 "parameters": {
#                     "type": "object",
#                     "properties": {
#                         "a": {"type": "number", "description": "First number"},
#                         "b": {"type": "number", "description": "Second number"}
#                     },
#                     "required": ["a", "b"]
#                 }
#             }
#         }
#     ],
#     "tool_choice":"auto",
# }

# # return
# {
#     "response": {
#         "content": null,
#         "tool_calls": [
#             {
#                 "id": "call_oSUkDwcOqkNulrSjCfCpRRQI",
#                 "function": {
#                     "arguments": "{\"a\":8,\"b\":5}",
#                     "name": "add"
#                 },
#                 "type": "function"
#             }
#         ]
#     }
# }


class OpenAIFunctionDefinition(TypedDict, total=False):
    name: str
    description: str
    parameters: Dict[str, Any]


class OpenAITool(TypedDict):
    type: Literal["function"]
    function: OpenAIFunctionDefinition


class OpenAIToolChoiceFunction(TypedDict):
    name: str


class OpenAIToolChoiceObject(TypedDict):
    type: Literal["function"]
    function: OpenAIToolChoiceFunction


OpenAIToolChoice = Union[Literal["none", "auto", "required"], OpenAIToolChoiceObject]


class OpenAIToolCallFunction(TypedDict):
    name: str
    arguments: str


class OpenAIToolCall(TypedDict):
    id: str
    type: Literal["function"]
    function: OpenAIToolCallFunction


## ======== Anthropic Styled ========

# # request
# data = {
#     "user": "<**ENTER YOUR ANL DOMAIN USERNAME**>",
#     "model": "claudesonnet4",
#     "messages": [
#         {"role": "system",
#         "content": "You are a large language model with the name Argo that supports users at Argonne National Lab."},
#         {"role": "user",
#         "content": "What is the current stock price for MSFT"}
#     ],
#     "stop": [],
#     "temperature": 0.1,
#     "top_p": 0.9,
#     "tools": [
#         {
#             "name": "get_stock_price",
#             "description": "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company.",
#             "input_schema": {
#                 "type": "object",
#                 "properties": {
#                     "ticker": {
#                         "type": "string",
#                         "description": "The stock ticker symbol, e.g. AAPL for Apple Inc."
#                     }
#                 },
#                 "required": [
#                     "ticker"
#                 ]
#             }
#         }
#     ],
#     "tool_choice": {"type": "auto"}
# }

# # return
# {
#     "response": {
#         "content": "I'll get the current stock price for Microsoft (MSFT) for you.",
#         "tool_calls": [
#             {
#                 "id": "toolu_vrtx_01NsufZdmVCSMMdptrvxzbaa",
#                 "input": {
#                     "ticker": "MSFT"
#                 },
#                 "name": "get_stock_price",
#                 "type": "tool_use"
#             }
#         ]
#     }
# }


class AnthropicTool(TypedDict):
    name: str
    description: str
    input_schema: Dict[str, Any]


class AnthropicToolChoice(TypedDict, total=False):
    type: Literal["auto", "any", "none", "tool"]
    name: str


class AnthropicToolCall(TypedDict):
    id: str
    type: Literal["tool_use"]
    name: str
    input: Dict[str, Any]


## ======== Google Styled ========

# # request
# data = {
#     "user": "<**ENTER YOUR ANL DOMAIN USERNAME**>",
#     "model": "gemini25flash",
#     "messages": [
#         {"role": "system",
#           "content": "You are an LLM-based AI assistant with the name Argo that supports users at Argonne National Lab."},
#         {"role": "user",
#           "content": "What is 8 plus 5?"}
#     ],
#     "stop": [],
#     "temperature": 0.1,
#     "top_p": 0.9,
#     "tools": [
#         {
#             "name": "get_current_weather",
#             "description": "Get the current weather in a given location",
#             "parameters": {
#                 "type": "OBJECT",
#                 "properties": {
#                     "location": {
#                         "type": "STRING",
#                         "description": "The city and state, e.g. San Francisco, CA"
#                     }
#                 }
#             },
#             "required":["location"]
#         },
#         {
#             "name": "add",
#             "description": "Add two numbers together.",
#             "parameters": {
#                 "type": "OBJECT",
#                 "properties": {
#                     "a": {
#                         "type": "number",
#                         "description": "The first number to add."
#                     },
#                     "b": {
#                         "type": "number",
#                         "description": "The second number to add."
#                     }
#                 }
#             },
#             "required":["a","b"]
#         }
#     ]
# }

# # return
# {
#     "response": {
#         "content": null,
#         "tool_calls": {
#             "id": null,
#             "args": {
#                 "b": 5,
#                 "a": 8
#             },
#             "name": "add"
#         }
#     }
# }


class GoogleTool(TypedDict, total=False):
    name: str
    description: str
    parameters: Dict[str, Any]


class GoogleToolCall(TypedDict):
    id: Optional[str]
    name: str
    args: Dict[str, Any]


# tool choice for google models
class GoogleFunctionCallingConfig(TypedDict, total=False):
    mode: Literal["ANY", "AUTO", "NONE", "VALIDATED"]
    allowed_function_names: List[str]


class GoogleToolConfig(TypedDict, total=False):
    function_calling_config: GoogleFunctionCallingConfig


ArgoTool = Union[OpenAITool, AnthropicTool, GoogleTool]
ArgoToolChoice = Union[OpenAIToolChoice, AnthropicToolChoice, GoogleToolConfig]
ArgoToolCall = Union[OpenAIToolCall, AnthropicToolCall, GoogleToolCall]


# ==================== Argo Gateway API Types ====================


class ArgoResponseDict(TypedDict, total=False):
    """Argo Response dictionary structure when it's not a plain string."""

    content: Optional[str]
    tool_calls: Optional[List[ArgoToolCall]]


class ArgoChatResponse(TypedDict):
    """Argo Gateway API Chat Response type."""

    response: ArgoResponseDict


class ArgoChatRequest(TypedDict, total=False):
    """Argo Gateway API Chat Request type."""

    model: str
    messages: Optional[List[ArgoMessage]]
    prompt: Optional[List[str]]
    system: Optional[str]
    stream: Optional[bool]
    user: Optional[str]

    # Tools and tool_choice vary by model family (Argo, Anthropic, Google)
    tools: Optional[List[ArgoTool]]
    tool_choice: Optional[ArgoToolChoice]

    # Common LLM parameters
    stop: Optional[Union[str, List[str]]]  # Up to 4 sequences. Not for o1-preview.
    temperature: Optional[float]  # 0 to 2. Not for o1-preview.
    top_p: Optional[float]  # 0 to 1. Not for o1-preview.
    max_tokens: Optional[int]  # Max tokens to generate. Not for o1-preview.
    max_completion_tokens: Optional[int]  # Only for o1-preview.
