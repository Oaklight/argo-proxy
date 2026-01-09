# Argo LLMIR Implementation

Argo Gateway API 的 LLMIR 实现，采用轻量化模块化架构。

## 架构概览

本模块遵循 LLMIR 的轻量化架构设计，使用**组合优于继承**的模式：

```
src/argoproxy/llmir/
├── __init__.py       # 模块导出
├── atomic_ops.py     # ArgoAtomicOps - 原子级转换操作
├── complex_ops.py    # ArgoComplexOps - 复杂转换操作
├── converter.py      # ArgoConverter - 主转换器（轻量化）
├── processing.py     # 业务逻辑处理函数
└── README.md         # 本文档
```

## 核心组件

### 1. ArgoAtomicOps（原子级转换操作）

继承自 `llmir.converters.base.BaseAtomicOps`，实现基础内容类型的双向转换：

- **文本转换**: `ir_text_to_p()`, `p_text_to_ir()`
- **图像转换**: `ir_image_to_p()`, `p_image_to_ir()`
- **文件转换**: `ir_file_to_p()`, `p_file_to_ir()` (未实现)
- **工具调用转换**: `ir_tool_call_to_p()`, `p_tool_call_to_ir()`
- **工具结果转换**: `ir_tool_result_to_p()`, `p_tool_result_to_ir()`
- **工具定义转换**: `ir_tool_to_p()`, `p_tool_to_ir()`
- **工具选择转换**: `ir_tool_choice_to_p()`, `p_tool_choice_to_ir()`
- **内容部分转换**: `p_content_part_to_ir()`

**特点**：
- 所有方法都是静态方法
- 对于模型家族特定的转换（如工具调用），委托给 llmir 的专用转换器
- 通过 kwargs 传递预实例化的转换器

### 2. ArgoComplexOps（复杂转换操作）

继承自 `llmir.converters.base.BaseComplexOps`，实现消息、请求、响应级别的转换：

- **消息级转换**: `ir_message_to_p()`, `p_message_to_ir()`
- **内容部分转换**: `ir_content_part_to_p()`
- **请求级转换**: `ir_request_to_p()`, `p_request_to_ir()`
- **响应级转换**: `ir_response_to_p()`, `p_response_to_ir()`
- **辅助方法**: `p_user_message_to_ir()`, `p_assistant_message_to_ir()`

**特点**：
- 所有方法都是静态方法
- 调用 ArgoAtomicOps 处理基础类型
- 返回 `Tuple[result, warnings]` 以收集转换警告

### 3. ArgoConverter（主转换器）

继承自 `llmir.converters.base.BaseConverter`，采用轻量化架构：

```python
class ArgoConverter(BaseConverter):
    # 通过类属性指定 ops 类
    atomic_ops_class = ArgoAtomicOps
    complex_ops_class = ArgoComplexOps
    
    def __init__(self):
        # 预实例化 llmir 转换器
        self._openai_converter = OpenAIChatConverter()
        self._anthropic_converter = AnthropicConverter()
        self._google_converter = GoogleConverter()
    
    def to_provider(self, ir_data, **kwargs):
        # 直接调用 ops 类的静态方法
        return self.complex_ops_class.ir_request_to_p(ir_data, **kwargs)
    
    def from_provider(self, provider_data, **kwargs):
        # 直接调用 ops 类的静态方法
        return self.complex_ops_class.p_request_to_ir(provider_data, **kwargs)
```

**优势**：
- 无需实现大量委托方法
- 代码量减少约 200-300 行
- 清晰的职责分离
- 易于测试和维护

### 4. Processing Functions（业务逻辑）

- `process_chat_with_llmir()`: 处理聊天请求的主函数
- `_send_llmir_non_streaming_request()`: 发送非流式请求

**特点**：
- 与转换逻辑分离
- 专注于 HTTP 请求处理和响应构建
- 使用 ArgoConverter 进行格式转换

## 使用示例

### 基本使用

```python
from argoproxy.llmir import ArgoConverter

# 创建转换器
converter = ArgoConverter()

# 将 Argo 请求转换为 IR 格式
ir_request = converter.from_provider(argo_request_data)

# 将 IR 格式转换回 Argo 格式
argo_data, warnings = converter.to_provider(ir_request)

# 处理警告
for warning in warnings:
    logger.warning(f"Conversion warning: {warning}")
```

### 在端点中使用

```python
from argoproxy.llmir import process_chat_with_llmir

# 在 chat endpoint 中
if config.use_llmir:
    return await process_chat_with_llmir(
        request,
        convert_to_openai=True
    )
```

## 与 LLMIR 的关系

本实现遵循 LLMIR 的架构规范：

1. **继承关系**:
   - `ArgoAtomicOps` ← `BaseAtomicOps`
   - `ArgoComplexOps` ← `BaseComplexOps`
   - `ArgoConverter` ← `BaseConverter`

2. **委托模式**:
   - 工具相关转换委托给 llmir 的专用转换器
   - 根据 `model_family` 选择合适的转换器（OpenAI/Anthropic/Google）

3. **预实例化**:
   - 在 `ArgoConverter.__init__()` 中预实例化转换器
   - 通过 kwargs 传递给 ops 类使用
   - 避免重复创建，提高性能

## 模型家族支持

支持三种模型家族的转换：

- **OpenAI**: 默认格式，使用 `OpenAIChatConverter`
- **Anthropic**: 使用 `AnthropicConverter`
- **Google**: 使用 `GoogleConverter`

模型家族通过 `determine_model_family()` 自动检测，并通过 kwargs 传递给转换方法。

## 转换流程

### 请求转换流程

```
Client Request (Argo format)
    ↓
from_provider() [ArgoConverter]
    ↓
p_request_to_ir() [ArgoComplexOps]
    ↓
p_message_to_ir() [ArgoComplexOps]
    ↓
p_content_part_to_ir() [ArgoAtomicOps]
    ↓
IR Format (standardized)
    ↓
to_provider() [ArgoConverter]
    ↓
ir_request_to_p() [ArgoComplexOps]
    ↓
ir_message_to_p() [ArgoComplexOps]
    ↓
ir_content_part_to_p() [ArgoAtomicOps]
    ↓
Argo Request (processed)
```

### 响应转换流程

```
Argo Response
    ↓
parse_argo_response() [ArgoConverter]
    ↓
p_tool_call_to_ir() [ArgoAtomicOps]
    ↓
IR Response Message
    ↓
OpenAIChatConverter.to_provider()
    ↓
OpenAI Compatible Response
```

## 错误处理

### 转换错误

```python
try:
    ir_request = converter.from_provider(data)
except ValueError as e:
    # 处理无效的输入格式
    logger.error(f"Invalid input: {e}")
except Exception as e:
    # 处理其他转换错误
    logger.error(f"Conversion error: {e}")
```

### 警告收集

```python
argo_data, warnings = converter.to_provider(ir_request)

for warning in warnings:
    logger.warning(f"[LLMIR] {warning}")
```

## 性能优化

1. **预实例化转换器**: 避免每次调用时重复创建
2. **静态方法**: 无需实例创建，直接调用
3. **委托模式**: 复用 llmir 的高效实现

## 测试

运行测试：

```bash
# 运行所有测试
pytest test/

# 运行 LLMIR 相关测试
pytest test/test_chat_completions.py
pytest test/test_function_calling_single.py
pytest test/test_function_calling_multiple.py
```

## 迁移指南

从旧的 `llmir_impl.py` 迁移：

### 导入路径变化

```python
# 旧
from argoproxy.types.llmir_impl import process_chat_with_llmir, ArgoConverter

# 新
from argoproxy.llmir import process_chat_with_llmir, ArgoConverter
```

### API 保持不变

公共 API 完全向后兼容，无需修改使用代码。

## 参考资料

- [LLMIR Base Converter](https://github.com/your-org/llmir/tree/main/src/llmir/converters/base)
- [LLMIR OpenAI Chat Converter](https://github.com/your-org/llmir/tree/main/src/llmir/converters/openai/chat)
- [重构计划文档](../../../plans/llmir_refactoring_plan.md)
- [架构对比文档](../../../plans/llmir_architecture_comparison.md)

---

**创建时间**: 2026-01-09  
**最后更新**: 2026-01-09  
**版本**: 1.0.0