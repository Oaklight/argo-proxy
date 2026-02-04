"""
Test script to verify if the leaked tool call detection can be fooled by examples.

This script tests whether the current implementation incorrectly treats
tool call examples/documentation as real tool calls.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from argoproxy.tool_calls.output_handle import ToolInterceptor


def test_case_1_example_in_chinese():
    """Test case: User asks about Claude tool call format in Chinese"""
    print("\n" + "=" * 80)
    print("测试案例 1: 用户询问 Claude tool call 格式（中文）")
    print("=" * 80)
    
    # Simulate a response where the model is explaining the format
    response_data = {
        "content": """Claude 的 tool call 格式如下：

{'id': 'toolu_01A1B2C3D4E5F6', 'name': 'get_weather', 'input': {'city': 'Beijing'}, 'type': 'tool_use'}

这个格式包含了工具调用的所有必要信息。""",
        "tool_calls": []
    }
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    print(f"\n原始内容长度: {len(response_data['content'])}")
    print(f"处理后内容长度: {len(text_content)}")
    print(f"检测到的 tool calls: {tool_calls}")
    print(f"\n处理后的文本内容:\n{text_content}")
    
    if tool_calls:
        print("\n❌ 错误：将示例误判为真实 tool call！")
        return False
    else:
        print("\n✅ 正确：没有将示例误判为 tool call")
        return True


def test_case_2_example_in_english():
    """Test case: User asks about Claude tool call format in English"""
    print("\n" + "=" * 80)
    print("测试案例 2: 用户询问 Claude tool call 格式（英文）")
    print("=" * 80)
    
    response_data = {
        "content": """The Claude tool call format looks like this:

{'id': 'toolu_01XYZ123', 'name': 'search', 'input': {'query': 'test'}, 'type': 'tool_use'}

This is an example of how tool calls are structured.""",
        "tool_calls": []
    }
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    print(f"\n原始内容长度: {len(response_data['content'])}")
    print(f"处理后内容长度: {len(text_content)}")
    print(f"检测到的 tool calls: {tool_calls}")
    print(f"\n处理后的文本内容:\n{text_content}")
    
    if tool_calls:
        print("\n❌ 错误：将示例误判为真实 tool call！")
        return False
    else:
        print("\n✅ 正确：没有将示例误判为 tool call")
        return True


def test_case_3_real_leaked_tool_call():
    """Test case: Real leaked tool call (should be detected)"""
    print("\n" + "=" * 80)
    print("测试案例 3: 真实的 leaked tool call（应该被检测到）")
    print("=" * 80)
    
    # Simulate a real leaked tool call without example context
    response_data = {
        "content": "{'id': 'toolu_01REAL123', 'name': 'get_stock_price', 'input': {'ticker': 'AAPL'}, 'type': 'tool_use'}",
        "tool_calls": []
    }
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    print(f"\n原始内容长度: {len(response_data['content'])}")
    print(f"处理后内容长度: {len(text_content)}")
    print(f"检测到的 tool calls: {tool_calls}")
    print(f"\n处理后的文本内容:\n{text_content}")
    
    if tool_calls:
        print("\n✅ 正确：成功检测到真实的 leaked tool call")
        return True
    else:
        print("\n❌ 错误：未能检测到真实的 tool call！")
        return False


def test_case_4_example_with_explanation():
    """Test case: Example with detailed explanation"""
    print("\n" + "=" * 80)
    print("测试案例 4: 带详细解释的示例")
    print("=" * 80)
    
    response_data = {
        "content": """当你需要调用工具时，返回的格式应该类似这样：

{'id': 'toolu_01ABC', 'name': 'calculator', 'input': {'expression': '2+2'}, 'type': 'tool_use'}

其中 id 是唯一标识符，name 是工具名称。""",
        "tool_calls": []
    }
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    print(f"\n原始内容长度: {len(response_data['content'])}")
    print(f"处理后内容长度: {len(text_content)}")
    print(f"检测到的 tool calls: {tool_calls}")
    print(f"\n处理后的文本内容:\n{text_content}")
    
    if tool_calls:
        print("\n❌ 错误：将示例误判为真实 tool call！")
        return False
    else:
        print("\n✅ 正确：没有将示例误判为 tool call")
        return True


def test_case_5_in_code_block():
    """Test case: Tool call in markdown code block"""
    print("\n" + "=" * 80)
    print("测试案例 5: Markdown 代码块中的 tool call")
    print("=" * 80)
    
    response_data = {
        "content": """Here's an example in a code block:

```
{'id': 'toolu_01CODE', 'name': 'test', 'input': {}, 'type': 'tool_use'}
```

This is just for demonstration.""",
        "tool_calls": []
    }
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    print(f"\n原始内容长度: {len(response_data['content'])}")
    print(f"处理后内容长度: {len(text_content)}")
    print(f"检测到的 tool calls: {tool_calls}")
    print(f"\n处理后的文本内容:\n{text_content}")
    
    if tool_calls:
        print("\n❌ 错误：将代码块中的示例误判为真实 tool call！")
        return False
    else:
        print("\n✅ 正确：没有将代码块中的示例误判为 tool call")
        return True


def test_case_6_incomplete_structure():
    """Test case: Incomplete tool call structure (missing required fields)"""
    print("\n" + "=" * 80)
    print("测试案例 6: 不完整的结构（缺少必需字段）")
    print("=" * 80)
    
    response_data = {
        "content": "工具调用的 ID 格式是：{'id': 'toolu_01INCOMPLETE'}",
        "tool_calls": []
    }
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    print(f"\n原始内容长度: {len(response_data['content'])}")
    print(f"处理后内容长度: {len(text_content)}")
    print(f"检测到的 tool calls: {tool_calls}")
    print(f"\n处理后的文本内容:\n{text_content}")
    
    if tool_calls:
        print("\n❌ 错误：将不完整的结构误判为真实 tool call！")
        return False
    else:
        print("\n✅ 正确：没有将不完整的结构误判为 tool call")
        return True


def main():
    """Run all test cases"""
    print("\n" + "=" * 80)
    print("测试 Leaked Tool Call 检测的误判问题")
    print("=" * 80)
    
    results = []
    
    # Run all test cases
    results.append(("案例1: 中文示例", test_case_1_example_in_chinese()))
    results.append(("案例2: 英文示例", test_case_2_example_in_english()))
    results.append(("案例3: 真实 leaked call", test_case_3_real_leaked_tool_call()))
    results.append(("案例4: 带解释的示例", test_case_4_example_with_explanation()))
    results.append(("案例5: 代码块中的示例", test_case_5_in_code_block()))
    results.append(("案例6: 不完整结构", test_case_6_incomplete_structure()))
    
    # Summary
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{status} - {name}")
    
    total = len(results)
    passed = sum(1 for _, p in results if p)
    
    print(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！当前实现没有误判问题。")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败！存在误判问题。")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)