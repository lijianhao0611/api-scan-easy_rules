---
name: api-level-scan-test
description: >
  Harness 模式的 HarmonyOS/OpenHarmony API 规则驱动审计技能。
  将输入 API 列表按模块分组，通过并行 subagent 执行深度调用链审计，
  再由独立校验 subagent 合并结果并生成最终输出。
  输入为 JSONL 格式的 API 列表（每行含声明、NAPI映射、Framework接口、实现路径等 8 个字段）。
  当用户提供 JSONL 格式的 API 列表并需要对每个 API 逐个进行规范性审计、错误码检查、调用链分析时使用。
  触发场景包括：API 级别审计、单个 API 错码检查、调用链分析、API 规范性扫描、API level scan。
---

## 参数

```json
{
  "api_input": "JSONL 文件路径（每行一个 JSON 对象）",
  "repo_base": "代码仓库基础目录（包含各部件仓库的根目录）",
  "rule_xlsx": "规则 XLSX 文件路径（可选，覆盖 config/rule.json）",
  "out_path": "输出目录",
  "max_parallel": 3,
  "group_strategy": "auto",
  "api_error_code_doc_path":"API 文档开源代码仓的根目录",
  "kit_name": "Kit 名称，如 'Ability Kit'",
  "group_size": 80
}
```

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `api_input` | 是 | - | JSONL 文件路径，每行一个 JSON 对象 |
| `repo_base` | 是 | - | 代码仓库基础目录，包含各 OpenHarmony 部件仓库 |
| `rule_xlsx` | 否 | - | 规则 XLSX 文件，提供时先转换为 config/rule.json |
| `out_path` | 是 | - | 输出目录，结果保存至 `out_path/api_scan/` |
| `max_parallel` | 否 | 3 | 并行审计 subagent 最大数量（1-5） |
| `group_strategy` | 否 | `auto` | 分组策略：`module`按模块名 / `fixed`固定大小 / `auto`自动选择 |
| `group_size` | 否 | 80 | `fixed` 策略下每组的 API 数量 |
| `api_error_code_doc_path` | 否 | - | API 错误码文档开源仓根目录（包含 zh-cn 目录），提供时提取错误码文档供 subagent 参考 |
| `kit_name` | 否 | - | Kit 名称（如 "Ability Kit"），与 `api_error_code_doc_path` 同时提供时提取该 Kit 的错误码文档 |

---

## 执行模式

根据输入 API 数量自动选择执行模式：

- **Harness 模式**（默认）：API 数量 > 30 时启用。将 API 列表按模块分组，并行调度审计 subagent 处理每组 API，最后调度独立校验 subagent 合并和验证结果。
- **Direct 模式**：API 数量 <= 30 时使用。Harness 自身直接执行审计，等价于不使用 subagent 的单次处理流程。

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

**1.2** 如果用户同时提供了 `api_error_code_doc_path` 和 `kit_name`，提取错误码文档：

```bash
python3 {{skill_path}}/scripts/extract_errorcode_docs.py "{{api_error_code_doc_path}}" "{{kit_name}}" "{{out_path}}/api_scan/error_code_doc"
```

输出目录为 `{out_path}/api_scan/error_code_doc/`。

如果脚本报错或未提取到文件，打印警告 `[harness] Warning: No error code docs extracted for kit '{{kit_name}}'`，继续执行后续步骤（不中断流程）。

**1.3** 运行预检脚本（声明侧确定性检测）：

```bash
python3 {{skill_path}}/scripts/precheck_rules.py "{{api_input}}" "{{out_path}}/api_scan/active_rules.json" -o "{{out_path}}/api_scan/precheck_findings.json"
```

预检脚本从 `impl_api.jsonl` 的 `api_declaration` 字段检测可由正则确定性判定的声明违规（当前覆盖规则 5.1.7.8：数组返回值不应联合 null/undefined）。输出 `precheck_findings.json`，格式与 `raw_findings.json` 一致。校验 subagent 合并时需同时合并此文件。预检发现声明违规的 API **仍继续进入 LLM 审计流程**（subagent 检查其他规则）。

---

### Phase B：Harness 调度

#### Step 2. 解析与分组

**2.1** 读取 `api_input` 文件路径，逐行解析为 JSON 对象。记录 API 条目总数 n。

**2.2** 分离 Format 2 API（`impl_api_name` 为空且有 `js_doc` 的条目），单独处理。

**2.3** 确定 API 总数：
- 若 n <= 30：进入 Direct 模式（Harness 自身执行审计，遵循 Step 3 中的审计方法论直接处理所有 API，然后跳到 Phase C）
- 若 n > 30：进入 Harness 模式，继续以下步骤

**2.4** 按 `group_strategy` 分组：

- **`module`**：按 `module_name` 字段分组。同模块 API 共享声明文件和实现目录，最大化代码读取局部性。单模块 > 200 API 时按 ~100 API 拆分子组。单模块 < 10 个API 时合并, 合并策略优先同 `impl_repo_path` 的相邻小模块, 若无`impl_repo_path`则按个数合并，保证合并后每组不低于20个API。
- **`fixed`**：按 `group_size`（默认 80）均匀切分。
- **`auto`**（默认）：先按 `module` 分组，若平均组大小在 20-200 之间则使用 `module` 策略，否则使用 `fixed` 策略。

**2.5** 创建输出目录并写入分组文件：

```bash
mkdir -p "{{out_path}}/api_scan/groups"
```

将每组 API 写入 `{out_path}/api_scan/groups/group_{i}.jsonl`（i 从 1 开始）。

**2.6** 断点续跑检查：扫描 `{out_path}/api_scan/subagent_results/status_{i}.json`，若存在且 `"status" == "completed"` 则标记该组已完成，跳过。

打印恢复摘要：`[harness] Found X completed groups, Y pending groups, Z total groups`

#### Step 3. 调度审计 Subagent

对每个未完成的组（pending groups），使用 Agent tool 调度审计 subagent。

**3.1** 读取 `{out_path}/api_scan/active_rules.json`，准备注入 subagent 的规则。

**3.2** 并行调度策略：
- 每次并行调度 `max_parallel` 个 Agent tool 调用
- 使用 `run_in_background: true` 和 `subagent_type: "general-purpose"`
- 每个完成的 subagent 写入 `status_{i}.json` 作为完成标记
- 必须等待前一批完成后，再进行调度下一批 pending groups，禁止提前启动下一批次subagent

**3.3** 为每个组构建 subagent prompt，严格遵循下方的「审计 Subagent Prompt 模板」。

**3.4** 失败处理：若某个 subagent 未能产生输出文件，重试一次。若仍失败，标记该组为 failed，继续处理其余组。

**3.5** 同时运行的subagent的个数不得大于max_parallel，禁止过度并行导致资源争抢或结果混乱。

#### Step 4. 等待审计完成

确认所有审计 subagent 已完成。检查每个 `status_{i}.json` 文件。统计：
- 成功组数
- 失败组数（报告失败组的编号）

如果全部组都失败，中止流程并报告错误。

#### Step 5. 调度校验 Subagent

使用 Agent tool 调度单个校验 subagent（`subagent_type: "general-purpose"`），传入校验 prompt（遵循下方的「校验 Subagent Prompt 模板」）。

校验 subagent 负责：
1. 合并所有 `raw_findings_{i}.json` → `raw_findings.json`；如果 `precheck_findings.json` 存在，同时读取并合并
2. 合并所有 `call_chains_{i}.json` → `api_call_chains.json`
3. 自校验合并后的 `raw_findings.json`
4. 运行 `classify_findings.py`
5. 生成最终输出文件
6. 运行 `validate_output.py`

如果校验 subagent 失败，harness 报告错误并终止。

---

### Phase C：完成确认

#### Step 6. 检查最终输出

确认以下文件存在于 `{out_path}/api_scan/`：
- `api_scan_findings.jsonl`
- `api_call_chains.json`
- `api_scan_summary.md`
- `validation_status.json`（由校验 subagent 写入，`status` 为 `passed`）

若 `validation_status.json` 显示验证失败，报告具体错误。

---

## 审计 Subagent Prompt 模板

模板文件：`{{skill_path}}/subagents/audit_subagent_prompt.md`

Harness 必须按此模板为每个 group 构造 prompt，将 `{{变量}}` 替换为实际值。

**变量替换规则**：

| 变量 | 替换为 |
|------|--------|
| `{{group_file_path}}` | `{out_path}/api_scan/groups/group_{i}.jsonl` |
| `{{repo_base}}` | 用户提供的 `repo_base` |
| `{{out_path}}` | 用户提供的 `out_path` |
| `{{batch_index}}` | 当前组编号 i |
| `{{api_count}}` | 当前组 API 数量 |
| `{{active_rules_path}}` | `{out_path}/api_scan/active_rules.json` |
| `{{skill_path}}` | skill 目录绝对路径 |
| `{{rules_count}}` | active_rules.json 中规则数量 |
| `{{RULES_SUMMARY}}` | 规则摘要（见下方构建方法） |
| `{{error_code_doc_path}}` | `{out_path}/api_scan/error_code_doc/`（仅当 `api_error_code_doc_path` 和 `kit_name` 均已提供且提取成功时；否则为空字符串） |

**构建规则摘要**：

读取 `active_rules.json`，对每条规则生成一行摘要：
```
- {id}: {description}
```

对规则 5.1.7.8，追加预检标注：
```
- 5.1.7.8: {description} [声明层面已由预检脚本检测，仅需检查实现层面：应返回空数组但返回了 null/undefined]
```

将所有规则摘要拼接后替换模板中的 `{{RULES_SUMMARY}}` 占位符。

---

## 校验 Subagent Prompt 模板

模板文件：`{{skill_path}}/subagents/validation_subagent_prompt.md`

**变量替换规则**：

| 变量 | 替换为 |
|------|--------|
| `{{out_path}}` | 用户提供的 `out_path` |
| `{{active_rules_path}}` | `{out_path}/api_scan/active_rules.json` |
| `{{skill_path}}` | skill 目录绝对路径 |
| `{{completed_groups}}` | 成功完成的组编号列表（如 `"1,2,3,5,6"`） |
| `{{failed_groups}}` | 失败的组编号列表（如 `"4,7"`） |

---

## Subagent 输出契约

### 审计 Subagent 输出

| 文件 | 路径 | 格式 |
|------|------|------|
| `raw_findings_{i}.json` | `{out_path}/api_scan/subagent_results/` | `{"findings": [...]}` 9 个英文字段 |
| `call_chains_{i}.json` | `{out_path}/api_scan/subagent_results/` | JSON array of call chain docs |
| `status_{i}.json` | `{out_path}/api_scan/subagent_results/` | `{"status":"completed","batch_index":N,"api_count":N,"findings_count":N,"duration_seconds":N}` |

### 校验 Subagent 输出

| 文件 | 路径 | 格式 |
|------|------|------|
| `raw_findings.json` | `{out_path}/api_scan/` | `{"findings": [...]}` 合并后 |
| `classified_findings.json` | `{out_path}/api_scan/` | 分类结果 |
| `api_scan_findings.jsonl` | `{out_path}/api_scan/` | 最终 13 字段 JSONL |
| `api_call_chains.json` | `{out_path}/api_scan/` | 完整调用链 |
| `api_scan_summary.md` | `{out_path}/api_scan/` | 汇总报告 |
| `validation_status.json` | `{out_path}/api_scan/` | `{"status":"passed/failed",...}` |

---

## 断点续跑协议

1. 调度前检查 `status_{i}.json` 是否存在且 `"status" == "completed"`
2. 已完成则跳过，打印：`[harness] Skipping group {i} (already completed)`
3. 若 `status_{i}.json` 存在但 `status` 不是 `completed`，或输出文件缺失/格式错误，视为未完成并重新调度
4. 启动时打印恢复摘要：`[harness] Found X completed, Y pending, Z total`

---

## 输出目录结构

```
{out_path}/api_scan/
  active_rules.json                # Phase A 产出
  precheck_findings.json           # Phase A Step 1.3 产出（声明侧预检结果，可选）
  error_code_doc/                  # 错误码参考文档（Phase A Step 1.2 产出，可选）
  groups/                          # 分组输入文件
    group_1.jsonl ... group_N.jsonl
  subagent_results/                # 审计 subagent per-group 输出
    raw_findings_1.json
    call_chains_1.json
    status_1.json
    raw_findings_2.json
    call_chains_2.json
    status_2.json
    ...
  raw_findings.json                # 合并后
  classified_findings.json         # classify 产出
  api_scan_findings.jsonl          # 最终 JSONL 输出
  api_call_chains.json             # 最终调用链
  api_scan_summary.md              # 汇总报告
  validation_status.json           # 校验状态
```

---

## 执行顺序（严格按序）

1. 规则加载 → `filter_rules.py`
1.3 运行预检脚本 → `precheck_rules.py`（声明侧确定性检测）
1.5 [如果提供 `api_error_code_doc_path` + `kit_name`] 提取错误码文档 → `extract_errorcode_docs.py`
2. 解析输入 → 分组 → 检查已完成组（断点续跑）
3. [Format 2 API] 调度映射 subagent 查找 impl 映射
4. [n <= 30] Direct 模式：Harness 自身执行审计（Step 3 中的审计方法论）→ 生成 raw_findings.json → 跳到 Step 7
   [n > 30] Harness 模式：
5. 并行调度审计 subagent（每组一个，max_parallel 并发）
6. 等待所有审计 subagent 完成
7. 调度校验 subagent（合并 + 自校验 + classify + 生成输出 + validate）
8. 检查 `validation_status.json`，确认通过

---

## 关键参考文件

| 文件 | 用途 |
|------|------|
| `config/rule.json` | 唯一规则来源 |
| `subagents/audit_subagent_prompt.md` | 审计 subagent prompt 模板 |
| `subagents/validation_subagent_prompt.md` | 校验 subagent prompt 模板 |
| `references/call_chain_analysis_guide.md` | 调用链分析方法（subagent 按需读取） |
| `references/common_error_codes.md` | 通用错误码参考（201/202/203/401/801） |
| `references/LESSONS_LEARNED.md` | 历史审计经验 |
| `references/output_schema.md` | 输出结构定义 |
| `references/problem_patterns_checklist.md` | 常见问题模式（40 项） |
| `templates/api_scan_summary.md` | 汇总报告模板 |
| `scripts/extract_errorcode_docs.py` | 提取 Kit 错误码文档 |
| `scripts/precheck_rules.py` | 声明侧确定性预检脚本 |

---

## 注意事项

1. **Harness 自身不处理 API 数据**，仅负责分组、调度、编排
2. **config/rule.json 是唯一规则来源**
3. **每个审计 subagent 处理独立的一组 API**，组间无交叉
4. **校验 subagent 单独运行**，不与审计 subagent 并行
5. **subagent 间不共享状态**，仅通过文件系统通信
6. **合并时检查去重**（rule_id + affected_apis）
7. **`call_chains` 必须覆盖所有输入 API**（含无发现的 API）
8. **每个审计 subagent 限制在 20-200 个 API 范围内**
9. **调用链分析限制 2 层**：API → Level 1 → Level 2，停止
10. **影响的错误码** 必须是开发者通过 BusinessError.code 收到的数值错误码
11. **成功码（0）不是错误码**，在影响的错误码中排除
12. 如果输入量较大，审计 subagent 每处理 10 个 API 将中间结果刷新到文件
13. 仅报告实际违反规则的问题，不得报告遵守规则的情况
14. 无需考虑时间，避免因时间过长而着急输出结果

---

## 禁止事项

- 禁止输出评分、权重等评分类字段
- 禁止按 Kit 聚合输出（这是按 API 的审计）
- 禁止使用 GetDoc.py 或抓取文档
- 禁止使用 extract_js_api.py 或 extract_c_api.py（用户直接提供 API 列表）
- 禁止跳过 validate_output.py 验证步骤
- 禁止忽略验证错误
- 禁止追踪超过 2 层的外部函数调用
- 禁止 Harness 直接审计大量 API（>30 个必须使用 subagent 模式）
