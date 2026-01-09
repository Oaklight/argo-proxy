"""
LLMIR - Argo Complex Operations
Argo 复杂转换操作

实现消息、请求、响应级别的转换，包括：
- 消息级转换 (Message ↔ Argo message)
- 内容部分转换 (ContentPart ↔ Argo content part)
- 请求级转换 (IRRequest ↔ Argo request)
- 响应级转换 (IRResponse ↔ Argo response)
"""

import time
import uuid
from typing import Any, Dict, List, Tuple

from llmir.converters.base import BaseComplexOps
from llmir.types.ir_request import IRRequest
from llmir.types.ir_response import IRResponse

from .atomic_ops import ArgoAtomicOps


class ArgoComplexOps(BaseComplexOps):
    """Argo 复杂转换操作

    所有方法都是静态方法，处理消息、请求、响应级别的转换。
    调用 ArgoAtomicOps 处理基础类型转换。
    """

    # ==================== 消息级转换 Message level conversion ====================

    @staticmethod
    def ir_message_to_p(
        message: Dict[str, Any], **kwargs: Any
    ) -> Tuple[Any, List[str]]:
        """IR Message → Argo Message

        将 IR 格式的消息转换为 Argo 兼容的消息格式。

        Args:
            message: IR格式的消息
            **kwargs: 额外参数

        Returns:
            Tuple[Argo格式的消息, 警告信息列表]
        """
        warnings = []
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
                argo_part, part_warnings = ArgoComplexOps.ir_content_part_to_p(
                    part, **kwargs
                )
                if argo_part:
                    argo_content.append(argo_part)
                warnings.extend(part_warnings)

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
                # 使用 ArgoAtomicOps 处理工具调用
                argo_tool_call = ArgoAtomicOps.ir_tool_call_to_p(tool_call, **kwargs)
                tool_calls.append(argo_tool_call)
            argo_message["tool_calls"] = tool_calls

        # 处理其他字段
        for field in ["name", "tool_call_id"]:
            if field in message:
                argo_message[field] = message[field]

        return argo_message, warnings

    @staticmethod
    def ir_content_part_to_p(
        content_part: Dict[str, Any], **kwargs: Any
    ) -> Tuple[Any, List[str]]:
        """IR ContentPart → Argo Content/Part

        Args:
            content_part: IR格式的内容部分
            **kwargs: 额外参数

        Returns:
            Tuple[Argo格式的内容部分, 警告信息列表]
        """
        warnings = []
        part_type = content_part.get("type")

        try:
            if part_type == "text":
                return ArgoAtomicOps.ir_text_to_p(content_part, **kwargs), warnings
            elif part_type == "image":
                return ArgoAtomicOps.ir_image_to_p(content_part, **kwargs), warnings
            elif part_type == "file":
                return ArgoAtomicOps.ir_file_to_p(content_part, **kwargs), warnings
            elif part_type == "tool_call":
                return ArgoAtomicOps.ir_tool_call_to_p(content_part, **kwargs), warnings
            elif part_type == "tool_result":
                return ArgoAtomicOps.ir_tool_result_to_p(
                    content_part, **kwargs
                ), warnings
            else:
                # 未知类型，尝试作为文本处理
                warnings.append(
                    f"Unknown content part type: {part_type}, treating as text"
                )
                return {
                    "type": "text",
                    "text": str(content_part.get("content", content_part)),
                }, warnings
        except Exception as e:
            warnings.append(f"Error converting content part: {e}")
            # 返回错误信息作为文本
            return {
                "type": "text",
                "text": f"[Conversion Error: {e}]",
            }, warnings

    @staticmethod
    def p_message_to_ir(provider_message: Any, **kwargs: Any) -> Dict[str, Any]:
        """Argo Message → IR Message

        Args:
            provider_message: Argo格式的消息
            **kwargs: 额外参数

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
            ir_message["content"] = [ArgoAtomicOps.p_text_to_ir(content, **kwargs)]
        elif isinstance(content, list):
            # 内容部分列表
            ir_content = []
            for part in content:
                ir_parts = ArgoAtomicOps.p_content_part_to_ir(part, **kwargs)
                ir_content.extend(ir_parts)
            ir_message["content"] = ir_content
        elif content is not None:
            # 其他格式，转换为文本
            ir_message["content"] = [ArgoAtomicOps.p_text_to_ir(str(content), **kwargs)]
        else:
            ir_message["content"] = []

        # 处理工具调用（如果存在）
        if "tool_calls" in provider_message:
            tool_calls = []
            for tool_call in provider_message["tool_calls"]:
                # 从 kwargs 中获取 model_family，如果没有则默认为 openai
                model_family = kwargs.get("model_family", "openai")
                tool_call_kwargs = {**kwargs, "model_family": model_family}
                ir_tool_call = ArgoAtomicOps.p_tool_call_to_ir(
                    tool_call, **tool_call_kwargs
                )
                tool_calls.append(ir_tool_call)
            ir_message["tool_calls"] = tool_calls

        # 处理其他字段
        for field in ["name", "tool_call_id"]:
            if field in provider_message:
                ir_message[field] = provider_message[field]

        return ir_message

    # ==================== 请求级转换 Request level conversion ====================

    @staticmethod
    def ir_request_to_p(
        ir_request: IRRequest, **kwargs: Any
    ) -> Tuple[Dict[str, Any], List[str]]:
        """IRRequest → Argo Request

        将 IRRequest 转换为 Argo 请求参数。

        Args:
            ir_request: IR格式的完整请求
            **kwargs: 额外参数

        Returns:
            Tuple[Argo格式的请求参数, 警告信息列表]
        """
        warnings = []

        # 处理消息列表
        messages = ir_request.get("messages", [])
        argo_messages = []
        for message in messages:
            argo_message, msg_warnings = ArgoComplexOps.ir_message_to_p(
                message, **kwargs
            )
            argo_messages.append(argo_message)
            warnings.extend(msg_warnings)

        # 构建 Argo 请求
        argo_data = {"messages": argo_messages}

        # 添加工具相关字段（如果存在）
        if "tools" in ir_request and ir_request["tools"]:
            argo_tools = []
            for tool in ir_request["tools"]:
                argo_tool = ArgoAtomicOps.ir_tool_to_p(tool, **kwargs)
                argo_tools.append(argo_tool)
            argo_data["tools"] = argo_tools

        if "tool_choice" in ir_request and ir_request["tool_choice"]:
            argo_tool_choice = ArgoAtomicOps.ir_tool_choice_to_p(
                ir_request["tool_choice"], **kwargs
            )
            argo_data["tool_choice"] = argo_tool_choice

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
            if field in ir_request:
                argo_data[field] = ir_request[field]

        return argo_data, warnings

    @staticmethod
    def p_request_to_ir(provider_request: Dict[str, Any], **kwargs: Any) -> IRRequest:
        """Argo Request → IRRequest

        将 Argo 请求转换为 IRRequest。

        Args:
            provider_request: Argo格式的请求
            **kwargs: 额外参数

        Returns:
            IR格式的请求
        """
        if not isinstance(provider_request, dict):
            raise ValueError("Provider request must be a dictionary")

        # 处理消息列表
        ir_messages = []
        for message in provider_request.get("messages", []):
            ir_message = ArgoComplexOps.p_message_to_ir(message, **kwargs)
            ir_messages.append(ir_message)

        # 构建 IR 请求
        ir_data: IRRequest = {"messages": ir_messages}

        # 处理工具相关字段
        if "tools" in provider_request:
            ir_tools = []
            for tool in provider_request["tools"]:
                ir_tool = ArgoAtomicOps.p_tool_to_ir(tool, **kwargs)
                ir_tools.append(ir_tool)
            ir_data["tools"] = ir_tools

        if "tool_choice" in provider_request:
            ir_tool_choice = ArgoAtomicOps.p_tool_choice_to_ir(
                provider_request["tool_choice"], **kwargs
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
            if field in provider_request:
                ir_data[field] = provider_request[field]

        return ir_data

    # ==================== 响应级转换 Response level conversion ====================

    @staticmethod
    def p_response_to_ir(
        provider_response: Dict[str, Any], **kwargs: Any
    ) -> IRResponse:
        """Argo Response → IRResponse

        将 Argo 响应转换为 IRResponse。

        Argo 的响应格式可能是：
        1. {"response": "text content"}  - 纯文本响应
        2. {"response": {"content": "...", "tool_calls": [...]}}  - 带 tool calls 的响应

        Args:
            provider_response: Argo格式的响应
            **kwargs: 额外参数

        Returns:
            IR格式的响应
        """
        response_field = provider_response.get("response")

        # 构建 IR 格式的响应消息
        ir_response_message = {"role": "assistant", "content": []}

        # 解析响应内容
        if isinstance(response_field, dict):
            # 响应是字典格式，可能包含 content 和 tool_calls
            response_content = response_field.get("content")
            tool_calls = response_field.get("tool_calls")

            # 添加文本内容
            if response_content:
                ir_response_message["content"].append(
                    {"type": "text", "text": response_content}
                )

            # 添加工具调用
            if tool_calls:
                ir_tool_calls = []
                model_family = kwargs.get("model_family", "openai")
                for tool_call in tool_calls:
                    # 使用转换器将 Argo 格式的 tool_call 转换为 IR 格式
                    tool_call_kwargs = {**kwargs, "model_family": model_family}
                    ir_tool_call = ArgoAtomicOps.p_tool_call_to_ir(
                        tool_call, **tool_call_kwargs
                    )
                    ir_tool_calls.append(ir_tool_call)
                ir_response_message["tool_calls"] = ir_tool_calls

        elif isinstance(response_field, str):
            # 响应是纯文本
            ir_response_message["content"].append(
                {"type": "text", "text": response_field}
            )
        else:
            # 响应为 None 或其他类型，保持空内容
            pass

        # 构建完整的 IRResponse

        # 确定 finish_reason
        has_tool_calls = (
            "tool_calls" in ir_response_message and ir_response_message["tool_calls"]
        )
        finish_reason_value = "tool_calls" if has_tool_calls else "stop"

        ir_response: IRResponse = {
            "id": provider_response.get("id", str(uuid.uuid4().hex)),
            "object": "response",
            "created": provider_response.get("created", int(time.time())),
            "model": provider_response.get("model", "unknown"),
            "choices": [
                {
                    "index": 0,
                    "message": ir_response_message,
                    "finish_reason": {"reason": finish_reason_value},
                }
            ],
        }

        # 复制可选字段（如果存在）
        if "usage" in provider_response:
            ir_response["usage"] = provider_response["usage"]
        return ir_response

    @staticmethod
    def ir_response_to_p(ir_response: IRResponse, **kwargs: Any) -> Dict[str, Any]:
        """IRResponse → Argo Response

        将 IRResponse 转换为 Argo 响应。

        Args:
            ir_response: IR格式的响应
            **kwargs: 额外参数

        Returns:
            Argo格式的响应
        """
        # 提取第一个 choice 的消息
        if not ir_response.get("choices"):
            return {"response": None}

        first_choice = ir_response["choices"][0]
        message = first_choice.get("message", {})

        # 提取内容
        content_parts = message.get("content", [])
        text_content = ""
        if content_parts:
            # 合并所有文本部分
            text_parts = [
                part.get("text", "")
                for part in content_parts
                if part.get("type") == "text"
            ]
            text_content = " ".join(text_parts)

        # 提取工具调用
        tool_calls = message.get("tool_calls")

        # 构建响应
        if tool_calls:
            # 有工具调用，返回结构化响应
            argo_tool_calls = []
            for tool_call in tool_calls:
                argo_tool_call = ArgoAtomicOps.ir_tool_call_to_p(tool_call, **kwargs)
                argo_tool_calls.append(argo_tool_call)

            response_data = {
                "content": text_content if text_content else None,
                "tool_calls": argo_tool_calls,
            }
        else:
            # 纯文本响应
            response_data = text_content

        argo_response = {"response": response_data}

        # 复制其他字段（如果存在）
        for field in ["id", "object", "created", "model", "usage"]:
            if field in ir_response:
                argo_response[field] = ir_response[field]

        return argo_response

    # ==================== 辅助方法 Helper methods ====================

    @staticmethod
    def p_user_message_to_ir(content: Any, **kwargs: Any) -> Dict[str, Any]:
        """处理 Argo user 消息转换为 IR

        Args:
            content: Argo格式的用户消息内容
            **kwargs: 额外参数

        Returns:
            IR格式的用户消息
        """
        ir_message = {"role": "user", "content": []}

        if isinstance(content, str):
            ir_message["content"] = [ArgoAtomicOps.p_text_to_ir(content, **kwargs)]
        elif isinstance(content, list):
            ir_content = []
            for part in content:
                ir_parts = ArgoAtomicOps.p_content_part_to_ir(part, **kwargs)
                ir_content.extend(ir_parts)
            ir_message["content"] = ir_content
        else:
            ir_message["content"] = [ArgoAtomicOps.p_text_to_ir(str(content), **kwargs)]

        return ir_message

    @staticmethod
    def p_assistant_message_to_ir(
        provider_message: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        """处理 Argo assistant 消息转换为 IR

        Args:
            provider_message: Argo格式的助手消息
            **kwargs: 额外参数

        Returns:
            IR格式的助手消息
        """
        # 使用通用的消息转换方法
        return ArgoComplexOps.p_message_to_ir(provider_message, **kwargs)
