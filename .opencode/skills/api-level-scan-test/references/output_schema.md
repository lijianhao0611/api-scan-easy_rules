# 输出数据结构定义

## 中间文件: raw_findings.json

审计过程中生成的中间文件，供 `classify_findings.py` 验证。**字段名必须使用英文，不可使用中文名**。

### 合并规则（关键）

同一 `rule_id` + 同一 API 的多处违反点必须合并为一条 finding。多处的违反证据全部放入 `evidence` 数组中，`finding_description` 综合描述所有违反点。

### 文件结构

```json
{
  "findings": [
    {
      "rule_id": "APITEST.ERRORCODE.02.003",
      "rule_description": "检查API的异常分支是否返回了错误码和错误信息",
      "finding_description": "connect 实现中存在 3 处异常分支未返回错误码：(1)第120行参数校验失败时返回 nullptr；(2)第145行 socket 创建失败时返回 undefined；(3)第178行连接超时时静默返回",
      "evidence": [
        {"file": "communication_netstack/.../net_connection.cpp", "line": 120, "snippet": "return nullptr;"},
        {"file": "communication_netstack/.../net_connection.cpp", "line": 145, "snippet": "napi_get_undefined(env, &result);"},
        {"file": "communication_netstack/.../net_connection.cpp", "line": 178, "snippet": "return;"}
      ],
      "component": "communication_netstack",
      "affected_apis": ["connect"],
      "modification_suggestion": "在 connect 实现中：(1)第120行参数校验失败时抛出 BusinessError(401,...)；(2)第145行 socket 创建失败时抛出对应错误码；(3)第178行连接超时时抛出 BusinessError",
      "severity_level": "严重",
      "affected_error_codes": ""
    }
  ]
}
```

### 字段定义（9 个必需字段）

| 字段名 | 类型 | 必需 | 说明 |
|--------|------|------|------|
| `rule_id` | string | 是 | 规则 ID，必须存在于 active_rules.json |
| `rule_description` | string | 是 | 规则描述，与 active_rules.json 一致 |
| `finding_description` | string | 是 | 综合描述所有违反点（编号列举，如 (1)...(2)...(3)...） |
| `evidence` | array | 是 | 所有违反点的证据数组，至少一个元素 |
| `evidence[].file` | string | 是 | 代码文件相对路径 |
| `evidence[].line` | int | 是 | 行号，必须 > 0 |
| `evidence[].snippet` | string | 否 | 相关代码片段 |
| `component` | string | 是 | 部件仓目录名，不可为空 |
| `affected_apis` | array[string] | 是 | 受影响 API 名称列表 |
| `modification_suggestion` | string | 是 | 针对所有违反点的综合修改建议，不可为空 |
| `severity_level` | string | 是 | 必须是 `严重`/`高`/`中`/`低` |
| `affected_error_codes` | string | 是 | 逗号分隔数字或空字符串 `""` |

### raw_findings → 最终 JSONL 字段映射

```
raw_findings.rule_id                 → JSONL.编号
raw_findings.rule_description        → JSONL.问题描述
raw_findings.finding_description     → JSONL.发现详情说明
raw_findings.evidence[].file         → JSONL.代码文件（逗号分隔所有证据文件）
raw_findings.evidence[].line         → JSONL.代码行位置（逗号分隔所有行号，无行号用 NA）
raw_findings.component               → JSONL.部件
raw_findings.affected_apis[0]        → JSONL.受影响的api
raw_findings.modification_suggestion → JSONL.修改建议
raw_findings.severity_level          → JSONL.问题严重等级
raw_findings.affected_error_codes    → JSONL.影响的错误码
+ 声明文件 @kit 标签                  → JSONL.kit
+ api_declaration                     → JSONL.api声明
+ declaration_file (仅文件名)          → JSONL.声明文件位置
+ since                               → JSONL.since
+ deprecated                          → JSONL.deprecated
+ reserved                            → JSONL.reserved
```

**代码文件/代码行位置转换规则**：
- 将 evidence 数组中每条证据的 file 用逗号拼接 → `代码文件`
- 将 evidence 数组中每条证据的 line 用逗号拼接 → `代码行位置`，无行号时该位置用 `NA`
- 两个逗号分隔的字段一一对应，数量必须相同

---

## 最终输出 Part 1: api_scan_findings.jsonl

每行是一个 JSON 对象，代表一个 API 的一条审计发现。

### 字段定义

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `kit` | string | 是 | Kit 名称，从声明文件 `@kit` 标签提取，无则为空字符串 `""` |
| `部件` | string | 是 | 部件仓目录名，从 `impl_repo_path` 首段推导 |
| `编号` | string | 是 | 规则 ID，来自 active_rules.json |
| `问题描述` | string | 是 | 规则描述，来自 active_rules.json |
| `发现详情说明` | string | 是 | 本次实际发现的问题描述 |
| `代码文件` | string | 是 | 逗号分隔的代码文件路径，与 evidence 一一对应 |
| `代码行位置` | string | 是 | 逗号分隔的行号，无行号用 `NA`，与代码文件一一对应 |
| `受影响的api` | string | 是 | 受影响的 API 名称 |
| `api声明` | string | 是 | 完整方法签名 |
| `声明文件位置` | string | 是 | 声明文件名（仅文件名，非完整路径） |
| `修改建议` | string | 是 | AI 提供的具体修改建议 |
| `问题严重等级` | string | 是 | `严重` / `高` / `中` / `低` |
| `影响的错误码` | string | 是 | 开发者收到的逗号分隔数字错误码，无则为空字符串 `""` |
| `since` | string | 是 | @since 原始值，多个用 `; ` 连接；无则为空字符串 `""` |
| `deprecated` | string | 是 | @deprecated 值；无则为空字符串 `""` |
| `reserved` | string | 是 | @reserved 原始值；无则为空字符串 `""` |

### 格式要求

- 编码：UTF-8
- 每行恰好一个 JSON 对象，行间无额外分隔符
- 无发现的 API 不输出任何行
- 一个 API 对多条规则有发现时，输出多行（每个发现一行）
- `影响的错误码` 格式：`"201,13900020"` 或 `""`（空字符串）
  - 数值必须是开发者通过 BusinessError.code 收到的错误码
  - 成功码（0）不算错误码，必须排除
  - 内部原生错误码（如负数、位移值）不算，仅记录映射后的开发者可见码

### 示例行

```json
{"kit":"AbilityKit","部件":"ability_ability_runtime","编号":"APITEST.ERRORCODE.02.003","问题描述":"检查API的异常分支是否返回了错误码和错误信息","发现详情说明":"调用链 NAPI_PAGetWant->GetWant->Ability::GetWant：存在 2 处异常分支未返回错误码。(1)第196行 GetWant 返回失败时返回 undefined；(2)第210行 Ability::GetWant 静默返回","代码文件":"ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp,ability_ability_runtime/frameworks/native/ability/ability.cpp","代码行位置":"196,210","受影响的api":"getWant","api声明":"function getWant(callback: AsyncCallback<Want>): void","声明文件位置":"@ohos.ability.featureAbility.d.ts","修改建议":"(1)第196行 GetWant 失败时通过 napi_throw 抛出 BusinessError；(2)第210行 Ability::GetWant 同样抛出 BusinessError","问题严重等级":"严重","影响的错误码":"","since":"7","deprecated":"since 9","reserved":""}
```

---

## Part 2: api_call_chains.json

一个 JSON 数组，每个元素代表一个已审计 API 的调用链信息。**无深度限制**，递归追踪到任意层。

### 结构定义

```typescript
interface CallChainDocument {
  api_name: string;              // API 名称
  api_declaration: string;       // 完整方法签名
  module_name: string;           // 模块名（如 @ohos.ability.featureAbility）
  napi_entry: string;            // NAPI 注册声明（如 DECLARE_NAPI_FUNCTION("getWant", NAPI_PAGetWant)）
  implementation: {              // 实现入口信息，未找到时为 null
    function_name: string;       // 实现函数名（如 NAPI_PAGetWant）
    file: string;                // 实现文件相对路径
    line: number;                // 函数定义行号
  } | null;
  call_chain: CallNode[];        // 顶层调用列表
}

interface CallNode {
  function_name: string;         // 函数名
  file: string;                  // 定义所在文件相对路径
  line: number;                  // 定义行号
  calls: CallNode[];             // 子调用列表（递归），空数组表示叶子节点
}
```

### 格式要求

- 每个节点包含 `function_name`、`file`、`line`、`calls`
- `calls` 为空数组表示叶子节点（无更多业务逻辑调用或定义未找到）
- 未找到实现的 API：`implementation` 为 `null`，`napi_entry` 为空字符串，`call_chain` 为空数组 `[]`
- 排除标准库和框架调用（napi_*、std::*、memcpy 等）
- `file` 字段使用相对于 `repo_base` 的路径
- **无深度限制**，agent 可自由追踪到任意深度

### 示例

```json
[
  {
    "api_name": "getWant",
    "api_declaration": "function getWant(callback: AsyncCallback<Want>): void",
    "module_name": "@ohos.ability.featureActivity",
    "napi_entry": "DECLARE_NAPI_FUNCTION(\"getWant\", NAPI_PAGetWant)",
    "implementation": {
      "function_name": "NAPI_PAGetWant",
      "file": "ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp",
      "line": 180
    },
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
              {"function_name": "WantWrapper::ProcessResult", "file": "ability_ability_runtime/frameworks/native/ability/want_wrapper.cpp", "line": 45, "calls": []}
            ]
          }
        ]
      }
    ]
  },
  {
    "api_name": "hasWindowFocus",
    "api_declaration": "function hasWindowFocus(callback: AsyncCallback<boolean>): void",
    "module_name": "@ohos.ability.featureAbility",
    "napi_entry": "",
    "implementation": null,
    "call_chain": []
  }
]
```

---

## Part 3: api_scan_summary.md

Markdown 格式汇总报告。参照 `templates/api_scan_summary.md` 模板。

包含：
- 审计概览（API 数量、发现数量、规则数量）
- 严重等级分布
- 按 API 汇总
- 按规则汇总
