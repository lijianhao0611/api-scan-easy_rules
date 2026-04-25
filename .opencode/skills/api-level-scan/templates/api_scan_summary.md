# API 级别审计汇总报告

**审计日期**: {{audit_date}}
**规则来源**: config/rule.json
**API 输入**: {{total_api_count}} 条 API 记录

## 审计概览

| 指标 | 数值 |
|------|------|
| 已审计 API 数量 | {{total_api_count}} |
| 有发现的 API 数量 | {{api_with_findings}} |
| 总发现数 | {{total_findings}} |
| 有效规则数 | {{total_rules}} |

## 严重等级分布

| 严重等级 | 数量 | 占比 |
|---------|------|------|
| 严重 | {{serious_count}} | {{serious_pct}}% |
| 高 | {{high_count}} | {{high_pct}}% |
| 中 | {{medium_count}} | {{medium_pct}}% |
| 低 | {{low_count}} | {{low_pct}}% |

## 按 API 汇总

| API 名称 | 模块 | 发现数 | 最严重等级 | 影响的错误码 |
|---------|------|-------|-----------|------------|
{{#each api_summary}}
| {{api_name}} | {{module_name}} | {{finding_count}} | {{worst_severity}} | {{error_codes}} |
{{/each}}

## 按规则汇总

| 编号 | 问题描述 | 受影响 API 数 |
|------|---------|-------------|
{{#each rule_summary}}
| {{rule_id}} | {{rule_description}} | {{affected_api_count}} |
{{/each}}

## 关键发现

{{#each key_findings}}
- **[{{severity}}]** {{api_name}}: {{finding_summary}}
{{/each}}
