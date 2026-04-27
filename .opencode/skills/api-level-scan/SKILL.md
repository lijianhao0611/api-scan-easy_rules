---
name: api-level-scan
description: >
  对 HarmonyOS/OpenHarmony 单个 API 进行规则驱动审计，深度分析调用链路，输出 JSONL 格式的审计发现（含调用链路径）和调用链文档。
  输入为 JSONL 格式的 API 列表（每行含声明、NAPI映射、Framework接口、实现路径等 8 个字段）。
  当用户提供 JSONL 格式的 API 列表并需要对每个 API 逐个进行规范性审计、错误码检查、调用链分析时使用。
  触发场景包括：API 级别审计、单个 API 错误码检查、调用链分析、API 规范性扫描、API level scan。
---

## 参数

```json
{
  "api_input": "JSONL 文本内容或 JSONL 文件路径（每行一个 JSON 对象）",
  "repo_base": "代码仓库基础目录（包含各部件仓库的根目录）",
  "rule_xlsx": "规则 XLSX 文件路径（可选，覆盖 config/rule.json）",
  "out_path": "输出目录"
}
```

| 参数 | 必需 | 说明 |
|------|------|------|
| `api_input` | 是 | n 行 JSONL 数据（每行一个 JSON 对象），或 JSONL 文件路径 |
| `repo_base` | 是 | 代码仓库基础目录，包含各 OpenHarmony 部件仓库 |
| `rule_xlsx` | 否 | 规则 XLSX 文件，提供时先转换为 config/rule.json |
| `out_path` | 是 | 输出目录，结果保存至 `out_path/api_scan/` |

---

## 输入格式

每行一个 JSON 对象，包含 8 个字段：
**格式1**
```json
{"api_declaration": "function setController(controller: WindowAnimationController): void", "module_name": "@ohos.animation.windowAnimationManager", "impl_api_name": "RSWindowAnimationManager::SetController", "impl_repo_path": "graphic_graphic_2d", "declaration_file": "api/@ohos.animation.windowAnimationManager.d.ts", "NAPI_map_file": "graphic_graphic_2d/interfaces/kits/napi/graphic/animation/window_animation_manager/rs_window_animation_manager.cpp", "Framework_decl_file": "graphic_graphic_2d/rosen/modules/animation/window_animation/include/rs_window_animation_stub.h", "impl_file_path": "graphic_graphic_2d/interfaces/kits/napi/graphic/animation/window_animation_manager/rs_window_animation_manager.cpp"}
```

**格式2**
对于部分未能在前期直接找到映射的api，则采用以下格式
```json
{"api_declaration": "function getWant(callback: AsyncCallback<Want>): void", "js_doc": "/**\n....*/", "module_name": "@ohos.ability.featureAbility", "declaration_file": "api/@ohos.ability.featureAbility.d.ts"}
```
对于这些未能找到映射的api，请设定一个subagent，参考/kit-api-extract的技能说明找到对应的api映射，仅要求 subagent输出impl_api.jsonl即可

| 字段 | 类型 | 说明 |
|------|------|------|
| `api_declaration` | string | API 声明（完整函数签名，来自 .d.ts/.d.ets） |
| `module_name` | string | 模块名（如 `@ohos.animation.windowAnimationManager`） |
| `impl_api_name` | string | 实现函数名（NAPI 映射的 C++ 函数名） |
| `impl_repo_path` | string | 仓库名（仅 repo_name，如 `graphic_graphic_2d`） |
| `declaration_file` | string | API 声明文件路径（.d.ts / .d.ets） |
| `NAPI_map_file` | string | NAPI 映射文件路径（C++ NAPI 插件源码，含 JS 方法名到 C++ 函数的映射关系） |
| `Framework_decl_file` | string | Framework 接口声明文件路径（.h 头文件，定义 IPC 接口） |
| `impl_file_path` | string | 业务逻辑实现文件完整路径（.cpp） |

这些字段对应完整的代码路径分析流程：
1. **interface**（`declaration_file`）：暴露给应用层的函数签名、入参和返回类型
2. **NAPI 映射**（`NAPI_map_file`）：JS 方法名与 C++ 函数的映射关系
3. **Framework 接口声明**（`Framework_decl_file`）：IPC Proxy/Stub 模式的接口定义
4. **业务逻辑实现**（`impl_file_path`）：底层实际处理逻辑的代码

---

## 执行步骤

### Phase A：规则准备

#### Step 1. 规则加载

**1.1** 如果用户提供了 `rule_xlsx`：

```bash
python3 {{skill_path}}/scripts/convert_xlsx_to_json.py "{{rule_xlsx}}" "{{skill_path}}/config/rule.json"
```

转换结果覆盖写入 `config/rule.json`。

**1.2** 将 rule.json 复制到 `{out_path}/api_scan/` 目录，命名为 `active_rules.json`。读取 `active_rules.json`，理解每条规则的 `id`、`description`、`example`、`instructions`，作为后续审计依据。

规则结构：
```json
{
  "rules": [
    {"id": "APITEST.ERRORCODE.01.001", "description": "规则描述", "examples": "...", "instructions": "..."}
  ]
}
```

若 `example`、`instructions` 为空，则积极探索代码仓库，识别任何违反规则描述的条目。描述中带有"是否"的，当"否"的情况发生时即为违反该描述。

**1.3** 过滤评分类规则：

```bash
python3 {{skill_path}}/scripts/filter_rules.py "{{skill_path}}/config/rule.json" -o "{{out_path}}/api_scan/active_rules.json"
```

### Phase B：逐 API 审计

#### Step 2. 解析输入

读取 `api_input`（如果是文件路径则读取文件内容），逐行解析为 JSON 对象。记录 API 条目总数 n。

#### Step 3. 逐个 API 处理

对 n 个 API 条目中的每一个，执行以下步骤：

**3.1 Kit 信息提取（从声明文件）**

读取 `declaration_file` 的文件头注释，提取 `@kit` 标签值作为 kit 名称。声明文件头部格式示例：

```typescript
/**
 * @file
 * @kit AbilityKit
 */
```

提取规则：搜索文件开头的 JSDoc 注释块中 `@kit` 标签，取其值（如 `AbilityKit`）。如果声明文件中无 `@kit` 标签，则 `kit` 为空字符串。

`部件`（component）直接取 `impl_repo_path` 的值（现在就是仓库名本身，如 `graphic_graphic_2d`）。如果 `impl_repo_path` 为空，则从 `module_name` 推导（去除 `@ohos.` 前缀，将 `.` 替换为 `_`）。

**3.2 定位实现代码**

输入已提供完整的代码路径，agent 直接使用：

- **NAPI 映射层**：`{repo_base}/{NAPI_map_file}` — 包含 JS 方法名到 C++ 函数的映射（`DECLARE_NAPI_FUNCTION` 等）。直接读取此文件，找到 `impl_api_name` 对应的函数入口。
- **业务逻辑实现**：`{repo_base}/{impl_file_path}` — 具体业务逻辑代码。直接读取此文件中的 `impl_api_name` 函数实现。
- **Framework 接口声明**：`{repo_base}/{Framework_decl_file}` — IPC Proxy/Stub 接口定义。用于理解跨进程调用链路和错误码传递。
- **如果 `Framework_decl_file` 为空**：跳过 Framework 层分析，仅在 NAPI 映射层和实现层范围内审计。

**3.3 定位声明文件**

在 `{repo_base}/` 中搜索 `declaration_file`。读取完整文件内容。提取 `js_doc`（如果尚未提供），解析 `@throws`、`@permission`、`@systemapi`、`@syscap`、`@since` 标签。

**3.4 规则驱动审计**

对 `active_rules.json` 中的每条规则，审计 API 的实现代码和声明：

- 读取实现函数体（错误处理分支、返回路径）
- 读取声明文件中的 js_doc（`@throws`、`@permission`、`@systemapi`）
- 检查错误码映射（沿调用链追踪）
- 结合 `references/problem_patterns_checklist.md` 识别问题模式
- **记录调用链路径**：对每个发现的问题，记录从 NAPI 入口到问题位置的完整调用路径（如 `NAPI_PAGetWant->GetWant->Ability::GetWant`），写入 `finding_description`

每个发现生成一个结构化 JSON 对象，**必须严格遵循以下 raw_findings.json 格式**。

### Phase B 续：raw_findings.json 结构（严格遵守）

所有发现写入 `{out_path}/api_scan/raw_findings.json`，格式为 `{"findings": [...]}`。

**合并规则（重要）**：同一 `rule_id` + 同一 API 的多处违反点必须合并为一条 finding，不允许拆分为多条。多处的违反证据全部放入 `evidence` 数组中，`finding_description` 综合描述所有违反点。

**每条 finding 必须包含以下 9 个字段，字段名和类型不可更改**：

```json
{
  "rule_id": "APITEST.ERRORCODE.02.003",
  "rule_description": "检查API的异常分支是否返回了错误码和错误信息",
  "finding_description": "[调用链 NAPI_PAGetWant->GetWant->ProcessCallback] 存在多处异常分支未返回错误码。(1)[问题代码片段(5行以内)]第196行 GetWant 返回失败时仅返回 undefined；(2)[问题代码片段(5行以内)]第210行 ProcessCallback 回调错误时未抛出 BusinessError",
  "evidence": [
    {"file": "ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp", "line": 196, "snippet": "return undefined;"},
    {"file": "ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp", "line": 210, "snippet": "napi_get_undefined(env, &result);"}
  ],
  "component": "ability_ability_runtime",
  "affected_apis": ["getWant"],
  "modification_suggestion": "在 NAPI_PAGetWant 中：(1)第196行 GetWant 失败时通过 napi_throw 抛出 BusinessError；(2)第210行回调错误时同样抛出 BusinessError",
  "severity_level": "严重",
  "affected_error_codes": ""
}
```

**字段名对照表（raw_findings → 最终 JSONL）**：

| raw_findings 字段 (英文名) | 最终 JSONL 字段 (中文名) | 类型 | 说明 |
|---|---|---|---|
| `rule_id` | `编号` | string | 规则 ID，必须存在于 active_rules.json |
| `rule_description` | `问题描述` | string | 规则描述，与 active_rules.json 中一致 |
| `finding_description` | `发现详情说明` | string | 本次实际发现的问题描述。必须以调用链路径开头（格式 `入口函数->函数A->函数B`），后跟具体问题描述，多处违反用 (1)(2)(3) 编号列举，并且提供对应的问题代码片段，仅一处违反时也需要提供5行以内的问题代码片段 |
| `evidence` | `代码文件` + `代码行位置` | array | 证据数组，每个元素含 `file`(string)、`line`(int,>0)、`snippet`(string,可选)。最终 JSONL 中转换为逗号分隔字符串，无行号用 `NA`，注意该行号必须是问题出现位置行号 |
| `component` | `部件` | string | 部件仓目录名 |
| `affected_apis` | `受影响的api` | array[string] | 受影响 API 名称列表，通常只有一个元素 |
| `modification_suggestion` | `修改建议` | string | 具体可操作的修改建议，不可为空 |
| `severity_level` | `问题严重等级` | string | 必须是 `严重`/`高`/`中`/`低` 四选一 |
| `affected_error_codes` | `影响的错误码` | string | 逗号分隔数字错误码（如 `"201,13900020"`），无则为空字符串 `""` |

**完整 raw_findings.json 文件结构（含合并示例）**：

```json
{
  "findings": [
    {
      "rule_id": "APITEST.ERRORCODE.02.003",
      "rule_description": "检查API的异常分支是否返回了错误码和错误信息",
      "finding_description": "[调用链 NAPI_Connect->Connect->SocketCreate->BindAddress]：存在 3 处异常分支未返回错误码。(1)[问题代码片段(5行以内)]第120行参数校验失败时返回 nullptr；(2)[问题代码片段(5行以内)]第145行 SocketCreate 创建失败时返回 undefined；(3)第178行 BindAddress 超时时静默返回",
      "evidence": [
        {"file": "communication_netstack/.../net_connection.cpp", "line": 120, "snippet": "return nullptr;"},
        {"file": "communication_netstack/.../socket.cpp", "line": 145, "snippet": "napi_get_undefined(env, &result);"},
        {"file": "communication_netstack/.../address.cpp", "line": 178, "snippet": "return;"}
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

**常见错误（会导致 classify_findings.py 校验失败）**：
- 字段名使用中文名（如 `"编号"` 而非 `"rule_id"`）→ ❌ 必须使用英文字段名
- 同一 rule_id + 同一 API 拆成多条 finding → ❌ 必须合并为一条，多处违反放入 evidence 数组
- 缺少 `evidence` 或 `evidence` 为空数组 → ❌ 至少一条证据
- `evidence[].line` 为 0 或负数 → ❌ 必须大于 0
- `severity_level` 使用英文（如 `"high"` 而非 `"高"`）→ ❌ 必须中文
- `severity_level` 使用 `"serious"` → ❌ 必须是 `严重`
- `modification_suggestion` 为空字符串 → ❌ 必须有具体内容
- `affected_error_codes` 包含非数字字符 → ❌ 仅逗号分隔数字或空字符串
- `affected_apis` 为字符串而非数组 → ❌ 必须是数组
- `component` 为空 → ❌ 必须填写部件仓目录名
- `rule_id` 不在 active_rules.json 中 → ❌ 必须是有效规则 ID
- 报告遵守规则的问题 → ❌ 不得生成 finding

**3.5 调用链分析（无深度限制）**

从 NAPI 实现入口点（如 `DECLARE_NAPI_FUNCTION("getWant", NAPI_PAGetWant)` 中的 `NAPI_PAGetWant`）开始，自由追踪所有外部业务逻辑函数调用，无层级深度限制。

调用链追踪规则：
1. **入口**：NAPI 实现函数（如 `NAPI_PAGetWant`），即 `DECLARE_NAPI_FUNCTION` 宏中注册的函数
2. **递归追踪**：对每个函数，识别其调用的外部业务逻辑函数，然后继续追踪这些函数的调用，直到函数体中不再有需要分析的业务逻辑调用为止
3. **记录路径**：对每个发现的问题，记录从 NAPI 入口到问题所在函数的完整调用路径

"外部业务逻辑函数"：在同一代码库中定义的业务逻辑函数。排除标准库、OS API、框架函数（如 `napi_create_int32`、`std::make_shared`、`NAPI_CALL`、`memcpy`）。

**调用链路径格式**（写入 finding_description）：
```
NAPI_PAGetWant->GetWant->Ability::GetWant
```
用 `->` 连接从入口到问题位置的函数名序列。

**调用链路径示例**：
- 问题在入口函数本身：路径为 `NAPI_PAGetWant`
- 问题在入口直接调用的函数 A 中：路径为 `NAPI_PAGetWant->A`
- 问题在 A 调用的函数 C 中：路径为 `NAPI_PAGetWant->A->C`
- 同一发现涉及多处不同深度的违反：取最长公共路径前缀 + 各分支，在描述中分别标注

详细的调用链分析方法见 `references/call_chain_analysis_guide.md`。

**3.6 错误码提取**

在完整调用链中，识别所有生成 `BusinessError` 对象或向 JS 层返回错误码的代码路径。提取开发者实际接收到的**数字错误码**。这些是面向开发者的错误码（如 `201`、`202`、`13900020`），而非内部原生错误码（如 `-ENOSPC`）。

将提取的错误码记录为逗号分隔字符串（如 `"201,13900020"`）。如果发现不涉及特定错误码（如命名规范问题），则使用空字符串 `""`。

注意：成功码（0）不是错误码，必须排除。

### Phase C：分类与验证

#### Step 4. 自校验 raw_findings.json

在生成 raw_findings.json 后、分类验证前，进行自检：

- 检查 `rule_id` 是否在 `active_rules.json` 中存在
- 结合 `finding_description` 检查 `evidence` 是否真实（通过代码分析验证）
- 检查 `affected_apis` 数组中的 API 是否确实受影响
- 检查 `modification_suggestion` 是否非空且具有可操作性
- 检查 `severity_level` 是否为 `严重`/`高`/`中`/`低` 之一
- 检查 `affected_error_codes` 是否为逗号分隔数字或空字符串
- 检查所有 9 个必需字段（`rule_id`、`rule_description`、`finding_description`、`evidence`、`component`、`affected_apis`、`modification_suggestion`、`severity_level`、`affected_error_codes`）是否存在

发现不符合要求的条目必须修正，随后才能进入分类验证。

#### Step 5. 分类验证

```bash
python3 {{skill_path}}/scripts/classify_findings.py "{{out_path}}/api_scan/raw_findings.json" --rules "{{out_path}}/api_scan/active_rules.json" -o "{{out_path}}/api_scan/classified_findings.json"
```

#### Step 6. 生成输出

生成以下文件到 `{out_path}/api_scan/`：

| 文件 | 说明 |
|------|------|
| `api_scan_findings.jsonl` | JSONL 格式审计发现，每行一个发现（16 个字段） |
| `api_call_chains.json` | 每个 API 的调用链 JSON |
| `api_scan_summary.md` | 汇总报告，参照 `templates/api_scan_summary.md` |

**JSONL 每行字段**：

```json
{"kit":"AbilityKit","部件":"ability_ability_runtime","编号":"APITEST.ERRORCODE.0x.00x","问题描述":"规则描述","发现详情说明":"[调用链][问题详情][问题代码片段(5行以内)]","代码文件":"file.cpp,file.cpp","代码行位置":"196,210","受影响的api":"getWant","api声明":"function getWant(callback: AsyncCallback<Want>): void","声明文件位置":"@ohos.ability.featureAbility.d.ts","修改建议":"具体修改建议","问题严重等级":"严重","影响的错误码":"201,13900020","since":"7","deprecated":"since 9","reserved":""}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `kit` | string | Kit 名称，从声明文件 `@kit` 标签提取，无则为空字符串 |
| `部件` | string | 部件仓目录名，从 `impl_repo_path` 首段或 `module_name` 推导 |
| `编号` | string | 规则 ID，来自 active_rules.json |
| `问题描述` | string | 规则描述，来自 active_rules.json |
| `发现详情说明` | string | 本次实际发现的问题描述，多处违反用 (1)(2)(3) 编号列举，按照[调用链][问题详情][问题代码片段(5行以内)]的格式，若多处则为[调用链][问题详情](1)[问题代码片段(5行以内)][具体问题](2)[问题代码片段(5行以内)][具体问题]|
| `代码文件` | string | 逗号分隔的代码文件路径，与 evidence 数组一一对应 |
| `代码行位置` | string | 逗号分隔的代码行号，无行号用 `NA`，与代码文件一一对应 |
| `受影响的api` | string | 受影响的 API 名称 |
| `api声明` | string | 完整方法签名 |
| `声明文件位置` | string | 声明文件名（仅文件名，非完整路径） |
| `修改建议` | string | AI 提供的具体修改建议 |
| `问题严重等级` | string | `严重`/`高`/`中`/`低` |
| `影响的错误码` | string | 开发者收到的逗号分隔数字错误码，无则为空字符串 |
| `since` | string | @since 原始值，多个用 `; ` 连接；无则为空字符串 |
| `deprecated` | string | @deprecated 值；无则为空字符串 |
| `reserved` | string | @reserved 原始值；无则为空字符串 |

**调用链 JSON 结构**：

```json
[
  {
    "api_name": "getWant",
    "api_declaration": "function getWant(callback: AsyncCallback<Want>): void",
    "module_name": "@ohos.ability.featureActivity",
    "implementation": {
      "function_name": "NAPI_PAGetWant",
      "file": "ability_ability_runtime/frameworks/js/napi/particleAbility/particle_ability.cpp",
      "line": 180
    },
    "call_chain": {
      "level_1": [
        {
          "function_name": "GetWant",
          "file": "particle_ability.cpp",
          "line": 185,
          "level_2": [
            {
              "function_name": "Ability::GetWant",
              "file": "ability.cpp",
              "line": 210
            }
          ]
        }
      ]
    }
  }
]
```

- Level 2 条目不包含 `level_2` 字段（分析在此停止）
- 未找到实现的 API 仍包含条目，`implementation` 为 null，`call_chain` 为空
- 排除标准库/框架调用

**问题严重等级评估标准**：

| 等级 | 判定标准 |
|------|---------|
| **严重** | API 静默失败（返回 undefined/null/void）、错误码为字符串类型、多对一错误码映射导致信息丢失、错误码与根因完全不匹配 |
| **高** | 缺失错误码定义（如 @permission 缺 201、@systemapi 缺 202）、异常分支未抛出错误码、错误消息为空、跨语言错误码不一致 |
| **中** | 错误码与文档描述不符、错误消息过于笼统（如 "Internal error"）、冗余错误码定义、声明与实现轻微不一致 |
| **低** | 命名规范问题、参数排序问题、文档格式/措辞问题、非功能性小问题 |

### Phase D：验证

#### Step 7. 输出验证

```bash
python3 {{skill_path}}/scripts/validate_output.py "{{out_path}}/api_scan" --rules "{{out_path}}/api_scan/active_rules.json"
```

验证项包括：JSON/JSONL 有效性、必需字段完整性（含 `影响的错误码`）、规则存在性、证据非空、严重等级合法性、错误码格式、调用链结构、去重检查。

**验证失败必须修复后才能完成。**

---

## 执行顺序（严格按序）

1. 规则加载 — `scripts/convert_xlsx_to_json.py`（若提供 rule_xlsx）→ `filter_rules.py`
2. 解析输入 — 逐行解析 JSONL，检测格式
3. 逐 API 审计 — 读取声明文件提取 @kit → 定位实现 → 规则审计 → 调用链分析 → 错误码提取
4. 自校验 — 检查 raw_findings.json 内容
5. 分类验证 — `scripts/classify_findings.py`
6. 生成输出 — JSONL + 调用链 JSON + 汇总报告
7. 输出验证 — `scripts/validate_output.py`（必须执行）

**任何步骤失败必须中止整个流程。**

---

## 关键参考文件

| 文件 | 用途 |
|------|------|
| `config/rule.json` | 唯一规则来源（16 条审计规则） |
| `references/call_chain_analysis_guide.md` | 2 层调用链分析方法 |
| `references/output_schema.md` | JSONL + 调用链输出结构定义 |
| `references/problem_patterns_checklist.md` | 常见问题模式（40 项） |
| `references/common_error_codes.md` | 通用错误码参考（201/202/203/401/801） |
| `references/LESSONS_LEARNED.md` | 历史审计经验 |
| `templates/api_scan_summary.md` | 汇总报告模板 |

---

## 注意事项

1. **config/rule.json 是唯一规则来源**
2. **每个 API 独立审计**，不按 Kit 分组
3. **kit 从声明文件 `@kit` 标签获取**，不从 kit_compont.csv 查询
4. **同一 rule_id + 同一 API 的多处违反必须合并**为一条 finding，所有违反点放入 evidence 数组，finding_description 综合描述
5. **调用链分析限制 2 层**：API → Level 1 → Level 2，停止。不追踪 Level 2 的进一步调用
6. **影响的错误码** 必须是开发者通过 BusinessError.code 收到的数值错误码，不是原生层内部错误码
7. **成功码（0）不是错误码**，在影响的错误码中排除
8. 每个 API 必须审计 `active_rules.json` 中的所有规则
9. 所有发现必须包含 `修改建议` 和 `问题严重等级`
10. 无发现的 API 不输出 JSONL 行，但仍包含在调用链 JSON 中
11. 如果输入量较大（>20 个 API），每处理 10 个 API 将中间结果刷新到文件
12. 仅报告实际违反规则的问题，不得报告遵守规则的情况

---

## 禁止事项

- 禁止输出评分、权重等评分类字段
- 禁止按 Kit 聚合输出（这是按 API 的审计）
- 禁止使用 GetDoc.py 或抓取文档
- 禁止使用 extract_js_api.py 或 extract_c_api.py（用户直接提供 API 列表）
- 禁止跳过 validate_output.py 验证步骤
- 禁止忽略验证错误
- 禁止追踪超过 2 层的外部函数调用
