"""
LLMIR - Argo Atomic Operations
Argo 原子级转换操作

实现基础内容类型的双向转换，包括：
- 文本转换 (TextPart ↔ Argo text)
- 图像转换 (ImagePart ↔ Argo image)
- 文件转换 (FilePart ↔ Argo file)
- 工具调用转换 (ToolCallPart ↔ Argo tool call)
- 工具结果转换 (ToolResultPart ↔ Argo tool result)
- 工具定义转换 (ToolDefinition ↔ Argo tool definition)
- 工具选择转换 (ToolChoice ↔ Argo tool choice)
"""

import re
from typing import Any, List

from llmir.converters.base import BaseAtomicOps
from llmir.types.ir import (
    FilePart,
    ImagePart,
    TextPart,
    ToolCallPart,
    ToolChoice,
    ToolDefinition,
    ToolResultPart,
)


class ArgoAtomicOps(BaseAtomicOps):
    """Argo 原子级转换操作

    所有方法都是静态方法，专注于基础类型的双向转换。
    对于模型家族特定的转换（如工具调用），委托给 llmir 的专用转换器。
    """

    # ==================== 文本转换 Text conversion ====================

    @staticmethod
    def ir_text_to_p(text_part: TextPart, **kwargs: Any) -> Any:
        """IR TextPart → Argo Text Content

        Args:
            text_part: IR格式的文本部分
            **kwargs: 额外参数

        Returns:
            Argo格式的文本内容字典
        """
        return {"type": "text", "text": text_part["text"]}

    @staticmethod
    def p_text_to_ir(provider_text: Any, **kwargs: Any) -> TextPart:
        """Argo Text Content → IR TextPart

        Argo 支持多种文本格式：
        1. 简单字符串：直接文本内容
        2. OpenAI 格式：{"type": "text", "text": "..."}
        3. 其他格式的文本内容

        Args:
            provider_text: Argo格式的文本内容
            **kwargs: 额外参数

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

    # ==================== 图像转换 Image conversion ====================

    @staticmethod
    def ir_image_to_p(image_part: ImagePart, **kwargs: Any) -> Any:
        """IR ImagePart → Argo Image Content

        Argo 使用 OpenAI 兼容的图像格式：
        {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}

        注意：Argo 只接受 base64 编码的图像（data URL）。
        如果 image_url 是 HTTP/HTTPS URL，调用者应该先使用
        utils.image_processing.process_chat_images() 将其转换为 base64。

        Args:
            image_part: IR格式的图像部分，可以包含：
                - image_url: data URL（data:image/png;base64,...）
                - image_data: base64编码的图像数据
                - detail: 图像细节级别（auto/low/high）
            **kwargs: 额外参数

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
                    f"Argo does not support HTTP/HTTPS image URLs. "
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

        # 返回 Argo/OpenAI 兼容格式
        return {"type": "image_url", "image_url": {"url": final_url, "detail": detail}}

    @staticmethod
    def p_image_to_ir(provider_image: Any, **kwargs: Any) -> ImagePart:
        """Argo Image Content → IR ImagePart

        Argo 使用 OpenAI 兼容格式，需要解析：
        {"type": "image_url", "image_url": {"url": "...", "detail": "..."}}

        Args:
            provider_image: Argo格式的图像内容字典
            **kwargs: 额外参数

        Returns:
            IR格式的ImagePart
        """
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

    # ==================== 文件转换 File conversion ====================

    @staticmethod
    def ir_file_to_p(file_part: FilePart, **kwargs: Any) -> Any:
        """IR FilePart → Argo File Content

        注意：文件处理功能尚未实现，上游 LLMIR 转换器也未提供此功能
        """
        raise NotImplementedError(
            "File handling is not yet implemented. "
            "The upstream LLMIR converters do not provide file conversion functionality."
        )

    @staticmethod
    def p_file_to_ir(provider_file: Any, **kwargs: Any) -> FilePart:
        """Argo File Content → IR FilePart

        注意：文件处理功能尚未实现，上游 LLMIR 转换器也未提供此功能
        """
        raise NotImplementedError(
            "File handling is not yet implemented. "
            "The upstream LLMIR converters do not provide file conversion functionality."
        )

    # ==================== 工具调用转换 Tool call conversion ====================

    @staticmethod
    def ir_tool_call_to_p(tool_call_part: ToolCallPart, **kwargs: Any) -> Any:
        """IR ToolCallPart → Argo Tool Call

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器。
        需要通过 kwargs 传递预实例化的转换器。

        Args:
            tool_call_part: IR格式的工具调用部分
            **kwargs: 额外参数，必须包含：
                - model_family: 模型家族（openai/anthropic/google）
                - _openai_converter: OpenAI转换器实例
                - _anthropic_converter: Anthropic转换器实例
                - _google_converter: Google转换器实例

        Returns:
            Argo格式的工具调用
        """
        model_family = kwargs.get("model_family", "openai")

        if model_family == "anthropic":
            converter = kwargs.get("_anthropic_converter")
            return converter._ir_tool_call_to_p(tool_call_part, **kwargs)
        elif model_family == "google":
            converter = kwargs.get("_google_converter")
            return converter._ir_tool_call_to_p(tool_call_part, **kwargs)
        else:
            converter = kwargs.get("_openai_converter")
            return converter.atomic_ops_class.ir_tool_call_to_p(
                tool_call_part, **kwargs
            )

    @staticmethod
    def p_tool_call_to_ir(provider_tool_call: Any, **kwargs: Any) -> ToolCallPart:
        """Argo Tool Call → IR ToolCallPart

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器。

        Args:
            provider_tool_call: Argo格式的工具调用
            **kwargs: 额外参数，必须包含 model_family 和转换器实例

        Returns:
            IR格式的ToolCallPart
        """
        model_family = kwargs.get("model_family", "openai")

        if model_family == "anthropic":
            converter = kwargs.get("_anthropic_converter")
            return converter._p_tool_call_to_ir(provider_tool_call, **kwargs)
        elif model_family == "google":
            converter = kwargs.get("_google_converter")
            return converter._p_tool_call_to_ir(provider_tool_call, **kwargs)
        else:
            converter = kwargs.get("_openai_converter")
            return converter.atomic_ops_class.p_tool_call_to_ir(
                provider_tool_call, **kwargs
            )

    # ==================== 工具结果转换 Tool result conversion ====================

    @staticmethod
    def ir_tool_result_to_p(tool_result_part: ToolResultPart, **kwargs: Any) -> Any:
        """IR ToolResultPart → Argo Tool Result

        使用 IR 作为中间格式的工具结果，所有模型家族都支持：
        {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            tool_result_part: IR格式的工具结果部分
            **kwargs: 额外参数

        Returns:
            Argo格式的工具结果消息
        """
        tool_call_id = tool_result_part.get("tool_call_id", "")
        content = tool_result_part.get("content", "")

        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}

    @staticmethod
    def p_tool_result_to_ir(provider_tool_result: Any, **kwargs: Any) -> ToolResultPart:
        """Argo Tool Result → IR ToolResultPart

        使用 IR 作为中间格式的工具结果：
        {"role": "tool", "tool_call_id": "...", "content": "..."}

        Args:
            provider_tool_result: Argo格式的工具结果消息
            **kwargs: 额外参数

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

    # ==================== 工具定义转换 Tool definition conversion ====================

    @staticmethod
    def ir_tool_to_p(tool: ToolDefinition, **kwargs: Any) -> Any:
        """IR ToolDefinition → Argo Tool Definition

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器。

        Args:
            tool: IR格式的工具定义
            **kwargs: 额外参数，必须包含 model_family 和转换器实例

        Returns:
            Argo格式的工具定义
        """
        model_family = kwargs.get("model_family", "openai")

        if model_family == "anthropic":
            converter = kwargs.get("_anthropic_converter")
            return converter._ir_tool_to_p(tool, **kwargs)
        elif model_family == "google":
            converter = kwargs.get("_google_converter")
            return converter._ir_tool_to_p(tool, **kwargs)
        else:
            converter = kwargs.get("_openai_converter")
            return converter.atomic_ops_class.ir_tool_to_p(tool, **kwargs)

    @staticmethod
    def p_tool_to_ir(provider_tool: Any, **kwargs: Any) -> ToolDefinition:
        """Argo Tool Definition → IR ToolDefinition

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器。

        Args:
            provider_tool: Argo格式的工具定义
            **kwargs: 额外参数，必须包含 model_family 和转换器实例

        Returns:
            IR格式的ToolDefinition
        """
        model_family = kwargs.get("model_family", "openai")

        if model_family == "anthropic":
            converter = kwargs.get("_anthropic_converter")
            return converter._p_tool_to_ir(provider_tool, **kwargs)

        elif model_family == "google":
            converter = kwargs.get("_google_converter")
            return converter._p_tool_to_ir(provider_tool, **kwargs)
        else:
            converter = kwargs.get("_openai_converter")
            return converter.atomic_ops_class.p_tool_to_ir(provider_tool, **kwargs)

    # ==================== 工具选择转换 Tool choice conversion ====================

    @staticmethod
    def ir_tool_choice_to_p(tool_choice: ToolChoice, **kwargs: Any) -> Any:
        """IR ToolChoice → Argo Tool Choice Config

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器。

        Args:
            tool_choice: IR格式的工具选择
            **kwargs: 额外参数，必须包含 model_family 和转换器实例

        Returns:
            Argo格式的工具选择配置
        """
        model_family = kwargs.get("model_family", "openai")

        if model_family == "anthropic":
            converter = kwargs.get("_anthropic_converter")
            return converter._ir_tool_choice_to_p(tool_choice, **kwargs)

        elif model_family == "google":
            converter = kwargs.get("_google_converter")
            return converter._ir_tool_choice_to_p(tool_choice, **kwargs)
        else:
            converter = kwargs.get("_openai_converter")
            return converter.atomic_ops_class.ir_tool_choice_to_p(tool_choice, **kwargs)

    @staticmethod
    def p_tool_choice_to_ir(provider_tool_choice: Any, **kwargs: Any) -> ToolChoice:
        """Argo Tool Choice Config → IR ToolChoice

        使用 IR 作为中间格式，根据 model_family 选择合适的转换器。

        Args:
            provider_tool_choice: Argo格式的工具选择配置
            **kwargs: 额外参数，必须包含 model_family 和转换器实例

        Returns:
            IR格式的ToolChoice
        """
        model_family = kwargs.get("model_family", "openai")

        if model_family == "anthropic":
            converter = kwargs.get("_anthropic_converter")
            return converter._p_tool_choice_to_ir(provider_tool_choice, **kwargs)
        elif model_family == "google":
            converter = kwargs.get("_google_converter")
            return converter._p_tool_choice_to_ir(provider_tool_choice, **kwargs)
        else:
            converter = kwargs.get("_openai_converter")
            return converter.atomic_ops_class.p_tool_choice_to_ir(
                provider_tool_choice, **kwargs
            )

    # ==================== 内容部分转换 Content part conversion ====================

    @staticmethod
    def p_content_part_to_ir(provider_part: Any, **kwargs: Any) -> List[Any]:
        """Argo Content/Part → IR ContentPart(s)

        将 Argo 内容部分转换为 IR 内容部分列表。

        Args:
            provider_part: Argo格式的内容部分
            **kwargs: 额外参数

        Returns:
            IR格式的内容部分列表（可能返回多个部分）
        """
        if isinstance(provider_part, str):
            # 简单字符串
            return [ArgoAtomicOps.p_text_to_ir(provider_part, **kwargs)]
        elif isinstance(provider_part, dict):
            part_type = provider_part.get("type")

            if part_type == "text":
                return [ArgoAtomicOps.p_text_to_ir(provider_part, **kwargs)]
            elif part_type == "image_url":
                return [ArgoAtomicOps.p_image_to_ir(provider_part, **kwargs)]
            elif part_type == "tool_call":
                # 从 kwargs 中获取 model_family，如果没有则默认为 openai
                model_family = kwargs.get("model_family", "openai")
                tool_call_kwargs = {**kwargs, "model_family": model_family}
                return [
                    ArgoAtomicOps.p_tool_call_to_ir(provider_part, **tool_call_kwargs)
                ]
            elif part_type == "tool_result":
                return [ArgoAtomicOps.p_tool_result_to_ir(provider_part, **kwargs)]
            else:
                # 未知类型，尝试作为文本处理
                return [ArgoAtomicOps.p_text_to_ir(str(provider_part), **kwargs)]
        else:
            # 其他类型，转换为文本
            return [ArgoAtomicOps.p_text_to_ir(str(provider_part), **kwargs)]
