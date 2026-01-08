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
        **kwargs,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """将IR格式转换为Argo Gateway API特定格式
        Convert IR format to Argo Gateway API specific format

        Args:
            ir_input: IR格式的输入或完整请求 / IR format input or full request
            tools: 工具定义列表（如果ir_input不是IRRequest） / Tool definition list (if ir_input is not IRRequest)
            tool_choice: 工具选择配置（如果ir_input不是IRRequest） / Tool choice configuration (if ir_input is not IRRequest)
            **kwargs: 额外的参数 / Additional parameters

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

        # 转换消息列表（使用 IR 作为中间格式的抽象方法）
        argo_messages = []
        for message in messages:
            argo_message = self._ir_message_to_p(message, messages, **kwargs)
            argo_messages.append(argo_message)

        # 构建 Argo Gateway API 格式的数据
        argo_data = {"messages": argo_messages}

        # 添加工具相关字段（如果存在，使用 IR 作为中间格式）
        if request_tools:
            argo_tools = []
            for tool in request_tools:
                tool_kwargs = {**kwargs, "model_family": model_family}
                argo_tool = self._ir_tool_to_p(tool, **tool_kwargs)
                argo_tools.append(argo_tool)
            argo_data["tools"] = argo_tools

        if request_tool_choice:
            choice_kwargs = {**kwargs, "model_family": model_family}
            argo_tool_choice = self._ir_tool_choice_to_p(
                request_tool_choice, **choice_kwargs
            )
            argo_data["tool_choice"] = argo_tool_choice

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
                    argo_data[field] = ir_input[field]

        # 直接返回 Argo Gateway API 格式的数据，不需要额外转换
        # IR 已经作为中间格式处理了不同模型家族的差异
        return argo_data, warnings

    def from_provider(
        self, provider_data: Any, **kwargs
    ) -> Union[IRInput, Dict[str, Any]]:
        """将Argo Gateway API特定格式转换为IR格式
        Convert Argo Gateway API specific format to IR format

        Args:
            provider_data: Argo Gateway API特定格式的数据 / Argo Gateway API specific format data
            **kwargs: 额外的参数 / Additional parameters

        Returns:
            IR格式的数据（消息列表或完整响应） / IR format data (message list or full response)
        """
        logger.info(
            f"[LLMIR DEBUG] from_provider called with data type: {type(provider_data)}"
        )

        # 确定模型家族
        model_name = ""
        if isinstance(provider_data, dict):
            model_name = provider_data.get("model", "")
            logger.info(
                f"[LLMIR DEBUG] Extracted model_name: {model_name} (type: {type(model_name)})"
            )

        # 确保 model_name 是字符串类型
        if not isinstance(model_name, str):
            logger.info(f"[LLMIR DEBUG] Converting model_name to string: {model_name}")
            model_name = str(model_name) if model_name is not None else ""

        logger.info(f"[LLMIR DEBUG] Determining model family for: '{model_name}'")
        model_family = determine_model_family(model_name) if model_name else "openai"
        if model_family == "unknown":
            model_family = "openai"  # 默认使用 OpenAI 格式
        logger.info(f"[LLMIR DEBUG] Determined model_family: {model_family}")

        # 直接使用 provider_data，因为 IR 已经作为中间格式处理了不同模型家族的差异
        argo_data = provider_data

        # 使用 IR 作为中间格式的抽象方法进行转换
        logger.info(f"[LLMIR DEBUG] Processing argo_data type: {type(argo_data)}")
        if isinstance(argo_data, dict):
            if "messages" in argo_data:
                logger.info(
                    f"[LLMIR DEBUG] Processing {len(argo_data['messages'])} messages"
                )
                # 这是一个完整的请求/响应
                ir_messages = []
                for i, message in enumerate(argo_data["messages"]):
                    logger.info(
                        f"[LLMIR DEBUG] Processing message {i}: {type(message)}"
                    )
                    try:
                        ir_message = self._p_message_to_ir(message, **kwargs)
                        ir_messages.append(ir_message)
                        logger.info(f"[LLMIR DEBUG] Message {i} converted successfully")
                    except Exception as e:
                        logger.error(f"[LLMIR DEBUG] Error converting message {i}: {e}")
                        raise

                # 构建 IR 请求
                ir_data = {"messages": ir_messages}

                # 处理工具相关字段
                if "tools" in argo_data:
                    logger.info(
                        f"[LLMIR DEBUG] Processing {len(argo_data['tools'])} tools"
                    )
                    ir_tools = []
                    for i, tool in enumerate(argo_data["tools"]):
                        logger.info(f"[LLMIR DEBUG] Processing tool {i}: {type(tool)}")
                        try:
                            tool_kwargs = {**kwargs, "model_family": model_family}
                            ir_tool = self._p_tool_to_ir(tool, **tool_kwargs)
                            ir_tools.append(ir_tool)
                            logger.info(
                                f"[LLMIR DEBUG] Tool {i} converted successfully"
                            )
                        except Exception as e:
                            logger.error(
                                f"[LLMIR DEBUG] Error converting tool {i}: {e}"
                            )
                            raise
                    ir_data["tools"] = ir_tools

                if "tool_choice" in argo_data:
                    logger.info(
                        f"[LLMIR DEBUG] Processing tool_choice: {argo_data['tool_choice']}"
                    )
                    try:
                        choice_kwargs = {**kwargs, "model_family": model_family}
                        ir_tool_choice = self._p_tool_choice_to_ir(
                            argo_data["tool_choice"], **choice_kwargs
                        )
                        ir_data["tool_choice"] = ir_tool_choice
                        logger.info("[LLMIR DEBUG] tool_choice converted successfully")
                    except Exception as e:
                        logger.error(f"[LLMIR DEBUG] Error converting tool_choice: {e}")
                        raise

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
                    if field in argo_data:
                        ir_data[field] = argo_data[field]

                return ir_data
            else:
                # 这可能是一个单独的消息
                return self._p_message_to_ir(argo_data, **kwargs)
        elif isinstance(argo_data, list):
            # 这是一个消息列表
            ir_messages = []
            for message in argo_data:
                ir_message = self._p_message_to_ir(message, **kwargs)
                ir_messages.append(ir_message)
            return ir_messages
        else:
            raise ValueError(f"Unsupported provider data format: {type(argo_data)}")

    # ==================== 分层抽象方法 Layered abstract methods ====================

    def _ir_message_to_p(
        self, message: Dict[str, Any], ir_input: IRInput, **kwargs
    ) -> Any:
        """IR Message → Argo Gateway API Message / IR消息转换为Argo Gateway API消息

        将 IR 格式的消息转换为 Argo Gateway API 兼容的消息格式

        Args:
            message: IR格式的消息
            ir_input: 完整的IR输入（用于上下文）
            **kwargs: 额外的参数 / Additional parameters

        Returns:
            Argo Gateway API格式的消息
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
                argo_part = self._ir_content_part_to_p(part, ir_input, **kwargs)
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
                # 使用 IR 作为中间格式的抽象方法
                # 从 ir_input 中获取 model_family 信息
                model_name = ""
                if isinstance(ir_input, dict) and "model" in ir_input:
                    model_name = ir_input["model"]
                elif hasattr(ir_input, "model"):
                    model_name = getattr(ir_input, "model", "")

                model_family = (
                    determine_model_family(model_name) if model_name else "openai"
                )
                if model_family == "unknown":
                    model_family = "openai"

                tool_call_kwargs = {**kwargs, "model_family": model_family}
                argo_tool_call = self._ir_tool_call_to_p(tool_call, **tool_call_kwargs)
                tool_calls.append(argo_tool_call)
            argo_message["tool_calls"] = tool_calls

        # 处理其他字段
        for field in ["name", "tool_call_id"]:
            if field in message:
                argo_message[field] = message[field]

        return argo_message

    def _ir_content_part_to_p(
        self, content_part: Dict[str, Any], ir_input: IRInput, **kwargs
    ) -> Any:
        """IR ContentPart → Argo Gateway API Content/Part / IR内容部分转换为Argo Gateway API内容部分

        Args:
            content_part: IR格式的内容部分
            ir_input: 完整的IR输入（用于上下文）
            **kwargs: 额外的参数 / Additional parameters

        Returns:
            Argo Gateway API格式的内容部分
        """
        part_type = content_part.get("type")

        if part_type == "text":
            return self._ir_text_to_p(content_part, **kwargs)
        elif part_type == "image":
            return self._ir_image_to_p(content_part, **kwargs)
        elif part_type == "file":
            return self._ir_file_to_p(content_part, **kwargs)
        elif part_type == "tool_call":
            # 从 ir_input 中获取 model_family 信息
            model_name = ""
            if isinstance(ir_input, dict) and "model" in ir_input:
                model_name = ir_input["model"]
            elif hasattr(ir_input, "model"):
                model_name = getattr(ir_input, "model", "")

            model_family = (
                determine_model_family(model_name) if model_name else "openai"
            )
            if model_family == "unknown":
                model_family = "openai"

            tool_call_kwargs = {**kwargs, "model_family": model_family}
            return self._ir_tool_call_to_p(content_part, **tool_call_kwargs)
        elif part_type == "tool_result":
            return self._ir_tool_result_to_p(content_part, **kwargs)
        else:
            # 未知类型，尝试作为文本处理
            return {
                "type": "text",
                "text": str(content_part.get("content", content_part)),
            }

    def _p_message_to_ir(self, provider_message: Any, **kwargs) -> Dict[str, Any]:
        """Argo Gateway API Message → IR Message / Argo Gateway API消息转换为IR消息

        Args:
            provider_message: Argo Gateway API格式的消息
            **kwargs: 额外的参数 / Additional parameters

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
            ir_message["content"] = [self._p_text_to_ir(content, **kwargs)]
        elif isinstance(content, list):
            # 内容部分列表
            ir_content = []
            for part in content:
                ir_parts = self._p_content_part_to_ir(part, **kwargs)
                ir_content.extend(ir_parts)
            ir_message["content"] = ir_content
        elif content is not None:
            # 其他格式，转换为文本
            ir_message["content"] = [self._p_text_to_ir(str(content), **kwargs)]
        else:
            ir_message["content"] = []

        # 处理工具调用（如果存在）
        if "tool_calls" in provider_message:
            tool_calls = []
            for tool_call in provider_message["tool_calls"]:
                # 从 kwargs 中获取 model_family，如果没有则默认为 openai
                model_family = kwargs.get("model_family", "openai")
                tool_call_kwargs = {**kwargs, "model_family": model_family}
                ir_tool_call = self._p_tool_call_to_ir(tool_call, **tool_call_kwargs)
                tool_calls.append(ir_tool_call)
            ir_message["tool_calls"] = tool_calls

        # 处理其他字段
        for field in ["name", "tool_call_id"]:
            if field in provider_message:
                ir_message[field] = provider_message[field]

        return ir_message

    def _p_content_part_to_ir(
        self, provider_part: Any, **kwargs
    ) -> List[Dict[str, Any]]:
        """Argo Gateway API Content/Part → IR ContentPart(s) / Argo Gateway API内容部分转换为IR内容部分

        Args:
            provider_part: Argo Gateway API格式的内容部分
            **kwargs: 额外的参数 / Additional parameters

        Returns:
            IR格式的内容部分列表
        """
        if isinstance(provider_part, str):
            # 简单字符串
            return [self._p_text_to_ir(provider_part, **kwargs)]
        elif isinstance(provider_part, dict):
            part_type = provider_part.get("type")

            if part_type == "text":
                return [self._p_text_to_ir(provider_part, **kwargs)]
            elif part_type == "image_url":
                return [self._p_image_to_ir(provider_part, **kwargs)]
            elif part_type == "tool_call":
                # 从 kwargs 中获取 model_family，如果没有则默认为 openai
                model_family = kwargs.get("model_family", "openai")
                tool_call_kwargs = {**kwargs, "model_family": model_family}
                return [self._p_tool_call_to_ir(provider_part, **tool_call_kwargs)]
            elif part_type == "tool_result":
                return [self._p_tool_result_to_ir(provider_part, **kwargs)]
            else:
                # 未知类型，尝试作为文本处理
                return [self._p_text_to_ir(str(provider_part), **kwargs)]
        else:
            # 其他类型，转换为文本
            return [self._p_text_to_ir(str(provider_part), **kwargs)]

    # ==================== 共性内容类型转换接口 Common content type conversion interfaces ====================

    def _ir_text_to_p(self, text_part: TextPart, **kwargs) -> Any:
        """IR TextPart → Argo Gateway API Text Content / IR文本部分转换为Argo Gateway API文本内容"""
        return {"type": "text", "text": text_part["text"]}

    def _p_text_to_ir(self, provider_text: Any, **kwargs) -> TextPart:
        """Argo Gateway API Text Content → IR TextPart / Argo Gateway API文本内容转换为IR文本部分

        Argo Gateway API 支持多种文本格式：
        1. 简单字符串：直接文本内容
        2. OpenAI 格式：{"type": "text", "text": "..."}
        3. 其他格式的文本内容

        Args:
            provider_text: Argo Gateway API格式的文本内容
            **kwargs: 额外的参数 / Additional parameters

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

    def _ir_image_to_p(self, image_part: ImagePart, **kwargs) -> Any:
        """IR ImagePart → Argo Gateway API Image Content / IR图像部分转换为Argo Gateway API图像内容

        Argo Gateway API使用OpenAI兼容的图像格式：
        {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}

        注意：Argo Gateway API 只接受 base64 编码的图像（data URL）。
        如果 image_url 是 HTTP/HTTPS URL，调用者应该先使用
        utils.image_processing.process_chat_images() 将其转换为 base64。

        Args:
            image_part: IR格式的图像部分，可以包含：
                - image_url: data URL（data:image/png;base64,...）
                - image_data: base64编码的图像数据
                - detail: 图像细节级别（auto/low/high）
            **kwargs: 额外的参数 / Additional parameters

        Returns:
            Argo Gateway API格式的图像内容字典
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

            # 检查是否是 HTTP/HTTPS URL（Argo Gateway API 不支持）
            if is_http_url(image_url):
                raise ValueError(
                    f"Argo Gateway API does not support HTTP/HTTPS image URLs. "
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

        # 返回Argo Gateway API/OpenAI兼容格式
        return {"type": "image_url", "image_url": {"url": final_url, "detail": detail}}

    def _p_image_to_ir(self, provider_image: Any, **kwargs) -> ImagePart:
        """Argo Gateway API Image Content → IR ImagePart / Argo Gateway API图像内容转换为IR图像部分

        Argo Gateway API使用OpenAI兼容格式，需要解析：
        {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}

        Args:
            provider_image: Argo Gateway API格式的图像内容字典
            **kwargs: 额外的参数 / Additional parameters

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

    def _ir_file_to_p(self, file_part: FilePart, **kwargs) -> Any:
        """IR FilePart → Argo Gateway API File Content / IR文件部分转换为Argo Gateway API文件内容

        注意：文件处理功能尚未实现，上游 LLMIR 转换器也未提供此功能
        """
        raise NotImplementedError(
            "File handling is not yet implemented. "
            "The upstream LLMIR converters do not provide file conversion functionality."
        )

    def _p_file_to_ir(self, provider_file: Any, **kwargs) -> FilePart:
        """Argo Gateway API File Content → IR FilePart / Argo Gateway API文件内容转换为IR文件部分

        注意：文件处理功能尚未实现，上游 LLMIR 转换器也未提供此功能
        """
        raise NotImplementedError(
            "File handling is not yet implemented. "
            "The upstream LLMIR converters do not provide file conversion functionality."
        )

    def _ir_tool_call_to_p(self, tool_call_part: ToolCallPart, **kwargs) -> Any:
        """IR ToolCallPart → Argo Gateway API Tool Call / IR工具调用部分转换为Argo Gateway API工具调用

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器
        """
        model_family = kwargs.get("model_family", "openai")
        if model_family == "anthropic":
            return self._anthropic_converter._ir_tool_call_to_p(
                tool_call_part, **kwargs
            )
        elif model_family == "google":
            return self._google_converter._ir_tool_call_to_p(tool_call_part, **kwargs)
        else:
            return self._openai_converter._ir_tool_call_to_p(tool_call_part, **kwargs)

    def _p_tool_call_to_ir(self, provider_tool_call: Any, **kwargs) -> ToolCallPart:
        """Argo Gateway API Tool Call → IR ToolCallPart / Argo Gateway API工具调用转换为IR工具调用部分

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器
        """
        model_family = kwargs.get("model_family", "openai")
        if model_family == "anthropic":
            return self._anthropic_converter._p_tool_call_to_ir(
                provider_tool_call, **kwargs
            )
        elif model_family == "google":
            return self._google_converter._p_tool_call_to_ir(
                provider_tool_call, **kwargs
            )
        else:
            return self._openai_converter._p_tool_call_to_ir(
                provider_tool_call, **kwargs
            )

    def _ir_tool_result_to_p(self, tool_result_part: ToolResultPart, **kwargs) -> Any:
        """IR ToolResultPart → Argo Gateway API Tool Result / IR工具结果部分转换为Argo Gateway API工具结果

        使用 IR 作为中间格式的工具结果，所有模型家族都支持：
        {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            tool_result_part: IR格式的工具结果部分
            **kwargs: 额外的参数 / Additional parameters

        Returns:
            Argo Gateway API格式的工具结果消息
        """
        tool_call_id = tool_result_part.get("tool_call_id", "")
        content = tool_result_part.get("content", "")

        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}

    def _p_tool_result_to_ir(
        self, provider_tool_result: Any, **kwargs
    ) -> ToolResultPart:
        """Argo Gateway API Tool Result → IR ToolResultPart / Argo Gateway API工具结果转换为IR工具结果部分

        使用 IR 作为中间格式的工具结果：
        {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            provider_tool_result: Argo Gateway API格式的工具结果消息
            **kwargs: 额外的参数 / Additional parameters

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

    def _ir_tool_to_p(self, tool: ToolDefinition, **kwargs) -> Any:
        """IR ToolDefinition → Argo Gateway API Tool Definition / IR工具定义转换为Argo Gateway API工具定义

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器
        """
        model_family = kwargs.get("model_family", "openai")
        if model_family == "anthropic":
            return self._anthropic_converter._ir_tool_to_p(tool, **kwargs)
        elif model_family == "google":
            return self._google_converter._ir_tool_to_p(tool, **kwargs)
        else:
            return self._openai_converter._ir_tool_to_p(tool, **kwargs)

    def _p_tool_to_ir(self, provider_tool: Any, **kwargs) -> ToolDefinition:
        """Argo Gateway API Tool Definition → IR ToolDefinition / Argo Gateway API工具定义转换为IR工具定义

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器
        """
        model_family = kwargs.get("model_family", "openai")
        if model_family == "anthropic":
            return self._anthropic_converter._p_tool_to_ir(provider_tool, **kwargs)
        elif model_family == "google":
            return self._google_converter._p_tool_to_ir(provider_tool, **kwargs)
        else:
            return self._openai_converter._p_tool_to_ir(provider_tool, **kwargs)

    def _ir_tool_choice_to_p(self, tool_choice: ToolChoice, **kwargs) -> Any:
        """IR ToolChoice → Argo Gateway API Tool Choice Config / IR工具选择转换为Argo Gateway API工具选择配置

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器
        """
        model_family = kwargs.get("model_family", "openai")
        if model_family == "anthropic":
            return self._anthropic_converter._ir_tool_choice_to_p(tool_choice, **kwargs)
        elif model_family == "google":
            return self._google_converter._ir_tool_choice_to_p(tool_choice, **kwargs)
        else:
            return self._openai_converter._ir_tool_choice_to_p(tool_choice, **kwargs)

    def _p_tool_choice_to_ir(self, provider_tool_choice: Any, **kwargs) -> ToolChoice:
        """Argo Gateway API Tool Choice Config → IR ToolChoice / Argo Gateway API工具选择配置转换为IR工具选择

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器
        """
        model_family = kwargs.get("model_family", "openai")
        if model_family == "anthropic":
            return self._anthropic_converter._p_tool_choice_to_ir(
                provider_tool_choice, **kwargs
            )
        elif model_family == "google":
            return self._google_converter._p_tool_choice_to_ir(
                provider_tool_choice, **kwargs
            )
        else:
            return self._openai_converter._p_tool_choice_to_ir(
                provider_tool_choice, **kwargs
            )

    # ==================== 响应解析方法 Response parsing methods ====================

    def parse_argo_response(
        self, response_data: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[List[Any]]]:
        """解析 Argo 上游响应，提取 content 和 tool_calls
        Parse Argo upstream response to extract content and tool_calls

        Argo 的响应格式可能是：
        1. {"response": "text content"}  - 纯文本响应
        2. {"response": {"content": "...", "tool_calls": [...]}}  - 带 tool calls 的响应

        Args:
            response_data: Argo 上游返回的响应数据

        Returns:
            Tuple[content, tool_calls]: 提取的内容和工具调用列表
        """
        response_field = response_data.get("response")

        # 解析响应内容
        if isinstance(response_field, dict):
            # 响应是字典格式，可能包含 content 和 tool_calls
            response_content = response_field.get("content")
            tool_calls = response_field.get("tool_calls")
        elif isinstance(response_field, str):
            # 响应是纯文本
            response_content = response_field
            tool_calls = None
        else:
            # 响应为 None 或其他类型
            response_content = None
            tool_calls = None

        return response_content, tool_calls


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

        try:
            logger.info("[LLMIR DEBUG] Starting from_provider conversion")
            logger.info(f"[LLMIR DEBUG] Input data type: {type(data)}")
            logger.info(
                f"[LLMIR DEBUG] Input data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
            )

            # 将请求数据转换为 IR 格式（自动处理模型家族检测）
            ir_request = converter.from_provider(data)

            logger.info("[LLMIR DEBUG] from_provider conversion completed")
            logger.info(f"[LLMIR DEBUG] IR request type: {type(ir_request)}")
            logger.info(
                f"[LLMIR DEBUG] IR request keys: {list(ir_request.keys()) if isinstance(ir_request, dict) else 'N/A'}"
            )

            logger.info("[LLMIR DEBUG] Starting to_provider conversion")
            # 将 IR 格式转换回 Argo 格式（应用标准化处理和模型家族转换）
            argo_data, warnings = converter.to_provider(ir_request)

            logger.info("[LLMIR DEBUG] to_provider conversion completed")

        except Exception as e:
            logger.error(f"[LLMIR DEBUG] Error during conversion: {e}")
            logger.error(f"[LLMIR DEBUG] Error type: {type(e)}")
            import traceback

            logger.error(f"[LLMIR DEBUG] Full traceback: {traceback.format_exc()}")
            raise

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

            # 直接透传模式
            if not convert_to_openai:
                return web.json_response(
                    response_data,
                    status=upstream_resp.status,
                    content_type="application/json",
                )

            # 使用 ArgoConverter 解析响应
            converter = ArgoConverter()
            response_content, tool_calls = converter.parse_argo_response(response_data)

            # 检查是否有有效的响应（content 或 tool_calls）
            if response_content is None and not tool_calls:
                return web.json_response(
                    {
                        "object": "error",
                        "message": "Upstream model returned no response. Please try different request parameters.",
                        "type": "upstream_no_response",
                    },
                    status=502,
                )

            # 计算 tokens
            prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])
            # 确保 response_content 是字符串类型
            if response_content and isinstance(response_content, str):
                completion_tokens = await count_tokens_async(
                    response_content, data["model"]
                )
            else:
                completion_tokens = 0
            total_tokens = prompt_tokens + completion_tokens

            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

            # 确定 finish_reason
            finish_reason = "tool_calls" if tool_calls else "stop"

            # 构建 OpenAI 兼容响应
            # 注意：当有 tool_calls 时，content 可以为 None（符合 OpenAI 规范）
            openai_response = ChatCompletion(
                id=str(uuid.uuid4().hex),
                created=int(time.time()),
                model=data.get("model", "unknown"),
                choices=[
                    NonStreamChoice(
                        index=0,
                        message=ChatCompletionMessage(
                            content=response_content,
                            tool_calls=tool_calls,
                        ),
                        finish_reason=finish_reason,
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
