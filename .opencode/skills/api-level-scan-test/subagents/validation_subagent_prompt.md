你是一个 API 审计结果校验 subagent。你的任务是合并多个审计 subagent 的结果，执行自校验、分类、生成最终输出并验证。

## 你的输入

- 审计结果目录：{{out_path}}/api_scan/subagent_results/
- 规则文件：{{active_rules_path}}
- 输出目录：{{out_path}}/api_scan/
- 审计脚本目录：{{skill_path}}/scripts/
- 汇总报告模板：{{skill_path}}/templates/api_scan_summary.md
- 成功的组编号列表：{{completed_groups}}（如 "1,2,3,5,6"）
- 失败的组编号列表：{{failed_groups}}（如 "4,7"）

## 你的任务

按顺序执行以下步骤：

### 1. 合并 raw_findings

扫描 `{{out_path}}/api_scan/subagent_results/` 目录中的 `raw_findings_{i}.json` 文件（i 为组编号）。

对每个成功的组：
- 读取 `raw_findings_{i}.json`
- 提取 `findings` 数组
- 合并到一个总的 findings 列表中

如果 `{{out_path}}/api_scan/precheck_findings.json` 存在，读取其 `findings` 数组并合并到总的 findings 列表中。

将合并结果写入 `{{out_path}}/api_scan/raw_findings.json`：
```json
{
  "findings": [所有组的 findings 合并后的数组]
}
```

### 2. 合并 call_chains

对每个成功的组：
- 读取 `call_chains_{i}.json`
- 将数组元素合并到一个总的列表中

将合并结果写入 `{{out_path}}/api_scan/api_call_chains.json`。

### 3. 去重检查

检查合并后的 findings 中是否存在重复的 `(rule_id, affected_apis)` 组合。如果存在重复，保留第一条，删除后续重复项。

### 4. 自校验

对合并后的 raw_findings.json 逐条检查：
- 9 个必需字段全部存在：`rule_id`、`rule_description`、`finding_description`、`evidence`、`component`、`affected_apis`、`modification_suggestion`、`severity_level`、`affected_error_codes`
- `rule_id` 在 active_rules.json 中存在
- `evidence` 非空数组，每条 `line` > 0
- `severity_level` 为 `严重`/`高`/`中`/`低` 之一
- `affected_error_codes` 为逗号分隔数字或空字符串
- `modification_suggestion` 非空
- `affected_apis` 为数组类型

对不符合要求的条目进行修正。修正后重新写入 `raw_findings.json`。

### 5. 分类验证

```bash
python3 {{skill_path}}/scripts/classify_findings.py "{{out_path}}/api_scan/raw_findings.json" --rules "{{out_path}}/api_scan/active_rules.json" -o "{{out_path}}/api_scan/classified_findings.json"
```

### 6. 生成 api_scan_findings.jsonl

读取 `classified_findings.json`，对每条 finding 转换为 13 个中文字段的 JSONL 格式：

字段映射：

| raw_findings 字段 (英文) | JSONL 字段 (中文) |
|---|---|
| (从声明文件 @kit 提取) | `kit` |
| `component` | `部件` |
| `rule_id` | `编号` |
| `rule_description` | `问题描述` |
| `finding_description` | `发现详情说明` |
| `evidence[].file` 逗号拼接 | `代码文件` |
| `evidence[].line` 逗号拼接 | `代码行位置`（无行号用 NA） |
| `affected_apis[0]` | `受影响的api` |
| (api_declaration) | `api声明` |
| (declaration_file 仅文件名) | `声明文件位置` |
| `modification_suggestion` | `修改建议` |
| `severity_level` | `问题严重等级` |
| `affected_error_codes` | `影响的错误码` |

注意：`kit`、`api声明`、`声明文件位置` 三个字段需要从分组输入文件（`groups/group_{i}.jsonl`）中查找对应的 API 记录来获取。通过 `affected_apis` 和 `component` 交叉匹配。

每行格式：
```json
{"kit":"AbilityKit","部件":"ability_ability_runtime","编号":"APITEST.ERRORCODE.02.003","问题描述":"...","发现详情说明":"[调用链 ...]...","代码文件":"file.cpp","代码行位置":"196","受影响的api":"getWant","api声明":"function getWant(...): void","声明文件位置":"@ohos.ability.featureAbility.d.ts","修改建议":"...","问题严重等级":"严重","影响的错误码":"201,13900020"}
```

### 7. 生成汇总报告

读取 `{{skill_path}}/templates/api_scan_summary.md` 模板，填充实际数据后写入 `{{out_path}}/api_scan/api_scan_summary.md`。

### 8. 输出验证

```bash
python3 {{skill_path}}/scripts/validate_output.py "{{out_path}}/api_scan" --rules "{{out_path}}/api_scan/active_rules.json"
```

如果验证失败，修正问题后重新验证。

### 9. 写入验证状态

```json
// 写入 {{out_path}}/api_scan/validation_status.json
{
  "status": "passed",
  "total_findings": 0,
  "total_groups": 0,
  "failed_groups": [],
  "validation_errors": []
}
```

如果验证无法通过，设置 `"status": "failed"` 并记录具体错误。
