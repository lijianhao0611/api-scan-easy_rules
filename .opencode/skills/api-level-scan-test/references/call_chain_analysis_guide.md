# 调用链分析指南

## 概述

从 NAPI 实现入口点开始，自由追踪所有外部业务逻辑函数调用，**无深度限制**。对每个发现的问题，记录从 NAPI 入口到问题位置的完整调用路径。

## 外部函数的定义

**属于外部函数（需追踪）**：
- 在同一代码库中定义的业务逻辑函数
- 错误处理/生成函数（如 `CreateBusinessError`、`ThrowError`）
- 数据转换函数（如 `ConvertToJSValue`、`ParseParam`）
- 服务调用函数（如 `Service::GetMethod`）

**不属于外部函数（排除）**：
- NAPI 框架宏/函数：`napi_create_int32`、`napi_get_undefined`、`napi_create_string_utf8`、`NAPI_CALL`、`napi_create_function` 等
- C++ 标准库：`std::make_shared`、`std::string`、`std::to_string`、`std::move` 等
- C 运行时：`memcpy`、`memset`、`strlen`、`sprintf` 等
- 操作系统 API：`pthread_*`、`open`、`close`、`read` 等
- 日志宏：`HILOG_*`、`LOG_*`
- 内存管理宏：`CHECK_*`、`ASSERT_*`

## 提取过程

### 递归追踪

1. 在实现文件中定位 NAPI 入口函数体（通过 `impl_api_name` 或 NAPI 注册宏 `DECLARE_NAPI_FUNCTION` 的搜索结果）
2. 读取完整函数体
3. 识别所有函数调用表达式：
   - 直接调用：`FunctionName(args)`
   - 成员调用：`object->Method(args)`、`object.Method(args)`
   - 静态调用：`Class::StaticMethod(args)`
   - 命名空间调用：`Namespace::Function(args)`
4. 过滤掉标准库/框架调用
5. 对每个保留的调用，记录 `function_name`、`file`（当前文件）、`line`（调用行号）
6. 对每个识别出的外部函数，**重复步骤 2-5**：搜索其定义、读取函数体、识别调用、过滤
7. 当某个函数的定义未找到（如预编译库中）或函数体中无更多业务逻辑调用时，停止该分支

### 调用链路径记录

对每个发现的问题，记录从 NAPI 入口到问题所在函数的完整路径，格式为 `入口->函数A->函数B->...`。

**路径示例**：
- 问题在入口函数中：`NAPI_PAGetWant`
- 问题在入口调用的 GetWant 中：`NAPI_PAGetWant->GetWant`
- 问题在 GetWant 调用的 Ability::GetWant 中：`NAPI_PAGetWant->GetWant->Ability::GetWant`
- 问题在更深层函数中：`NAPI_PAGetWant->GetWant->Ability::GetWant->WantWrapper::ProcessResult`

**同一发现多处违反的路径处理**：
如果多处违反点在不同深度的函数中，在 `finding_description` 中分别标注每处的路径：

```
调用链 NAPI_Connect->Connect->SocketCreate：(1)第120行参数校验失败；(2)第145行 socket 创建失败。调用链 NAPI_Connect->Connect->BindAddress：(3)第178行地址绑定超时
```

## 示例

给定 API `getWant`，实现为 `NAPI_PAGetWant`：

```
NAPI 入口: DECLARE_NAPI_FUNCTION("getWant", NAPI_PAGetWant)
实现函数: NAPI_PAGetWant (particle_ability.cpp:180)
│
├── GetWant (particle_ability.cpp:185)
│   ├── Ability::GetWant (ability.cpp:210)
│   │   ├── WantWrapper::ProcessResult (want_wrapper.cpp:45)
│   │   │   └── ...（可继续追踪）
│   │   └── IntentManager::ResolveIntent (intent_mgr.cpp:88)
│   └── CreateJSWant (napi_common.cpp:45)
│
├── CreateCallbackError (particle_ability.cpp:195)
│   └── napi_create_error (框架调用)                  ← 排除
│
├── napi_get_undefined (框架调用)                      ← 排除
└── NAPI_CALL (框架宏)                                ← 排除
```

生成的调用链 JSON：

```json
{
  "call_chain": [
    {
      "function_name": "GetWant",
      "file": "ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp",
      "line": 185,
      "calls": [
        {
          "function_name": "Ability::GetWant",
          "file": "ability_ability_runtime/frameworks/native/ability/ability.cpp",
          "line": 210,
          "calls": [
            {
              "function_name": "WantWrapper::ProcessResult",
              "file": "ability_ability_runtime/frameworks/native/ability/want_wrapper.cpp",
              "line": 45,
              "calls": []
            },
            {
              "function_name": "IntentManager::ResolveIntent",
              "file": "ability_ability_runtime/frameworks/native/ability/intent_mgr.cpp",
              "line": 88,
              "calls": []
            }
          ]
        },
        {
          "function_name": "CreateJSWant",
          "file": "ability_ability_runtime/frameworks/js/napi/particleAbility/napi_common.cpp",
          "line": 45,
          "calls": []
        }
      ]
    },
    {
      "function_name": "CreateCallbackError",
      "file": "ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp",
      "line": 195,
      "calls": []
    }
  ]
}
```

如果问题发现在 `WantWrapper::ProcessResult` 第 50 行，`finding_description` 的路径部分为：
```
调用链 NAPI_PAGetWant->GetWant->Ability::GetWant->WantWrapper::ProcessResult：第50行...
```

## 与审计的集成

调用链分析在审计过程中起到以下作用：

1. **错误码追踪**：沿完整调用链追踪错误码从产生到返回给开发者的完整路径
2. **静默失败检测**：识别错误在调用链中间某层被吞掉（未传播）的情况
3. **错误码映射**：找到内部错误码转换为开发者可见错误码的映射函数（可能在调用链任意深度）
4. **一致性验证**：检查调用链各层的错误处理是否与声明一致

## 大规模处理建议

如果输入的 API 数量较大（>20 个），建议分批处理：

- 每处理 10 个 API 后，将已生成的 JSONL 行和调用链数据刷新到输出文件
- 中间结果追加写入，避免内存占用过大
- 最后统一进行分类验证和输出验证
