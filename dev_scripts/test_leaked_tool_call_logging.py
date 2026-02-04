"""
Test script to verify the leaked tool call logging functionality.

This script tests:
1. Logging is triggered when leaked tool calls are detected
2. Fix behavior is controlled by the enable_leaked_tool_fix flag
3. Log files are created in the correct location
"""

import json
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from argoproxy.tool_calls.output_handle import ToolInterceptor, _get_leaked_tool_log_dir


def test_logging_without_fix():
    """Test that logging works when fix is disabled (default behavior)"""
    print("\n" + "=" * 80)
    print("测试案例 1: 禁用修复时的日志记录（默认行为）")
    print("=" * 80)
    
    # Ensure fix is disabled
    os.environ.pop("ENABLE_LEAKED_TOOL_FIX", None)
    
    response_data = {
        "content": "Here's an example: {'id': 'toolu_01TEST', 'name': 'test', 'input': {}, 'type': 'tool_use'}",
        "tool_calls": []
    }
    
    # Get log directory before test
    log_dir = _get_leaked_tool_log_dir()
    existing_logs = set(log_dir.glob("leaked_tool_*.json"))
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    # Check for new log files
    new_logs = set(log_dir.glob("leaked_tool_*.json")) - existing_logs
    
    print(f"\n日志目录: {log_dir}")
    print(f"新增日志文件数: {len(new_logs)}")
    
    if new_logs:
        latest_log = max(new_logs, key=lambda p: p.stat().st_mtime)
        print(f"最新日志文件: {latest_log.name}")
        
        with open(latest_log, "r", encoding="utf-8") as f:
            log_data = json.load(f)
        
        print(f"\n日志内容预览:")
        print(f"  - 时间戳: {log_data.get('timestamp')}")
        print(f"  - Leaked 字符串长度: {len(log_data.get('leaked_tool_string', ''))}")
        print(f"  - 完整文本长度: {len(log_data.get('full_text_content', ''))}")
        print(f"  - 包含响应数据: {'response' in log_data}")
        
        print("\n✅ 日志记录功能正常")
        return True
    else:
        print("\n❌ 未生成日志文件")
        return False


def test_fix_enabled():
    """Test that fix works when enabled"""
    print("\n" + "=" * 80)
    print("测试案例 2: 启用修复时的行为")
    print("=" * 80)
    
    # Enable fix
    os.environ["ENABLE_LEAKED_TOOL_FIX"] = "true"
    
    # Test with a real leaked tool call (should be fixed)
    response_data = {
        "content": "{'id': 'toolu_01REAL', 'name': 'get_data', 'input': {'key': 'value'}, 'type': 'tool_use'}",
        "tool_calls": []
    }
    
    log_dir = _get_leaked_tool_log_dir()
    existing_logs = set(log_dir.glob("leaked_tool_*.json"))
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    new_logs = set(log_dir.glob("leaked_tool_*.json")) - existing_logs
    
    print(f"\n检测到的 tool calls: {tool_calls}")
    print(f"处理后的文本内容: '{text_content}'")
    print(f"新增日志文件数: {len(new_logs)}")
    
    if tool_calls and len(new_logs) > 0:
        print("\n✅ 修复功能正常工作且记录了日志")
        return True
    elif tool_calls:
        print("\n⚠️  修复功能工作但未记录日志")
        return False
    else:
        print("\n❌ 修复功能未工作")
        return False


def test_example_also_fixed():
    """Test that examples are also fixed when fix is enabled (simple approach)"""
    print("\n" + "=" * 80)
    print("测试案例 3: 启用修复时也会修复示例（简单方案）")
    print("=" * 80)
    
    # Ensure fix is enabled
    os.environ["ENABLE_LEAKED_TOOL_FIX"] = "true"
    
    response_data = {
        "content": "格式如下：{'id': 'toolu_01EXAMPLE', 'name': 'test', 'input': {}, 'type': 'tool_use'}",
        "tool_calls": []
    }
    
    log_dir = _get_leaked_tool_log_dir()
    existing_logs = set(log_dir.glob("leaked_tool_*.json"))
    
    interceptor = ToolInterceptor()
    tool_calls, text_content = interceptor._process_anthropic_native(response_data)
    
    new_logs = set(log_dir.glob("leaked_tool_*.json")) - existing_logs
    
    print(f"\n检测到的 tool calls: {tool_calls}")
    has_leaked_str = "'id': 'toolu_" in text_content
    print(f"文本内容是否保留: {has_leaked_str}")
    print(f"新增日志文件数: {len(new_logs)}")
    
    # With simple fix approach, even examples will be fixed
    if tool_calls and not has_leaked_str and len(new_logs) > 0:
        print("\n✅ 使用简单修复方案，示例也被修复并记录了日志")
        return True
    else:
        print("\n❌ 简单修复方案未正常工作")
        return False


def main():
    """Run all test cases"""
    print("\n" + "=" * 80)
    print("测试 Leaked Tool Call 日志记录功能")
    print("=" * 80)
    
    results = []
    
    # Run all test cases
    results.append(("案例1: 禁用修复时的日志", test_logging_without_fix()))
    results.append(("案例2: 启用修复时的行为", test_fix_enabled()))
    results.append(("案例3: 示例也被修复（简单方案）", test_example_also_fixed()))
    
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
    
    # Show log directory info
    log_dir = _get_leaked_tool_log_dir()
    log_files = list(log_dir.glob("leaked_tool_*.json"))
    print(f"\n日志目录: {log_dir}")
    print(f"总日志文件数: {len(log_files)}")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败！")
    
    # Cleanup environment
    os.environ.pop("ENABLE_LEAKED_TOOL_FIX", None)
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)