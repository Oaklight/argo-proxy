"""
LLMIR - Processing Functions
LLMIR 业务逻辑处理

包含使用 LLMIR 处理聊天请求的业务逻辑函数。
"""

import json
import time
import uuid
from http import HTTPStatus
from typing import Any, Dict, Union

import aiohttp
from aiohttp import web
from llmir import OpenAIChatConverter
from loguru import logger

from ..config import ArgoConfig
from ..models import ModelRegistry
from ..types import CompletionUsage
from ..utils.image_processing import process_chat_images, sanitize_data_for_logging
from ..utils.misc import apply_username_passthrough, make_bar
from ..utils.tokens import calculate_prompt_tokens_async, count_tokens_async
from .converter import ArgoConverter


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
        openai_converter = OpenAIChatConverter()

        try:
            logger.info("[LLMIR DEBUG] Starting from_provider conversion")
            logger.info(f"[LLMIR DEBUG] Input data type: {type(data)}")
            logger.info(
                f"[LLMIR DEBUG] Input data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
            )

            # 将请求数据转换为 IR 格式（自动处理模型家族检测）
            ir_request = openai_converter.from_provider(data)

            logger.info("[LLMIR DEBUG] from_provider conversion completed")
            logger.info(f"[LLMIR DEBUG] IR request type: {type(ir_request)}")
            logger.info(
                f"[LLMIR DEBUG] IR request keys: {list(ir_request.keys()) if isinstance(ir_request, dict) else 'N/A'}"
            )

            logger.info("[LLMIR DEBUG] Starting to_provider conversion")
            # 将 IR 格式转换回 Argo 格式（应用标准化处理和模型家族转换）
            argo_data, warnings = converter.to_provider(ir_request)

            # 手动添加 user 字段，因为 OpenAIChatConverter 可能不会保留它
            if "user" in data:
                argo_data["user"] = data["user"]

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
    config: ArgoConfig,
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

            # 使用 ArgoConverter 将 Argo 响应转换为 IR 格式
            argo_converter = ArgoConverter()

            # 确定模型家族
            model_name = data.get("model", "")
            from ..utils.models import determine_model_family

            model_family = (
                determine_model_family(model_name) if model_name else "openai"
            )
            if model_family == "unknown":
                model_family = "openai"

            # Argo Response → IR Response
            ir_response = argo_converter.from_provider(
                response_data, model_family=model_family
            )

            # 检查是否有有效的响应
            if not ir_response.get("choices"):
                return web.json_response(
                    {
                        "object": "error",
                        "message": "Upstream model returned no response. Please try different request parameters.",
                        "type": "upstream_no_response",
                    },
                    status=502,
                )

            # 提取第一个 choice 的消息用于 token 计算
            first_choice = ir_response["choices"][0]
            ir_message = first_choice.get("message", {})

            # 提取文本内容用于 token 计算
            content_parts = ir_message.get("content", [])
            text_parts = [
                part.get("text", "")
                for part in content_parts
                if part.get("type") == "text"
            ]
            response_content = " ".join(text_parts) if text_parts else ""

            # 计算 tokens
            prompt_tokens = await calculate_prompt_tokens_async(data, data["model"])
            completion_tokens = (
                await count_tokens_async(response_content, data["model"])
                if response_content
                else 0
            )
            total_tokens = prompt_tokens + completion_tokens

            # 使用 OpenAIChatConverter 将 IR Response 转换为 OpenAI 格式
            openai_converter = OpenAIChatConverter()
            openai_response_data, _ = openai_converter.to_provider(ir_response)

            # 创建 CompletionUsage 对象并添加 usage 信息到响应中
            usage = CompletionUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
            openai_response_data["usage"] = usage.model_dump()

            # 确保有 id, object, created, model 字段
            if "id" not in openai_response_data:
                openai_response_data["id"] = str(uuid.uuid4().hex)
            if "object" not in openai_response_data:
                openai_response_data["object"] = "chat.completion"
            if "created" not in openai_response_data:
                openai_response_data["created"] = int(time.time())
            if "model" not in openai_response_data:
                openai_response_data["model"] = data.get("model", "unknown")

            openai_response = openai_response_data

            return web.json_response(
                openai_response,
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
