# Claude 泄漏工具调用问题调查报告

> **状态**: 🔄 进行中 - 日志分析完成，待进一步验证
> **最后更新**: 2026-02-04
> **调查分支**: `investigation/leaked-tool-calls`

## 背景

在使用 Claude 模型进行工具调用时，发现了一个问题：Claude 有时会将工具调用信息"泄漏"到文本内容中，而不是通过正常的 `tool_calls` 字段返回。这导致工具调用无法被正确识别和处理。

### 问题现象

Claude 返回的响应中，`tool_calls` 字段为空，但 `content` 字段包含类似以下格式的文本：

```python
{'id': 'toolu_vrtx_01X1tcW6qR1uUoUkfpZMiXnH', 'input': {'ticker': 'MSFT'}, 'name': 'get_stock_price', 'type': 'tool_use'}
```

## 版本演进

### 1. fix/neil-fixes 分支（基础版本）

Neil 首先实现了一个简单直接的修复方案：

**核心逻辑**（[`_process_anthropic_native()`](src/argoproxy/tool_calls/output_handle.py:322-422)）：

```python
import ast
if not claude_tool_calls and "{'id': 'toolu_" in text_content:
    try:
        # 查找平衡的字典
        start_idx = text_content.find("{'id': 'toolu_")
        balance = 0
        end_idx = -1
        for i, char in enumerate(text_content[start_idx:], start=start_idx):
            if char == '{': balance += 1
            elif char == '}': balance -= 1
            if balance == 0:
                end_idx = i + 1
                break

        if end_idx != -1:
            leaked_str = text_content[start_idx:end_idx]
            logger.warning(f"Found leaked tool string: {leaked_str}")
            leaked_dict = ast.literal_eval(leaked_str)
            claude_tool_calls = [leaked_dict]
            # 从文本中移除
            text_content = text_content[:start_idx] + text_content[end_idx:]
    except Exception as e:
        logger.warning(f"Failed to parse leaked tool: {e}")
```

**特点**：

- 简单直接，发现问题就修复
- 无配置开关，始终启用
- 无日志记录，不收集数据
- 代码简洁，约 20 行核心逻辑

### 2. master 分支（增强版本）

在 Neil 的基础上，master 分支添加了以下功能：

#### 2.1 配置开关

```python
# config.py
_enable_leaked_tool_fix: bool = False

@property
def enable_leaked_tool_fix(self):
    """Check if leaked tool call fix is enabled."""
    return self._enable_leaked_tool_fix

# 环境变量支持
if env_enable_leaked_tool_fix := os.getenv("ENABLE_LEAKED_TOOL_FIX"):
    config_data._enable_leaked_tool_fix = str_to_bool(env_enable_leaked_tool_fix)
```

**设计意图**：

- 默认禁用修复，保守策略
- 可通过配置或环境变量启用
- 便于在生产环境中控制行为

#### 2.2 日志记录系统

添加了完整的日志记录功能，用于收集和分析泄漏案例：

```python
def _log_leaked_tool_case(
    text_content: str,
    leaked_str: str,
    request_data: Optional[Dict[str, Any]] = None,
    response_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a leaked tool call case for analysis."""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "leaked_tool_string": leaked_str,
        "full_text_content": text_content,
        "context_before": ...,
        "context_after": ...,
    }

    if request_data:
        log_entry["request"] = request_data
    if response_data:
        log_entry["response"] = response_data

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_entry, f, indent=2, ensure_ascii=False)
```

**设计意图**：

- 收集泄漏案例用于分析
- 记录完整上下文（请求、响应、前后文本）
- 自动压缩日志（超过 50MB 时）
- 便于后续改进修复逻辑

#### 2.3 修改后的处理逻辑

```python
# 检查配置是否启用修复
config_data, _ = load_config(verbose=False)
enable_fix = config_data.enable_leaked_tool_fix if config_data else False

if not claude_tool_calls and "{'id': 'toolu_" in text_content:
    try:
        # ... 查找泄漏的工具调用 ...

        # 总是记录（即使 enable_fix=False）
        _log_leaked_tool_case(
            text_content=text_content,
            leaked_str=leaked_str,
            request_data=request_data,
            response_data=response_data,
        )

        if enable_fix:
            # 启用修复时才解析和移除
            leaked_dict = ast.literal_eval(leaked_str)
            claude_tool_calls = [leaked_dict]
            text_content = text_content[:start_idx] + text_content[end_idx:]
        else:
            # 仅记录，不修复
            logger.warning(f"[LEAKED TOOL FIX DISABLED] Found potential leaked tool call...")
    except Exception as e:
        logger.warning(f"Failed to process potential leaked tool: {e}")
```

## 问题报告

### 现象

- **官方 OpenAI native 模式**：正常工作
- **master 分支（启用 leaked tool fix）**：出现 `internal error, upstream error 500`
- **fix/neil-fixes 分支**：没有此错误

### 根因分析

master 分支新增的日志记录功能存在多个潜在风险点：

#### 1. JSON 序列化失败（最可能）

```python
if request_data:
    log_entry["request"] = request_data  # 可能包含不可序列化的对象
if response_data:
    log_entry["response"] = response_data  # 可能包含不可序列化的对象

json.dump(log_entry, f, indent=2, ensure_ascii=False)  # 可能失败
```

**问题**：

- `request_data` 或 `response_data` 可能包含不可 JSON 序列化的对象
- 大对象序列化可能导致内存问题
- 特殊字符编码问题

#### 2. 文件系统操作失败

```python
log_dir = _get_leaked_tool_log_dir()  # 可能失败
dir_size = _get_log_dir_size(log_dir)  # 可能失败
if dir_size > 50 * 1024 * 1024:
    _compress_log_files(log_dir)  # 可能失败且耗时
```

**问题**：

- 磁盘空间不足
- 权限问题（无法创建目录或写入文件）
- 压缩操作耗时过长导致超时

#### 3. 关键问题：即使禁用修复也会记录

```python
# 总是记录（即使 enable_fix=False）
_log_leaked_tool_case(...)

if enable_fix:
    # 修复逻辑
else:
    # 仅记录，不修复
```

这意味着只要检测到泄漏的工具调用，就会执行日志记录，无论是否启用修复功能。

## 代码差异对比

| 功能       | fix/neil-fixes       | master                            |
| ---------- | -------------------- | --------------------------------- |
| 泄漏检测   | ✅                   | ✅                                |
| 自动修复   | ✅ 始终启用          | ⚙️ 可配置                         |
| 日志记录   | ❌                   | ✅                                |
| 日志压缩   | ❌                   | ✅                                |
| 配置开关   | ❌                   | ✅                                |
| 代码行数   | ~20 行               | ~150 行                           |
| 依赖       | ast                  | ast, gzip, datetime, Path, config |
| 文件 I/O   | ❌                   | ✅                                |
| 潜在风险点 | 1 (ast.literal_eval) | 5+                                |

## 建议方案

### 方案 1：回退到 fix/neil-fixes 的简单方案

**优点**：

- 简单可靠
- 性能更好
- 没有副作用

**缺点**：

- 失去数据收集能力

**实施**：

```bash
git checkout fix/neil-fixes -- src/argoproxy/tool_calls/output_handle.py
git checkout fix/neil-fixes -- src/argoproxy/config.py
```

### 方案 2：修复 master 分支的日志记录问题

如果需要保留数据收集能力，建议：

#### 2.1 使用安全的 JSON 序列化

```python
def _safe_serialize(obj):
    """安全序列化，处理不可序列化的对象"""
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return str(obj)[:1000]  # 截断

log_entry = {
    "timestamp": datetime.now().isoformat(),
    "leaked_tool_string": leaked_str,
    "text_preview": text_content[:500] if text_content else "",
    "text_length": len(text_content),
}

# 只记录关键信息，不记录完整请求/响应
if request_data:
    log_entry["request_model"] = request_data.get("model")
    log_entry["request_has_tools"] = "tools" in request_data
```

#### 2.2 异步日志记录

```python
from concurrent.futures import ThreadPoolExecutor

_log_executor = ThreadPoolExecutor(max_workers=1)

def _log_leaked_tool_case_async(...):
    """异步记录，不阻塞主流程"""
    try:
        _log_executor.submit(_log_leaked_tool_case, ...)
    except Exception:
        pass  # 静默失败
```

#### 2.3 添加开关控制日志记录

```python
# 只在启用修复时才记录
if enable_fix:
    _log_leaked_tool_case(...)
    leaked_dict = ast.literal_eval(leaked_str)
    claude_tool_calls = [leaked_dict]
    text_content = text_content[:start_idx] + text_content[end_idx:]
```

### 方案 3：混合方案（推荐）

1. **保留简单的修复逻辑**（来自 fix/neil-fixes）
2. **添加可选的轻量级日志**：
   - 仅在 `DEBUG_LEAKED_TOOLS=true` 时启用
   - 只记录关键信息（泄漏字符串、时间戳、模型名）
   - 使用异步写入
3. **移除复杂的压缩逻辑**

## 验证步骤

1. **检查日志**：

   ```bash
   grep "Failed to log leaked tool call case" /path/to/logs
   grep "Failed to compress" /path/to/logs
   ```

2. **检查磁盘和权限**：

   ```bash
   ls -la /path/to/leaked_tool_calls/
   du -sh /path/to/leaked_tool_calls/
   ```

3. **测试 fix/neil-fixes**：
   ```bash
   git checkout fix/neil-fixes
   # 运行相同的测试用例
   ```

## 新发现：上游 API 500 错误

### 问题描述

用户报告：

- 直接使用 `https://apps-dev.inside.anl.gov/argoapi/v1` 正常工作
- 通过 argo-proxy (`http://0.0.0.0:60475/v1`) 使用 Claude-4.5-opus 时出现 "Internal Server Error: Upstream API error: 500"
- 使用 Gemini 模型时 argo-proxy 正常工作

### 错误来源分析

错误信息 "Upstream API error: 500" 来自 [`chat.py:608-616`](src/argoproxy/endpoints/chat.py:608-616)：

```python
async with session.post(api_url, headers=headers, json=data) as upstream_resp:
    if upstream_resp.status != 200:
        error_text = await upstream_resp.text()
        return web.json_response(
            {"error": f"Upstream API error: {upstream_resp.status} {error_text}"},
            status=upstream_resp.status,
            content_type="application/json",
        )
```

这表明**上游 ARGO API 本身返回了 500 错误**，而不是 argo-proxy 内部产生的错误。

### 可能的原因

#### 1. 请求数据转换问题

argo-proxy 在发送请求前会对数据进行转换，可能导致上游 API 无法处理：

- **工具调用格式转换**：[`handle_tools()`](src/argoproxy/tool_calls/input_handle.py) 可能产生不兼容的格式
- **消息格式处理**：[`scrutinize_message_entries()`](src/argoproxy/utils/input_handle.py) 可能修改了消息结构
- **模型名称映射**：模型名称可能被错误映射

#### 2. Claude 特定的请求格式问题

Claude 模型可能对请求格式有特殊要求：

- 系统消息处理
- 工具定义格式
- 消息角色顺序

#### 3. 日志记录的副作用（不太可能）

虽然日志记录发生在**响应处理阶段**，但如果在请求准备阶段有任何副作用，可能会影响请求数据。

### 调试建议

#### 1. 对比请求数据

在 [`chat.py:722-724`](src/argoproxy/endpoints/chat.py:722-724) 已有日志输出：

```python
logger.warning(
    f"[chat] data: {json.dumps(sanitize_data_for_logging(data), indent=4)}"
)
```

检查发送给上游 API 的实际请求数据。

#### 2. 检查上游错误详情

错误信息中的 `error_text` 应该包含上游 API 返回的详细错误信息，需要查看完整日志。

#### 3. 直接测试上游 API

使用相同的请求数据直接调用上游 API，确认是否是数据格式问题：

```bash
curl -X POST https://apps-dev.inside.anl.gov/argoapi/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-4.5-opus", "messages": [...], "tools": [...]}'
```

#### 4. 对比两个分支的请求处理

虽然 `input_handle.py` 没有差异，但 master 分支的其他变化可能间接影响了请求处理。

### 关键差异总结

| 组件     | fix/neil-fixes | master |
| -------- | -------------- | ------ |
| 版本     | 2.8.0          | 2.8.1  |
| usage.py | 不存在         | 新增   |
| 日志记录 | 无             | 有     |
| 配置开关 | 无             | 有     |
| 响应处理 | 简单           | 复杂   |

## 结论

### 原始问题（日志记录导致的潜在问题）

master 分支在 fix/neil-fixes 基础上添加的日志记录功能引入了多个潜在的故障点，最可能的原因是 JSON 序列化失败或文件系统操作问题。

### 新问题（上游 API 500 错误）

上游 ARGO API 返回 500 错误，需要进一步调查：

1. 检查发送给上游的请求数据
2. 查看上游返回的详细错误信息
3. 确认是否是 Claude 特定的格式问题

**推荐行动**：

1. **立即**：查看完整的错误日志，获取上游 API 返回的详细错误信息
2. **短期**：回退到 fix/neil-fixes 的简单方案，确认是否解决问题
3. **长期**：如果需要数据收集，实现轻量级的异步日志记录方案

---

## 待办事项

- [ ] 等待同事发送完整的错误日志
- [ ] 分析上游 API 返回的详细错误信息
- [ ] 对比 master 和 fix/neil-fixes 发送的请求数据
- [ ] 确认问题根因
- [ ] 制定修复方案

---

## 日志分析区域

### 收到的日志文件

**来源**: `reference/bugs_report/leaked_tool_logs_20260128_171914.tar.gz`

**解压位置**: `reference/bugs_report/leaked_tool_logs/`

**文件列表**:
- `leaked_tool_20260128_171422_165810.json` (83,269 bytes)
- `leaked_tool_20260128_171653_513513.json` (89,432 bytes)

---

### 日志 1: leaked_tool_20260128_171422_165810.json

**时间戳**: 2026-01-28T17:14:22.166209

**泄漏的工具调用**:
```python
{
    'id': 'toolu_vrtx_01HxkqNiX9NvAXS6Aejq6Wph',
    'input': {
        'command': 'gh api repos/AD-SDL/MADSci/issues/218/sub_issues 2>/dev/null || gh api graphql -f query=\'...\' 2>/dev/null || echo "Sub-issues API not available"',
        'description': 'Try sub_issues API endpoint'
    },
    'name': 'bash',
    'type': 'tool_use',
    'cache_control': None
}
```

**上下文**:
- **context_before**: "Let me check the GitHub sub-issues feature more directly - it looks like they might be using a newer GitHub feature:"
- **context_after**: "" (空)

**请求信息**:
| 字段 | 值 |
|------|-----|
| model | `claudeopus45` |
| max_tokens | 20999 |
| stream | false |
| user | luckierdodge |

**客户端**: OpenCode (CLI 编码助手)

**响应结构**:
```json
{
  "content": "Let me check the GitHub sub-issues feature more directly - it looks like they might be using a newer GitHub feature:{'id': 'toolu_vrtx_01HxkqNiX9NvAXS6Aejq6Wph', ...}",
  "tool_calls": []
}
```

---

### 日志 2: leaked_tool_20260128_171653_513513.json

**时间戳**: 2026-01-28T17:16:53.513590

**泄漏的工具调用**:
```python
{
    'id': 'toolu_vrtx_01DJaLx1tDTwxMoxLhcBqnMj',
    'input': {
        'description': 'Explore EventClient/EventManager',
        'prompt': 'Explore the EventClient and EventManager implementation in this codebase...',
        'subagent_type': 'explore'
    },
    'name': 'task',
    'type': 'tool_use',
    'cache_control': None
}
```

**上下文**:
- **context_before**: "Now let me explore the current EventClient and EventManager codebase to understand the existing implementation:"
- **context_after**: "" (空)

**请求信息**:
| 字段 | 值 |
|------|-----|
| model | `claudeopus45` |
| max_tokens | 20999 |
| stream | false |
| user | luckierdodge |

**客户端**: OpenCode (CLI 编码助手)

**响应结构**:
```json
{
  "content": "Now let me explore the current EventClient and EventManager codebase to understand the existing implementation:{'id': 'toolu_vrtx_01DJaLx1tDTwxMoxLhcBqnMj', ...}",
  "tool_calls": []
}
```

---

### 版本与代码关联分析

#### 使用的 argo-proxy 版本

日志是由 argo-proxy 的 [`_log_leaked_tool_case()`](src/argoproxy/tool_calls/output_handle.py:109-167) 函数生成的。

**日志格式匹配验证**:

| 日志字段 | 代码位置 | 匹配 |
|----------|----------|------|
| `timestamp` | 第 142 行 | ✓ |
| `leaked_tool_string` | 第 143 行 | ✓ |
| `full_text_content` | 第 144 行 | ✓ |
| `context_before` | 第 145-147 行 | ✓ |
| `context_after` | 第 148-152 行 | ✓ |
| `request` | 第 155-156 行 | ✓ |
| `response` | 第 157-158 行 | ✓ |

**文件名格式**: `leaked_tool_{timestamp}.json` (第 139 行)

**结论**: 日志由 **master 分支** (版本 2.8.1+) 生成，因为：
1. 日志记录功能是 master 分支新增的
2. fix/neil-fixes 分支 (2.8.0) 没有日志记录功能

#### 重要发现：请求格式异常

日志中的工具定义使用 **Anthropic 原生格式**：

```json
{
  "input_schema": {
    "type": "object",
    "properties": {...}
  },
  "name": "bash",
  "cache_control": null,
  "description": "...",
  "type": "custom"
}
```

而非 OpenAI 格式（argo-proxy 期望的输入格式）：

```json
{
  "type": "function",
  "function": {
    "name": "bash",
    "parameters": {...}
  }
}
```

**这意味着**：
1. 客户端（OpenCode）直接发送 Anthropic 格式的工具定义
2. 请求可能绕过了 argo-proxy 的工具格式转换逻辑
3. 或者 argo-proxy 的输入处理没有正确转换这种格式

---

### 关键发现

#### 1. 模型信息
- 两个案例都使用 **`claudeopus45`** 模型（Claude 4.5 Opus）
- 这是 Anthropic 的最新模型

#### 2. 泄漏模式特征

| 特征 | 描述 |
|------|------|
| 格式 | Python 字典格式（非 JSON） |
| ID 前缀 | `toolu_vrtx_` (Anthropic 原生格式) |
| 位置 | 紧跟解释性文本，无分隔符 |
| cache_control | 包含 `None` 值（Python 特有） |

#### 3. 响应结构异常

```
正常情况:
  response.content = "文本内容"
  response.tool_calls = [{"id": "...", "function": {...}}]

泄漏情况:
  response.content = "文本内容{'id': 'toolu_vrtx_...', ...}"
  response.tool_calls = []
```

#### 4. 工具定义格式

请求中的工具使用 **Anthropic 原生格式**：
```json
{
  "input_schema": {
    "type": "object",
    "properties": {...}
  },
  "name": "bash",
  "cache_control": null,
  "description": "...",
  "type": "custom"
}
```

而非 OpenAI 格式：
```json
{
  "type": "function",
  "function": {
    "name": "bash",
    "parameters": {...}
  }
}
```

#### 5. 客户端信息

- **客户端**: OpenCode (https://github.com/anomalyco/opencode)
- **类型**: CLI 编码助手
- **用户**: luckierdodge
- **工作目录**: /Users/luckierdodge/AD-SDL/MADSci

---

### 问题根因分析

基于日志分析，问题的根因可能是：

#### 假设 1: 上游 ARGO API 响应格式问题 ⭐ 最可能

Claude 模型返回的 `tool_use` 块没有被正确解析为结构化的 `tool_calls`，而是被序列化为 Python 字典格式并嵌入到文本内容中。

**证据**:
- 泄漏的格式是 Python 字典（使用单引号、`None` 而非 `null`）
- 这表明某处代码使用了 `str()` 或 `repr()` 而非 `json.dumps()`
- 上游 ARGO API 可能在处理 Claude 4.5 Opus 响应时存在 bug

**代码关联**:
- [`_process_anthropic_native()`](src/argoproxy/tool_calls/output_handle.py:342-464) 期望响应格式为：
  ```json
  {
    "response": {
      "content": "text",
      "tool_calls": [{"id": "toolu_...", "input": {...}, "name": "...", "type": "tool_use"}]
    }
  }
  ```
- 但实际收到的是 `tool_calls: []` 且工具调用嵌入在 `content` 中

#### 假设 2: 模型行为异常

Claude 4.5 Opus 在某些情况下可能会将工具调用"泄漏"到文本输出中，而不是通过正常的工具调用机制返回。

**证据**:
- 两个案例都发生在 Claude 4.5 Opus 上
- 工具调用紧跟在解释性文本之后，没有换行或分隔

#### 假设 3: 请求格式不兼容

OpenCode 客户端发送的工具定义格式可能与上游 API 期望的格式不完全兼容。

**证据**:
- 工具定义使用了 `type: "custom"` 字段（非标准）
- 包含 `cache_control` 字段（Anthropic 特有）
- 工具格式是 Anthropic 原生格式，而非 OpenAI 格式

**代码关联**:
- argo-proxy 的 [`handle_tools_native()`](src/argoproxy/tool_calls/input_handle.py:247-475) 负责工具格式转换
- 如果输入已经是 Anthropic 格式，转换逻辑可能不会正确处理

---

### 与现有修复的关联

| 分支 | 处理方式 |
|------|----------|
| fix/neil-fixes | 检测 `{'id': 'toolu_` 模式并解析修复 |
| master | 添加日志记录 + 可选修复 |

**Neil 的修复逻辑**可以正确处理这种情况：
```python
if not claude_tool_calls and "{'id': 'toolu_" in text_content:
    # 查找并解析泄漏的工具调用
    leaked_dict = ast.literal_eval(leaked_str)
    claude_tool_calls = [leaked_dict]
```

---

### 下一步行动

1. **确认修复有效性**
   - [ ] 在 fix/neil-fixes 分支上测试相同的请求
   - [ ] 验证工具调用是否被正确提取

2. **调查上游 API**
   - [ ] 检查 ARGO API 对 Claude 4.5 Opus 的支持情况
   - [ ] 确认是否是已知问题
   - [ ] 联系上游团队报告此问题

3. **优化修复方案**
   - [ ] 考虑添加对 `cache_control: None` 的处理
   - [ ] 确保修复逻辑能处理多个连续的工具调用
   - [ ] 添加对 Anthropic 原生工具格式输入的兼容处理

4. **长期方案**
   - [ ] 向上游报告此问题
   - [ ] 考虑添加更健壮的工具调用解析逻辑
   - [ ] 评估是否需要支持 Anthropic 原生格式的直接透传

---

## 代码参考

### 关键文件

| 文件 | 功能 |
|------|------|
| [`output_handle.py`](src/argoproxy/tool_calls/output_handle.py) | 响应处理和泄漏检测 |
| [`input_handle.py`](src/argoproxy/tool_calls/input_handle.py) | 请求工具格式转换 |
| [`config.py`](src/argoproxy/config.py) | 配置管理（`enable_leaked_tool_fix`） |

### 泄漏检测逻辑

```python
# output_handle.py:400-445
if not claude_tool_calls and "{'id': 'toolu_" in text_content:
    # 查找平衡的字典
    start_idx = text_content.find("{'id': 'toolu_")
    # ... 平衡括号查找 ...
    
    if end_idx != -1:
        leaked_str = text_content[start_idx:end_idx]
        
        # 总是记录日志
        _log_leaked_tool_case(...)
        
        if enable_fix:
            # 解析并修复
            leaked_dict = ast.literal_eval(leaked_str)
            claude_tool_calls = [leaked_dict]
            text_content = text_content[:start_idx] + text_content[end_idx:]
```

### 版本信息

| 分支 | 版本 | 泄漏修复 | 日志记录 |
|------|------|----------|----------|
| fix/neil-fixes | 2.8.0 | ✅ 始终启用 | ❌ |
| master | 2.8.1+ | ⚙️ 可配置 | ✅ |
| 当前 | 2.8.2 | ⚙️ 可配置 | ✅ |

---

## 请求处理流程分析

### 请求处理链路

```
客户端请求 → argo-proxy → 上游 ARGO API → Claude 模型
```

### 关键处理步骤

1. **接收请求** ([`chat.py:694`](src/argoproxy/endpoints/chat.py:694))
   ```python
   data = await request.json()
   ```

2. **图片处理** ([`chat.py:712`](src/argoproxy/endpoints/chat.py:712))
   ```python
   data = await process_chat_images(session, data, config)
   ```

3. **请求数据准备** ([`chat.py:715-717`](src/argoproxy/endpoints/chat.py:715-717))
   ```python
   data = prepare_chat_request_data(
       data, config, model_registry, enable_tools=True
   )
   ```

4. **工具调用处理** ([`input_handle.py:483-528`](src/argoproxy/tool_calls/input_handle.py:483-528))
   - 检测模型类型：`determine_model_family(data.get("model", "gpt4o"))`
   - Claude 模型 → `model_type = "anthropic"`
   - 转换工具格式：OpenAI → Anthropic

5. **发送请求** ([`chat.py:607`](src/argoproxy/endpoints/chat.py:607))
   ```python
   async with session.post(api_url, headers=headers, json=data) as upstream_resp:
   ```

### Claude 特定的格式转换

当检测到 Claude 模型时，[`handle_tools_native()`](src/argoproxy/tool_calls/input_handle.py:247-475) 会进行以下转换：

#### 1. 工具定义转换
```python
# OpenAI 格式
{"type": "function", "function": {"name": "...", "parameters": {...}}}

# 转换为 Anthropic 格式
{"name": "...", "input_schema": {...}}
```

#### 2. 工具调用消息转换
```python
# OpenAI 格式 (assistant message with tool_calls)
{"role": "assistant", "tool_calls": [{"id": "...", "function": {...}}]}

# 转换为 Anthropic 格式 (content array with tool_use blocks)
{"role": "assistant", "content": [{"type": "tool_use", "id": "...", "name": "...", "input": {...}}]}
```

#### 3. 工具结果消息转换
```python
# OpenAI 格式
{"role": "tool", "tool_call_id": "...", "content": "..."}

# 转换为 Anthropic 格式
{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}
```

### 潜在问题点

1. **格式转换错误**
   - 工具定义转换可能丢失必要字段
   - 消息格式转换可能不完整

2. **上游 API 不兼容**
   - 上游 ARGO API 可能期望特定格式
   - 转换后的格式可能不被接受

3. **两个分支的差异**
   - 虽然 `input_handle.py` 没有差异
   - 但 master 分支的其他变化可能间接影响了请求处理

### 验证方法

1. **对比请求数据**
   - 在两个分支上运行相同的请求
   - 对比 `[chat] data:` 日志输出

2. **直接测试上游 API**
   - 使用 argo-proxy 转换后的数据直接调用上游 API
   - 确认是否是格式问题

3. **检查工具转换日志**
   - 查看 `[Input Handle]` 开头的日志
   - 确认工具格式转换是否正确

---

## OpenCode 客户端分析

### 客户端信息

| 属性 | 值 |
|------|-----|
| 名称 | OpenCode |
| 仓库 | https://github.com/anomalyco/opencode |
| 版本 | v1.1.51 |
| 类型 | CLI 编码助手 |
| 本地代码 | `reference/opencode/` |

### 技术栈

OpenCode 使用 **Vercel AI SDK** (`@ai-sdk/*`) 来处理不同的 LLM 提供商：

```typescript
// provider.ts - 支持的 SDK 包
import { createAnthropic } from "@ai-sdk/anthropic"
import { createOpenAI } from "@ai-sdk/openai"
import { createGoogleGenerativeAI } from "@ai-sdk/google"
// ... 更多提供商
```

### Anthropic 特殊处理

OpenCode 对 Anthropic/Claude 模型有特殊配置：

```typescript
// provider.ts:91-99
async anthropic() {
  return {
    autoload: false,
    options: {
      headers: {
        "anthropic-beta":
          "claude-code-20250219,interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14",
      },
    },
  }
}
```

### 工具调用 ID 规范化

OpenCode 对 Claude 的 `toolCallId` 进行规范化处理：

```typescript
// transform.ts:71-86
if (model.api.id.includes("claude")) {
  return msgs.map((msg) => {
    if ((msg.role === "assistant" || msg.role === "tool") && Array.isArray(msg.content)) {
      msg.content = msg.content.map((part) => {
        if ((part.type === "tool-call" || part.type === "tool-result") && "toolCallId" in part) {
          return {
            ...part,
            // 只保留字母数字和 _-
            toolCallId: part.toolCallId.replace(/[^a-zA-Z0-9_-]/g, "_"),
          }
        }
        return part
      })
    }
    return msg
  })
}
```

### 关键发现

1. **工具格式**: OpenCode 使用 AI SDK 的标准格式，工具调用通过 `tool-call` 和 `tool-result` 类型处理

2. **日志中的格式异常**: 日志中看到的工具格式是 **Anthropic 原生 API 格式**：
   ```python
   {'id': 'toolu_vrtx_01HxkqNiX9NvAXS6Aejq6Wph', 'input': {...}, 'name': 'bash', 'type': 'tool_use', 'cache_control': None}
   ```
   而不是 AI SDK 的格式，这表明问题发生在 **上游 ARGO API** 层面

3. **Python 字典格式**: 泄漏的工具调用使用 Python 字典格式（单引号、`None`），而非 JSON 格式（双引号、`null`），说明某处代码使用了 `str()` 或 `repr()` 而非 `json.dumps()`

---

## 相关案例：LangChain 泄漏问题

### 背景

同事在使用 LangChain 时也遇到过类似的工具调用泄漏问题。

### 共同特征

| 特征 | OpenCode 案例 | LangChain 案例 |
|------|---------------|----------------|
| 模型 | Claude 4.5 Opus | Claude 系列 |
| 泄漏格式 | Python 字典 | 待确认 |
| tool_calls 字段 | 空数组 | 待确认 |
| 上游 API | ARGO API | ARGO API |

### 推断

这两个案例的共同点表明问题可能出在：

1. **上游 ARGO API** 对 Claude 模型响应的处理
2. Claude 模型在某些情况下的特殊行为
3. 工具调用格式转换过程中的 bug

---

## 综合结论

### 问题根因（按可能性排序）

1. **上游 ARGO API 响应处理 bug** ⭐⭐⭐
   - Claude 的 `tool_use` 块没有被正确解析
   - 被序列化为 Python 字典格式嵌入到文本内容中
   - 证据：泄漏格式是 Python 字典（单引号、`None`）

2. **Claude 4.5 Opus 模型行为异常** ⭐⭐
   - 模型在某些情况下将工具调用"泄漏"到文本输出
   - 可能与特定的 prompt 或工具定义格式有关

3. **请求格式不兼容** ⭐
   - OpenCode 发送的 Anthropic 原生格式工具定义
   - 可能与上游 API 期望的格式不完全兼容

### 修复方案评估

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| fix/neil-fixes 简单修复 | 简单可靠、无副作用 | 无数据收集 | ⭐⭐⭐⭐⭐ |
| master 分支日志记录 | 可收集数据分析 | 复杂、有潜在风险 | ⭐⭐⭐ |
| 向上游报告问题 | 根本解决 | 依赖上游响应 | ⭐⭐⭐⭐ |

### 建议行动

1. **立即**: 启用 `ENABLE_LEAKED_TOOL_FIX=true` 或使用 fix/neil-fixes 分支
2. **短期**: 向上游 ARGO API 团队报告此问题
3. **长期**: 优化日志记录功能，使用异步写入和安全序列化
