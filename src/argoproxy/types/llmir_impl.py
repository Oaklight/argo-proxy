"""
LLMIR - Base Converter

定义转换器的基础接口（抽象基类，分层模板）
Defines the basic interface for converters (abstract base class, layered template)
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

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
        pass

    def from_provider(self, provider_data: Any) -> Union[IRInput, Dict[str, Any]]:
        """将provider特定格式转换为IR格式
        Convert provider-specific format to IR format

        Args:
            provider_data: provider特定格式的数据 / Provider-specific format data

        Returns:
            IR格式的数据（消息列表或完整响应） / IR format data (message list or full response)
        """
        pass

    # ==================== 分层抽象方法 Layered abstract methods ====================

    def _ir_message_to_p(self, message: Dict[str, Any], ir_input: IRInput) -> Any:
        """IR Message → Provider Message / IR消息转换为Provider消息"""
        pass

    def _ir_content_part_to_p(
        self, content_part: Dict[str, Any], ir_input: IRInput
    ) -> Any:
        """IR ContentPart → Provider Content/Part / IR内容部分转换为Provider内容/Part"""
        pass

    def _p_message_to_ir(self, provider_message: Any) -> Dict[str, Any]:
        """Provider Message → IR Message / Provider消息转换为IR消息"""
        pass

    def _p_content_part_to_ir(self, provider_part: Any) -> List[Dict[str, Any]]:
        """Provider Content/Part → IR ContentPart(s) / Provider内容/Part转换为IR内容部分"""
        pass

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
        """IR ToolCallPart → Provider Tool Call / IR工具调用部分转换为Provider工具调用

        注意：此方法需要 model_family 参数，请使用 ir_tool_call_to_argo() 方法
        """
        raise NotImplementedError(
            "Use ir_tool_call_to_argo(tool_call_part, model_family) instead. "
            "This method requires model_family parameter to determine the correct format."
        )

    def _p_tool_call_to_ir(self, provider_tool_call: Any) -> ToolCallPart:
        """Provider Tool Call → IR ToolCallPart / Provider工具调用转换为IR工具调用部分

        注意：此方法需要 model_family 参数，请使用 argo_tool_call_to_ir() 方法
        """
        raise NotImplementedError(
            "Use argo_tool_call_to_ir(provider_tool_call, model_family) instead. "
            "This method requires model_family parameter to determine the correct format."
        )

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
        """IR ToolDefinition → Provider Tool Definition / IR工具定义转换为Provider工具定义

        注意：此方法需要 model_family 参数，请使用 ir_tool_to_argo() 方法
        """
        raise NotImplementedError(
            "Use ir_tool_to_argo(tool, model_family) instead. "
            "This method requires model_family parameter to determine the correct format."
        )

    def _p_tool_to_ir(self, provider_tool: Any) -> ToolDefinition:
        """Provider Tool Definition → IR ToolDefinition / Provider工具定义转换为IR工具定义

        注意：此方法需要 model_family 参数，请使用 argo_tool_to_ir() 方法
        """
        raise NotImplementedError(
            "Use argo_tool_to_ir(provider_tool, model_family) instead. "
            "This method requires model_family parameter to determine the correct format."
        )

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
        """IR ToolChoice → Provider Tool Choice Config / IR工具选择转换为Provider工具选择配置

        注意：此方法需要 model_family 参数，请使用 ir_tool_choice_to_argo() 方法
        """
        raise NotImplementedError(
            "Use ir_tool_choice_to_argo(tool_choice, model_family) instead. "
            "This method requires model_family parameter to determine the correct format."
        )

    def _p_tool_choice_to_ir(self, provider_tool_choice: Any) -> ToolChoice:
        """Provider Tool Choice Config → IR ToolChoice / Provider工具选择配置转换为IR工具选择

        注意：此方法需要 model_family 参数，请使用 argo_tool_choice_to_ir() 方法
        """
        raise NotImplementedError(
            "Use argo_tool_choice_to_ir(provider_tool_choice, model_family) instead. "
            "This method requires model_family parameter to determine the correct format."
        )

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
