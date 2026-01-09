"""
LLMIR - Argo Converter
Argo 主转换器（轻量化架构）

采用组合优于继承的设计模式，通过类属性指定 ops 类。
"""

from typing import Any, Dict, List, Tuple, Union

from llmir.converters.anthropic import AnthropicConverter
from llmir.converters.base import BaseConverter
from llmir.converters.google import GoogleConverter
from llmir.converters.openai_chat import OpenAIChatConverter
from llmir.types.ir import IRInput
from llmir.types.ir_request import IRRequest
from llmir.types.ir_response import IRResponse
from loguru import logger

from ..utils.models import determine_model_family
from .atomic_ops import ArgoAtomicOps
from .complex_ops import ArgoComplexOps


class ArgoConverter(BaseConverter):
    """Argo 转换器（轻量化架构）

    使用组合模式而非继承：
    - 通过类属性指定使用的 atomic_ops 和 complex_ops 类
    - 直接调用 ops 类的静态方法，无需实现大量委托方法
    - 预实例化 llmir 转换器以提高性能
    """

    # 指定使用的 ops 类
    atomic_ops_class = ArgoAtomicOps
    complex_ops_class = ArgoComplexOps

    def __init__(self):
        """初始化 ArgoConverter，预先实例化 LLMIR 转换器组件"""
        super().__init__()

        # 预先实例化 LLMIR 转换器，避免每次调用时重复实例化
        self._openai_converter = OpenAIChatConverter()
        self._anthropic_converter = AnthropicConverter()
        self._google_converter = GoogleConverter()

    def to_provider(
        self,
        ir_data: Union[IRInput, IRRequest, IRResponse],
        **kwargs: Any,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """将 IR 格式转换为 Argo 格式

        Args:
            ir_data: IR格式的数据（请求、响应或消息列表）
            **kwargs: 额外参数

        Returns:
            Tuple[转换后的数据, 警告信息列表]
        """
        # 添加转换器实例到 kwargs，供 ops 类使用
        kwargs["_openai_converter"] = self._openai_converter
        kwargs["_anthropic_converter"] = self._anthropic_converter
        kwargs["_google_converter"] = self._google_converter

        # 处理 IRRequest 格式
        if isinstance(ir_data, dict) and "messages" in ir_data:
            # 这是一个 IRRequest
            return self.complex_ops_class.ir_request_to_p(ir_data, **kwargs)
        elif isinstance(ir_data, dict) and "choices" in ir_data:
            # 这是一个 IRResponse
            return self.complex_ops_class.ir_response_to_p(ir_data, **kwargs), []
        else:
            # 这是一个 IRInput (消息列表)
            # 将其包装为 IRRequest 格式
            ir_request: IRRequest = {"messages": ir_data}
            return self.complex_ops_class.ir_request_to_p(ir_request, **kwargs)

    def from_provider(
        self,
        provider_data: Any,
        **kwargs: Any,
    ) -> Union[IRInput, IRRequest, IRResponse]:
        """将 Argo 格式转换为 IR 格式

        Args:
            provider_data: Argo格式的数据（请求、响应或消息）
            **kwargs: 额外参数

        Returns:
            IR格式的数据（IRRequest、IRResponse或IRInput）
        """
        logger.info(
            f"[LLMIR DEBUG] from_provider called with data type: {type(provider_data)}"
        )

        # 添加转换器实例到 kwargs
        kwargs["_openai_converter"] = self._openai_converter
        kwargs["_anthropic_converter"] = self._anthropic_converter
        kwargs["_google_converter"] = self._google_converter

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

        # 添加 model_family 到 kwargs
        kwargs["model_family"] = model_family

        # 使用 complex_ops 进行转换
        logger.info(
            f"[LLMIR DEBUG] Processing provider_data type: {type(provider_data)}"
        )
        if isinstance(provider_data, dict):
            if "messages" in provider_data:
                logger.info(
                    f"[LLMIR DEBUG] Processing {len(provider_data['messages'])} messages"
                )
                # 这是一个完整的请求
                return self.complex_ops_class.p_request_to_ir(provider_data, **kwargs)
            elif "response" in provider_data:
                # 这是一个响应
                return self.complex_ops_class.p_response_to_ir(provider_data, **kwargs)
            else:
                # 这可能是一个单独的消息
                return self.complex_ops_class.p_message_to_ir(provider_data, **kwargs)
        elif isinstance(provider_data, list):
            # 这是一个消息列表
            ir_messages = []
            for message in provider_data:
                ir_message = self.complex_ops_class.p_message_to_ir(message, **kwargs)
                ir_messages.append(ir_message)
            return ir_messages
        else:
            raise ValueError(f"Unsupported provider data format: {type(provider_data)}")

    def parse_argo_response(
        self, response_data: Dict[str, Any], **kwargs: Any
    ) -> Dict[str, Any]:
        """解析 Argo 上游响应，转换为 IR 格式

        Argo 的响应格式可能是：
        1. {"response": "text content"}  - 纯文本响应
        2. {"response": {"content": "...", "tool_calls": [...]}}  - 带 tool calls 的响应

        Args:
            response_data: Argo 上游返回的响应数据
            **kwargs: 额外参数，包括 model_family 等

        Returns:
            IR格式的响应消息
        """
        # 添加转换器实例到 kwargs
        kwargs["_openai_converter"] = self._openai_converter
        kwargs["_anthropic_converter"] = self._anthropic_converter
        kwargs["_google_converter"] = self._google_converter

        response_field = response_data.get("response")

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
                    # 使用 atomic_ops 将 Argo 格式的 tool_call 转换为 IR 格式
                    tool_call_kwargs = {**kwargs, "model_family": model_family}
                    ir_tool_call = self.atomic_ops_class.p_tool_call_to_ir(
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

        return ir_response_message
