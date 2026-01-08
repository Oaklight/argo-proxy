"""
LLMIR - Base Converter

定义转换器的基础接口（抽象基类，分层模板）
Defines the basic interface for converters (abstract base class, layered template)
"""

import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import aiohttp
from aiohttp import web
from llmir.converters.base import BaseConverter
from llmir.types.ir import (
    FilePart,
    ImagePart,
    IRInput,
    TextPart,
    ToolCallPart,
    ToolChoice,
    ToolDefinition,
    ToolResultPart,
)
from llmir.types.ir_request import IRRequest
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..types import (
    ChatCompletion,
    ChatCompletionMessage,
    CompletionUsage,
    NonStreamChoice,
)
from ..utils.image_processing import process_chat_images, sanitize_data_for_logging
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.models import determine_model_family
from ..utils.tokens import calculate_prompt_tokens_async, count_tokens_async


class ArgoConverter(BaseConverter):
    """转换器基类，定义统一的分层转换接口
    Base class for converters, defines a unified layered conversion interface
    """

    def __init__(self):
        """初始化ArgoConverter，预先实例化LLMIR转换器组件"""
        super().__init__()

        # 预先实例化LLMIR转换器，避免每次调用时重复实例化
        from llmir.converters.anthropic import AnthropicConverter
        from llmir.converters.google import GoogleConverter
        from llmir.converters.openai_chat import OpenAIChatConverter

        self._openai_converter = OpenAIChatConverter()
        self._anthropic_converter = AnthropicConverter()
        self._google_converter = GoogleConverter()

    def to_provider(
        self,
        ir_input: Union[IRInput, IRRequest],
        tools: Optional[Iterable[ToolDefinition]] = None,
        tool_choice: Optional[ToolChoice] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """将IR格式转换为provider特定格式
        Convert IR format to provider-specific format

        Args:
            ir_input: IR格式的输入或完整请求 / IR format input or full request
            tools: 工具定义列表（如果ir_input不是IRRequest） / Tool definition list (if ir_input is not IRRequest)
            tool_choice: 工具选择配置（如果ir_input不是IRRequest） / Tool choice configuration (if ir_input is not IRRequest)

        Returns:
            Tuple[转换后的数据, 警告信息列表] / Tuple[converted data, warning list]
        """
        warnings = []

        # 处理 IRRequest 格式
        if isinstance(ir_input, dict) and "messages" in ir_input:
            # 这是一个 IRRequest
            messages = ir_input["messages"]
            request_tools = ir_input.get("tools", tools)
            request_tool_choice = ir_input.get("tool_choice", tool_choice)
            model_name = ir_input.get("model", "")
        else:
            # 这是一个 IRInput (消息列表)
            messages = ir_input
            request_tools = tools
            request_tool_choice = tool_choice
            model_name = (
                getattr(ir_input, "model", "") if hasattr(ir_input, "model") else ""
            )

        # 确定模型家族
        # 确保 model_name 是字符串类型
        if not isinstance(model_name, str):
            model_name = str(model_name) if model_name is not None else ""

        model_family = determine_model_family(model_name) if model_name else "openai"
        if model_family == "unknown":
            model_family = "openai"  # 默认使用 OpenAI 格式

        # 转换消息列表（统一使用 OpenAI 格式的抽象方法）
        openai_messages = []
        for message in messages:
            openai_message = self._ir_message_to_p(message, messages)
            openai_messages.append(openai_message)

        # 构建 OpenAI 格式的数据
        openai_data = {"messages": openai_messages}

        # 添加工具相关字段（如果存在，统一使用 OpenAI 格式）
        if request_tools:
            openai_tools = []
            for tool in request_tools:
                openai_tool = self._ir_tool_to_p(tool)
                openai_tools.append(openai_tool)
            openai_data["tools"] = openai_tools

        if request_tool_choice:
            openai_tool_choice = self._ir_tool_choice_to_p(request_tool_choice)
            openai_data["tool_choice"] = openai_tool_choice

        # 复制其他字段
        if isinstance(ir_input, dict):
            for field in [
                "model",
                "max_tokens",
                "temperature",
                "top_p",
                "stream",
                "stop",
                "presence_penalty",
                "frequency_penalty",
                "logit_bias",
                "user",
                "seed",
                "response_format",
                "n",
            ]:
                if field in ir_input:
                    openai_data[field] = ir_input[field]

        # 如果目标模型家族不是 OpenAI，则进行格式转换
        if model_family == "openai":
            final_data = openai_data
        else:
            # 使用对应的 LLMIR 转换器将 OpenAI 格式转换为目标格式
            final_data = self._convert_openai_to_target_format(
                openai_data, model_family
            )

        return final_data, warnings

    def from_provider(self, provider_data: Any) -> Union[IRInput, Dict[str, Any]]:
        """将provider特定格式转换为IR格式
        Convert provider-specific format to IR format

        Args:
            provider_data: provider特定格式的数据 / Provider-specific format data

        Returns:
            IR格式的数据（消息列表或完整响应） / IR format data (message list or full response)
        """
        # 确定模型家族
        model_name = ""
        if isinstance(provider_data, dict):
            model_name = provider_data.get("model", "")

        # 确保 model_name 是字符串类型
        if not isinstance(model_name, str):
            model_name = str(model_name) if model_name is not None else ""

        from ..utils.models import determine_model_family

        model_family = determine_model_family(model_name) if model_name else "openai"
        if model_family == "unknown":
            model_family = "openai"  # 默认使用 OpenAI 格式

        # 如果不是 OpenAI 格式，先转换为 OpenAI 格式
        if model_family != "openai":
            openai_data = self._convert_target_to_openai_format(
                provider_data, model_family
            )
        else:
            openai_data = provider_data

        # 使用统一的 OpenAI 格式抽象方法进行转换
        if isinstance(openai_data, dict):
            if "messages" in openai_data:
                # 这是一个完整的请求/响应
                ir_messages = []
                for message in openai_data["messages"]:
                    ir_message = self._p_message_to_ir(message)
                    ir_messages.append(ir_message)

                # 构建 IR 请求
                ir_data = {"messages": ir_messages}

                # 处理工具相关字段
                if "tools" in openai_data:
                    ir_tools = []
                    for tool in openai_data["tools"]:
                        ir_tool = self._p_tool_to_ir(tool)
                        ir_tools.append(ir_tool)
                    ir_data["tools"] = ir_tools

                if "tool_choice" in openai_data:
                    ir_tool_choice = self._p_tool_choice_to_ir(
                        openai_data["tool_choice"]
                    )
                    ir_data["tool_choice"] = ir_tool_choice

                # 复制其他字段
                for field in [
                    "model",
                    "max_tokens",
                    "temperature",
                    "top_p",
                    "stream",
                    "stop",
                    "presence_penalty",
                    "frequency_penalty",
                    "logit_bias",
                    "user",
                    "seed",
                    "response_format",
                    "n",
                ]:
                    if field in openai_data:
                        ir_data[field] = openai_data[field]

                return ir_data
            else:
                # 这可能是一个单独的消息
                return self._p_message_to_ir(openai_data)
        elif isinstance(openai_data, list):
            # 这是一个消息列表
            ir_messages = []
            for message in openai_data:
                ir_message = self._p_message_to_ir(message)
                ir_messages.append(ir_message)
            return ir_messages
        else:
            raise ValueError(f"Unsupported provider data format: {type(openai_data)}")

    # ==================== 分层抽象方法 Layered abstract methods ====================

    def _ir_message_to_p(self, message: Dict[str, Any], ir_input: IRInput) -> Any:
        """IR Message → Provider Message / IR消息转换为Argo消息

        将 IR 格式的消息转换为 Argo 兼容的消息格式

        Args:
            message: IR格式的消息
            ir_input: 完整的IR输入（用于上下文）

        Returns:
            Argo格式的消息
        """
        argo_message = {"role": message.get("role", "user")}

        # 处理消息内容
        content = message.get("content", [])
        if isinstance(content, str):
            # 简单字符串内容
            argo_message["content"] = content
        elif isinstance(content, list):
            # 内容部分列表
            argo_content = []
            for part in content:
                argo_part = self._ir_content_part_to_p(part, ir_input)
                if argo_part:
                    argo_content.append(argo_part)

            # 如果只有一个文本部分，简化为字符串
            if len(argo_content) == 1 and argo_content[0].get("type") == "text":
                argo_message["content"] = argo_content[0]["text"]
            else:
                argo_message["content"] = argo_content
        else:
            # 其他格式，转换为字符串
            argo_message["content"] = str(content)

        # 处理工具调用（如果存在）
        if "tool_calls" in message:
            tool_calls = []
            for tool_call in message["tool_calls"]:
                # 使用统一的 OpenAI 格式抽象方法
                argo_tool_call = self._ir_tool_call_to_p(tool_call)
                tool_calls.append(argo_tool_call)
            argo_message["tool_calls"] = tool_calls

        # 处理其他字段
        for field in ["name", "tool_call_id"]:
            if field in message:
                argo_message[field] = message[field]

        return argo_message

    def _ir_content_part_to_p(
        self, content_part: Dict[str, Any], ir_input: IRInput
    ) -> Any:
        """IR ContentPart → Provider Content/Part / IR内容部分转换为Argo内容部分

        Args:
            content_part: IR格式的内容部分
            ir_input: 完整的IR输入（用于上下文）

        Returns:
            Argo格式的内容部分
        """
        part_type = content_part.get("type")

        if part_type == "text":
            return self._ir_text_to_p(content_part)
        elif part_type == "image":
            return self._ir_image_to_p(content_part)
        elif part_type == "file":
            return self._ir_file_to_p(content_part)
        elif part_type == "tool_call":
            return self._ir_tool_call_to_p(content_part)
        elif part_type == "tool_result":
            return self._ir_tool_result_to_p(content_part)
        else:
            # 未知类型，尝试作为文本处理
            return {
                "type": "text",
                "text": str(content_part.get("content", content_part)),
            }

    def _p_message_to_ir(self, provider_message: Any) -> Dict[str, Any]:
        """Provider Message → IR Message / Argo消息转换为IR消息

        Args:
            provider_message: Argo格式的消息

        Returns:
            IR格式的消息
        """
        if not isinstance(provider_message, dict):
            raise ValueError("Provider message must be a dictionary")

        ir_message = {"role": provider_message.get("role", "user")}

        # 处理消息内容
        content = provider_message.get("content")
        if isinstance(content, str):
            # 简单字符串内容
            ir_message["content"] = [self._p_text_to_ir(content)]
        elif isinstance(content, list):
            # 内容部分列表
            ir_content = []
            for part in content:
                ir_parts = self._p_content_part_to_ir(part)
                ir_content.extend(ir_parts)
            ir_message["content"] = ir_content
        elif content is not None:
            # 其他格式，转换为文本
            ir_message["content"] = [self._p_text_to_ir(str(content))]
        else:
            ir_message["content"] = []

        # 处理工具调用（如果存在）
        if "tool_calls" in provider_message:
            tool_calls = []
            for tool_call in provider_message["tool_calls"]:
                ir_tool_call = self._p_tool_call_to_ir(tool_call)
                tool_calls.append(ir_tool_call)
            ir_message["tool_calls"] = tool_calls

        # 处理其他字段
        for field in ["name", "tool_call_id"]:
            if field in provider_message:
                ir_message[field] = provider_message[field]

        return ir_message

    def _p_content_part_to_ir(self, provider_part: Any) -> List[Dict[str, Any]]:
        """Provider Content/Part → IR ContentPart(s) / Argo内容部分转换为IR内容部分

        Args:
            provider_part: Argo格式的内容部分

        Returns:
            IR格式的内容部分列表
        """
        if isinstance(provider_part, str):
            # 简单字符串
            return [self._p_text_to_ir(provider_part)]
        elif isinstance(provider_part, dict):
            part_type = provider_part.get("type")

            if part_type == "text":
                return [self._p_text_to_ir(provider_part)]
            elif part_type == "image_url":
                return [self._p_image_to_ir(provider_part)]
            elif part_type == "tool_call":
                return [self._p_tool_call_to_ir(provider_part)]
            elif part_type == "tool_result":
                return [self._p_tool_result_to_ir(provider_part)]
            else:
                # 未知类型，尝试作为文本处理
                return [self._p_text_to_ir(str(provider_part))]
        else:
            # 其他类型，转换为文本
            return [self._p_text_to_ir(str(provider_part))]

    # ==================== 共性内容类型转换接口 Common content type conversion interfaces ====================

    def _ir_text_to_p(self, text_part: TextPart) -> Any:
        """IR TextPart → Provider Text Content / IR文本部分转换为Provider文本内容"""
        return {"type": "text", "text": text_part["text"]}

    def _p_text_to_ir(self, provider_text: Any) -> TextPart:
        """Provider Text Content → IR TextPart / Argo文本内容转换为IR文本部分

        Argo 支持多种文本格式：
        1. 简单字符串：直接文本内容
        2. OpenAI 格式：{"type": "text", "text": "..."}
        3. 其他格式的文本内容

        Args:
            provider_text: Argo格式的文本内容

        Returns:
            IR格式的TextPart
        """
        if isinstance(provider_text, str):
            # 简单字符串格式
            return TextPart(type="text", text=provider_text)
        elif isinstance(provider_text, dict):
            if provider_text.get("type") == "text" and "text" in provider_text:
                # OpenAI 格式：{"type": "text", "text": "..."}
                return TextPart(type="text", text=provider_text["text"])
            else:
                # 其他字典格式，尝试提取文本内容
                text_content = provider_text.get("content", "") or str(provider_text)
                return TextPart(type="text", text=text_content)
        else:
            # 其他类型，转换为字符串
            return TextPart(type="text", text=str(provider_text))

    def _ir_image_to_p(self, image_part: ImagePart) -> Any:
        """IR ImagePart → Provider Image Content / IR图像部分转换为Argo图像内容

        Argo使用OpenAI兼容的图像格式：
        {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}

        注意：Argo API 只接受 base64 编码的图像（data URL）。
        如果 image_url 是 HTTP/HTTPS URL，调用者应该先使用
        utils.image_processing.process_chat_images() 将其转换为 base64。

        Args:
            image_part: IR格式的图像部分，可以包含：
                - image_url: data URL（data:image/png;base64,...）
                - image_data: base64编码的图像数据
                - detail: 图像细节级别（auto/low/high）

        Returns:
            Argo格式的图像内容字典
        """
        from ..utils.image_processing import is_http_url

        # 获取图像URL或数据
        image_url = image_part.get("image_url")
        image_data = image_part.get("image_data")
        detail = image_part.get("detail", "auto")

        # 构建最终的URL
        if image_url:
            # 确保 image_url 是字符串类型
            if not isinstance(image_url, str):
                image_url = str(image_url) if image_url is not None else ""

            # 检查是否是 HTTP/HTTPS URL（Argo 不支持）
            if is_http_url(image_url):
                raise ValueError(
                    f"Argo API does not support HTTP/HTTPS image URLs. "
                    f"Please use utils.image_processing.process_chat_images() "
                    f"to convert the URL to base64 first. URL: {image_url[:100]}..."
                )
            # 使用提供的 data URL
            final_url = image_url
        elif image_data:
            # 将base64数据转换为data URL
            media_type = image_data.get("media_type", "image/jpeg")
            data = image_data.get("data", "")
            final_url = f"data:{media_type};base64,{data}"
        else:
            raise ValueError("ImagePart must have either image_url or image_data")

        # 返回Argo/OpenAI兼容格式
        return {"type": "image_url", "image_url": {"url": final_url, "detail": detail}}

    def _p_image_to_ir(self, provider_image: Any) -> ImagePart:
        """Provider Image Content → IR ImagePart / Argo图像内容转换为IR图像部分

        Argo使用OpenAI兼容格式，需要解析：
        {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}

        Args:
            provider_image: Argo格式的图像内容字典

        Returns:
            IR格式的ImagePart
        """
        import re

        if not isinstance(provider_image, dict):
            raise ValueError("Provider image must be a dictionary")

        # 提取image_url对象
        image_url_obj = provider_image.get("image_url", {})
        url = image_url_obj.get("url", "")
        detail = image_url_obj.get("detail", "auto")

        # 确保 url 是字符串类型
        if not isinstance(url, str):
            url = str(url) if url is not None else ""

        # 检查是否是data URL（base64编码）
        if url.startswith("data:"):
            # 解析data URL: data:image/png;base64,iVBORw0KG...
            match = re.match(r"data:([^;]+);base64,(.+)", url)
            if match:
                media_type, data = match.groups()
                return ImagePart(
                    type="image",
                    image_data={"data": data, "media_type": media_type},
                    detail=detail,
                )

        # 否则是普通URL（HTTP/HTTPS）
        return ImagePart(type="image", image_url=url, detail=detail)

    def _ir_file_to_p(self, file_part: FilePart) -> Any:
        """IR FilePart → Provider File Content / IR文件部分转换为Provider文件内容

        注意：文件处理功能尚未实现，上游 LLMIR 转换器也未提供此功能
        """
        raise NotImplementedError(
            "File handling is not yet implemented. "
            "The upstream LLMIR converters do not provide file conversion functionality."
        )

    def _p_file_to_ir(self, provider_file: Any) -> FilePart:
        """Provider File Content → IR FilePart / Provider文件内容转换为IR文件部分

        注意：文件处理功能尚未实现，上游 LLMIR 转换器也未提供此功能
        """
        raise NotImplementedError(
            "File handling is not yet implemented. "
            "The upstream LLMIR converters do not provide file conversion functionality."
        )

    def _ir_tool_call_to_p(self, tool_call_part: ToolCallPart) -> Any:
        """IR ToolCallPart → Provider Tool Call / IR工具调用部分转换为OpenAI工具调用

        统一使用 OpenAI 格式，在 to_provider 层面处理不同模型家族的转换
        """
        return self._openai_converter._ir_tool_call_to_p(tool_call_part)

    def _p_tool_call_to_ir(self, provider_tool_call: Any) -> ToolCallPart:
        """Provider Tool Call → IR ToolCallPart / OpenAI工具调用转换为IR工具调用部分

        统一使用 OpenAI 格式，在 from_provider 层面处理不同模型家族的转换
        """
        return self._openai_converter._p_tool_call_to_ir(provider_tool_call)

    def _ir_tool_result_to_p(self, tool_result_part: ToolResultPart) -> Any:
        """IR ToolResultPart → Provider Tool Result / IR工具结果部分转换为Argo工具结果

        统一使用 OpenAI 格式的工具结果，所有模型家族都支持：
        {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            tool_result_part: IR格式的工具结果部分

        Returns:
            Argo格式的工具结果消息（OpenAI 格式）
        """
        tool_call_id = tool_result_part.get("tool_call_id", "")
        content = tool_result_part.get("content", "")

        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}

    def _p_tool_result_to_ir(self, provider_tool_result: Any) -> ToolResultPart:
        """Provider Tool Result → IR ToolResultPart / Argo工具结果转换为IR工具结果部分

        统一使用 OpenAI 格式的工具结果：
        {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            provider_tool_result: Argo格式的工具结果消息（OpenAI 格式）

        Returns:
            IR格式的ToolResultPart
        """
        if not isinstance(provider_tool_result, dict):
            raise ValueError("Provider tool result must be a dictionary")

        if provider_tool_result.get("role") != "tool":
            raise ValueError("Tool result must have role 'tool'")

        return ToolResultPart(
            type="tool_result",
            tool_call_id=provider_tool_result.get("tool_call_id", ""),
            content=provider_tool_result.get("content", ""),
        )

    def _ir_tool_to_p(self, tool: ToolDefinition) -> Any:
        """IR ToolDefinition → Provider Tool Definition / IR工具定义转换为OpenAI工具定义

        统一使用 OpenAI 格式，在 to_provider 层面处理不同模型家族的转换
        """
        return self._openai_converter._ir_tool_to_p(tool)

    def _p_tool_to_ir(self, provider_tool: Any) -> ToolDefinition:
        """Provider Tool Definition → IR ToolDefinition / OpenAI工具定义转换为IR工具定义

        统一使用 OpenAI 格式，在 from_provider 层面处理不同模型家族的转换
        """
        return self._openai_converter._p_tool_to_ir(provider_tool)

    # ==================== Argo 特定的工具转换方法 Argo-specific tool conversion methods ====================

    def ir_tool_to_argo(
        self, tool: ToolDefinition, model_family: str = "openai"
    ) -> Any:
        """IR ToolDefinition → Argo Tool Definition / IR工具定义转换为Argo工具定义

        使用 LLMIR 的现有转换器进行格式转换：
        - OpenAI 模型：使用 OpenAIChatConverter
        - Anthropic 模型：使用 AnthropicConverter
        - Google 模型：使用 GoogleConverter

        Args:
            tool: IR格式的工具定义
            model_family: 模型家族 ("openai", "anthropic", "google")

        Returns:
            Argo格式的工具定义字典
        """
        if model_family == "openai":
            return self._openai_converter._ir_tool_to_p(tool)
        elif model_family == "anthropic":
            return self._anthropic_converter._ir_tool_to_p(tool)
        elif model_family == "google":
            return self._google_converter._ir_tool_to_p(tool)
        else:
            # 默认使用 OpenAI 格式
            return self._openai_converter._ir_tool_to_p(tool)

    def argo_tool_to_ir(
        self, provider_tool: Any, model_family: str = "openai"
    ) -> ToolDefinition:
        """Argo Tool Definition → IR ToolDefinition / Argo工具定义转换为IR工具定义

        使用 LLMIR 的现有转换器进行格式转换

        Args:
            provider_tool: Argo格式的工具定义字典
            model_family: 模型家族 ("openai", "anthropic", "google")

        Returns:
            IR格式的ToolDefinition
        """
        if model_family == "openai":
            return self._openai_converter._p_tool_to_ir(provider_tool)
        elif model_family == "anthropic":
            return self._anthropic_converter._p_tool_to_ir(provider_tool)
        elif model_family == "google":
            return self._google_converter._p_tool_to_ir(provider_tool)
        else:
            # 默认使用 OpenAI 格式
            return self._openai_converter._p_tool_to_ir(provider_tool)

    def _ir_tool_choice_to_p(self, tool_choice: ToolChoice) -> Any:
        """IR ToolChoice → Provider Tool Choice Config / IR工具选择转换为OpenAI工具选择配置

        统一使用 OpenAI 格式，在 to_provider 层面处理不同模型家族的转换
        """
        return self._openai_converter._ir_tool_choice_to_p(tool_choice)

    def _p_tool_choice_to_ir(self, provider_tool_choice: Any) -> ToolChoice:
        """Provider Tool Choice Config → IR ToolChoice / OpenAI工具选择配置转换为IR工具选择

        统一使用 OpenAI 格式，在 from_provider 层面处理不同模型家族的转换
        """
        return self._openai_converter._p_tool_choice_to_ir(provider_tool_choice)

    def ir_tool_choice_to_argo(
        self, tool_choice: ToolChoice, model_family: str = "openai"
    ) -> Any:
        """IR ToolChoice → Argo Tool Choice Config / IR工具选择转换为Argo工具选择配置

        使用 LLMIR 的现有转换器进行格式转换

        Args:
            tool_choice: IR格式的工具选择配置
            model_family: 模型家族 ("openai", "anthropic", "google")

        Returns:
            Argo格式的工具选择配置
        """
        if model_family == "openai":
            return self._openai_converter._ir_tool_choice_to_p(tool_choice)
        elif model_family == "anthropic":
            return self._anthropic_converter._ir_tool_choice_to_p(tool_choice)
        elif model_family == "google":
            return self._google_converter._ir_tool_choice_to_p(tool_choice)
        else:
            # 默认使用 OpenAI 格式
            return self._openai_converter._ir_tool_choice_to_p(tool_choice)

    def argo_tool_choice_to_ir(
        self, provider_tool_choice: Any, model_family: str = "openai"
    ) -> ToolChoice:
        """Argo Tool Choice Config → IR ToolChoice / Argo工具选择配置转换为IR工具选择

        使用 LLMIR 的现有转换器进行格式转换

        Args:
            provider_tool_choice: Argo格式的工具选择配置
            model_family: 模型家族 ("openai", "anthropic", "google")

        Returns:
            IR格式的ToolChoice
        """
        if model_family == "openai":
            return self._openai_converter._p_tool_choice_to_ir(provider_tool_choice)
        elif model_family == "anthropic":
            return self._anthropic_converter._p_tool_choice_to_ir(provider_tool_choice)
        elif model_family == "google":
            return self._google_converter._p_tool_choice_to_ir(provider_tool_choice)
        else:
            # 默认使用 OpenAI 格式
            return self._openai_converter._p_tool_choice_to_ir(provider_tool_choice)

    # ==================== Argo 特定的工具调用转换方法 Argo-specific tool call conversion methods ====================

    def ir_tool_call_to_argo(
        self, tool_call_part: ToolCallPart, model_family: str = "openai"
    ) -> Any:
        """IR ToolCallPart → Argo Tool Call / IR工具调用部分转换为Argo工具调用

        使用 LLMIR 的现有转换器进行格式转换：
        - OpenAI 模型：使用 OpenAIChatConverter
        - Anthropic 模型：使用 AnthropicConverter
        - Google 模型：使用 GoogleConverter

        Args:
            tool_call_part: IR格式的工具调用部分
            model_family: 模型家族 ("openai", "anthropic", "google")

        Returns:
            Argo格式的工具调用
        """
        if model_family == "openai":
            return self._openai_converter._ir_tool_call_to_p(tool_call_part)
        elif model_family == "anthropic":
            return self._anthropic_converter._ir_tool_call_to_p(tool_call_part)
        elif model_family == "google":
            return self._google_converter._ir_tool_call_to_p(tool_call_part)
        else:
            # 默认使用 OpenAI 格式
            return self._openai_converter._ir_tool_call_to_p(tool_call_part)

    def argo_tool_call_to_ir(
        self, provider_tool_call: Any, model_family: str = "openai"
    ) -> ToolCallPart:
        """Argo Tool Call → IR ToolCallPart / Argo工具调用转换为IR工具调用部分

        使用 LLMIR 的现有转换器进行格式转换

        Args:
            provider_tool_call: Argo格式的工具调用
            model_family: 模型家族 ("openai", "anthropic", "google")

        Returns:
            IR格式的ToolCallPart
        """
        if model_family == "openai":
            return self._openai_converter._p_tool_call_to_ir(provider_tool_call)
        elif model_family == "anthropic":
            return self._anthropic_converter._p_tool_call_to_ir(provider_tool_call)
        elif model_family == "google":
            return self._google_converter._p_tool_call_to_ir(provider_tool_call)
        else:
            # 默认使用 OpenAI 格式
            return self._openai_converter._p_tool_call_to_ir(provider_tool_call)

    # ==================== 格式转换辅助方法 Format conversion helper methods ====================

    def _convert_openai_to_target_format(
        self, openai_data: Dict[str, Any], model_family: str
    ) -> Dict[str, Any]:
        """将 OpenAI 格式转换为目标模型家族格式
        Convert OpenAI format to target model family format

        Args:
            openai_data: OpenAI 格式的数据
            model_family: 目标模型家族 ("anthropic", "google")

        Returns:
            目标格式的数据
        """
        if model_family == "anthropic":
            # 使用 Anthropic 转换器的 from_provider 方法
            # 注意：这里需要将 OpenAI 格式先转换为 IR，再转换为 Anthropic 格式
            ir_data = self._openai_converter.from_provider(openai_data)
            return self._anthropic_converter.to_provider(ir_data)[
                0
            ]  # 只取数据，忽略警告
        elif model_family == "google":
            # 使用 Google 转换器
            ir_data = self._openai_converter.from_provider(openai_data)
            return self._google_converter.to_provider(ir_data)[0]  # 只取数据，忽略警告
        else:
            # 未知格式，返回原始 OpenAI 格式
            return openai_data

    def _convert_target_to_openai_format(
        self, target_data: Any, model_family: str
    ) -> Dict[str, Any]:
        """将目标模型家族格式转换为 OpenAI 格式
        Convert target model family format to OpenAI format

        Args:
            target_data: 目标格式的数据
            model_family: 源模型家族 ("anthropic", "google")

        Returns:
            OpenAI 格式的数据
        """
        if model_family == "anthropic":
            # 使用 Anthropic 转换器的 from_provider 方法
            ir_data = self._anthropic_converter.from_provider(target_data)
            return self._openai_converter.to_provider(ir_data)[0]  # 只取数据，忽略警告
        elif model_family == "google":
            # 使用 Google 转换器
            ir_data = self._google_converter.from_provider(target_data)
            return self._openai_converter.to_provider(ir_data)[0]  # 只取数据，忽略警告
        else:
            # 未知格式，假设已经是 OpenAI 格式
            return target_data


# ==================== LLMIR-based Chat Processing Functions ====================


async def process_chat_with_llmir(
    request: web.Request,
    *,
    convert_to_openai: bool = True,
) -> Union[web.Response, web.StreamResponse]:
    """使用 LLMIR 处理 chat completions 请求
    Process chat completions request using LLMIR

    这个函数使用 ArgoConverter 和 LLMIR 的统一接口来处理聊天请求，
    提供更标准化和可维护的转换逻辑。

    Args:
        request: 客户端的 web 请求对象
        convert_to_openai: 是否转换为 OpenAI 兼容格式

    Returns:
        web.Response 或 web.StreamResponse
    """
    config: ArgoConfig = request.app["config"]
    model_registry: ModelRegistry = request.app["model_registry"]

    try:
        # 获取请求数据
        data = await request.json()
        stream = data.get("stream", False)

        if not data:
            raise ValueError("Invalid input. Expected JSON data.")

        if config.verbose:
            logger.info(make_bar("[LLMIR chat] input"))
            logger.info(json.dumps(sanitize_data_for_logging(data), indent=4))
            logger.info(make_bar())

        # 使用共享的 HTTP 会话
        session = request.app["http_session"]

        # 处理图像 URL
        data = await process_chat_images(session, data, config)

        # 应用用户名透传
        apply_username_passthrough(data, request, config.user)

        # 自动替换用户信息
        data["user"] = config.user

        # 重新映射模型名称
        if "model" not in data:
            data["model"] = "argo:gpt-4o"  # DEFAULT_MODEL
        data["model"] = model_registry.resolve_model_name(
            data["model"], model_type="chat"
        )

        # 创建 ArgoConverter 实例
        converter = ArgoConverter()

        # 将请求数据转换为 IR 格式（自动处理模型家族检测）
        ir_request = converter.from_provider(data)

        # 将 IR 格式转换回 Argo 格式（应用标准化处理和模型家族转换）
        argo_data, warnings = converter.to_provider(ir_request)

        # 记录警告信息
        for warning in warnings:
            logger.warning(f"[LLMIR] {warning}")

        if config.verbose:
            logger.info(make_bar("[LLMIR chat] processed data"))
            logger.info(json.dumps(sanitize_data_for_logging(argo_data), indent=4))
            logger.info(make_bar())

        # 目前只支持非流式模式
        if stream:
            return web.json_response(
                {
                    "object": "error",
                    "message": "LLMIR mode currently only supports non-streaming requests",
                    "type": "llmir_streaming_not_supported",
                },
                status=HTTPStatus.NOT_IMPLEMENTED,
            )

        # 发送非流式请求
        return await _send_llmir_non_streaming_request(
            session, config, argo_data, convert_to_openai=convert_to_openai
        )

    except ValueError as err:
        logger.error(f"ValueError: {err}")
        return web.json_response(
            {"error": str(err)},
            status=HTTPStatus.BAD_REQUEST,
            content_type="application/json",
        )
    except aiohttp.ClientError as err:
        error_message = f"HTTP error occurred: {err}"
        logger.error(error_message)
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
            content_type="application/json",
        )
    except Exception as err:
        error_message = f"An unexpected error occurred in LLMIR mode: {err}"
        logger.error(error_message)
        # 添加详细的错误信息用于调试
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return web.json_response(
            {"error": error_message},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
            content_type="application/json",
        )


async def _send_llmir_non_streaming_request(
    session: aiohttp.ClientSession,
    config,  # ArgoConfig
    data: Dict[str, Any],
    *,
    convert_to_openai: bool = False,
) -> web.Response:
    """发送 LLMIR 处理后的非流式请求
    Send LLMIR-processed non-streaming request

    Args:
        session: 客户端会话
        config: Argo 配置对象
        data: LLMIR 处理后的请求数据
        convert_to_openai: 是否转换为 OpenAI 格式

    Returns:
        web.Response
    """
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(
            config.argo_url, headers=headers, json=data
        ) as upstream_resp:
            try:
                response_data = await upstream_resp.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError):
                return web.json_response(
                    {
                        "object": "error",
                        "message": "Upstream error: Invalid JSON response from upstream server",
                        "type": "upstream_invalid_json",
                    },
                    status=502,
                )

            # 处理响应格式
            response_content = response_data.get("response")
            if response_content is None:
                return web.json_response(
                    {
                        "object": "error",
                        "message": "Upstream model returned no response. Please try different request parameters.",
                        "type": "upstream_no_response",
                    },
                    status=502,
                )

            if not convert_to_openai:  # 直接透传
                return web.json_response(
                    response_data,
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # 转换为 OpenAI 格式
            prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])
            completion_tokens = (
                await count_tokens_async(response_content, data["model"])
                if response_content
                else 0
            )
            total_tokens = prompt_tokens + completion_tokens

            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            # 构建 OpenAI 兼容响应
            openai_response = ChatCompletion(
                id=str(uuid.uuid4().hex),
                created=int(time.time()),
                model=data.get("model", "unknown"),
                choices=[
                    NonStreamChoice(
                        index=0,
                        message=ChatCompletionMessage(
                            content=response_content,
                            tool_calls=None,  # TODO: 处理工具调用
                        ),
                        finish_reason="stop",
                    )
                ],
                usage=usage,
            )

            return web.json_response(
                openai_response.model_dump(),
                status=upstream_resp.status,
                content_type="application/json",
            )

    except aiohttp.ClientResponseError as err:
        return web.json_response(
            {
                "object": "error",
                "message": f"Upstream error: {err}",
                "type": "upstream_api_error",
            },
            status=err.status,
        )
