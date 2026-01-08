#!/usr/bin/env python3
"""
测试 LLMIR 模式的基本功能
Test basic functionality of LLMIR mode
"""

import json

from src.argoproxy.types.llmir_impl import ArgoConverter


def test_basic_conversion():
    """测试基本的消息转换功能"""
    print("=== 测试基本消息转换 ===")

    # 创建转换器
    converter = ArgoConverter()

    # 测试数据：简单的聊天消息
    test_data = {
        "model": "argo:gpt-4o",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"},
            {"role": "assistant", "content": "I'm doing well, thank you!"},
        ],
        "temperature": 0.7,
        "max_tokens": 100,
    }

    print("原始数据:")
    print(json.dumps(test_data, indent=2, ensure_ascii=False))

    try:
        # 测试 from_provider
        print("\n--- 测试 from_provider ---")
        ir_data = converter.from_provider(test_data)
        print("IR 格式:")
        print(json.dumps(ir_data, indent=2, ensure_ascii=False))

        # 测试 to_provider
        print("\n--- 测试 to_provider ---")
        argo_data, warnings = converter.to_provider(ir_data)
        print("转换后的 Argo 格式:")
        print(json.dumps(argo_data, indent=2, ensure_ascii=False))

        if warnings:
            print("警告信息:")
            for warning in warnings:
                print(f"  - {warning}")

        print("\n✅ 基本转换测试通过")
        return True

    except Exception as e:
        print(f"\n❌ 基本转换测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_image_conversion():
    """测试图像消息转换功能"""
    print("\n=== 测试图像消息转换 ===")

    converter = ArgoConverter()

    # 测试数据：包含图像的消息
    test_data = {
        "model": "argo:gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=",
                            "detail": "auto",
                        },
                    },
                ],
            }
        ],
    }

    print("包含图像的数据:")
    print(json.dumps(test_data, indent=2, ensure_ascii=False))

    try:
        # 测试转换
        ir_data = converter.from_provider(test_data)
        print("\nIR 格式 (图像部分):")
        for msg in ir_data["messages"]:
            if "content" in msg:
                for part in msg["content"]:
                    if part.get("type") == "image":
                        print(f"  图像类型: {part.get('type')}")
                        print(f"  详细级别: {part.get('detail')}")
                        if "image_data" in part:
                            print(f"  数据类型: {part['image_data'].get('media_type')}")
                            print(
                                f"  数据长度: {len(part['image_data'].get('data', ''))}"
                            )

        argo_data, warnings = converter.to_provider(ir_data)
        print("\n✅ 图像转换测试通过")
        return True

    except Exception as e:
        print(f"\n❌ 图像转换测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_tool_conversion():
    """测试工具调用转换功能"""
    print("\n=== 测试工具调用转换 ===")

    converter = ArgoConverter()

    # 测试数据：包含工具的消息
    test_data = {
        "model": "argo:gpt-4o",
        "messages": [{"role": "user", "content": "What's the weather like?"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            }
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }

    print("包含工具的数据:")
    print(json.dumps(test_data, indent=2, ensure_ascii=False))

    try:
        # 测试转换
        ir_data = converter.from_provider(test_data)
        print("\nIR 格式 (工具部分):")
        if "tools" in ir_data:
            print(f"  工具数量: {len(ir_data['tools'])}")
            for tool in ir_data["tools"]:
                print(f"  工具名称: {tool.get('function', {}).get('name')}")

        argo_data, warnings = converter.to_provider(ir_data)
        print("\n✅ 工具转换测试通过")
        return True

    except Exception as e:
        print(f"\n❌ 工具转换测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("🧠 LLMIR 模式功能测试")
    print("=" * 50)

    tests = [test_basic_conversion, test_image_conversion, test_tool_conversion]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1

    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！LLMIR 模式基本功能正常")
    else:
        print("⚠️  部分测试失败，需要进一步调试")


if __name__ == "__main__":
    main()
