# kit-measurement Skill 经验总结

本文档总结了在审计 HarmonyOS/OpenHarmony Kit API 规范性过程中的经验教训和最佳实践。

## 更新日期

- 2026-04-01: 改造为规则驱动审计模式（v5.0）
- 2026-02-23: communication_netmanager_base 审核经验（v4.0）
- 2026-02-13: multimedia_audio_framework 审核经验（v3.0）

---

## v4.0 经验总结 (2026-02-23)

### 1. 必须使用脚本提取 API 清单

**问题**: 手动分析 API 会遗漏大量 API，导致统计不准确

**对比数据**:

| 分析方式 | JS/NAPI API 数量 | NDK API 数量 |
|---------|-----------------|-------------|
| 手动分析 | 92+ 个 | 20+ 个 |
| 脚本提取 | **109 个** | **29 + 20 类型** |
| 差异 | +17 个 (18%) | +9 个 (45%) |

**经验**:
- 手动分析会遗漏同步版本 API（如 `getDefaultNetSync`）
- 手动分析会遗漏 observer 方法（`on`/`off`）
- 必须使用 `extract_js_api.py` 和 `extract_c_api.py` 脚本
- 脚本提取的 JSON 文件应保存到 out_path 供后续分析

**脚本使用**:
```bash
python extract_js_api.py {{kit_path}} --js-api-header-root {{js_api_header_root}} --kit-name {{kit_name}} -o {{out_path}}/js_api.json
python extract_c_api.py {{kit_path}} --c-api-header-root {{c_api_header_root}} --kit-name {{kit_name}} -o {{out_path}}/c_api.json
```

### 2. 成功码（0）不是错误码

**问题**: 在错误码统计中错误地将成功码（0）计入

**修正**:
- ❌ 错误: "暴露给开发者的错误码共 13 个（包含 0）"
- ✅ 正确: "暴露给开发者的错误码共 12 个（不含成功码）"

**经验**:
- 成功码（通常为 0）表示操作成功，不是错误
- 错误码表格中不应包含成功码
- 统计时需明确排除成功码

### 3. JS/NAPI 层错误码必须输出详细表格

**问题**: 之前的报告对 JS/NAPI 层错误码描述过于简略

#### 3.1 JS/NAPI 层错误

| 错误码名称 | 值 | 错误消息原文 | 说明 |
|-----------|---|-------------|------|
| [示例] | [值] | [错误消息原文] | [说明] |

### 4. communication_netmanager_base 审核数据

**API 统计**:

| 模块 | API 数量 |
|------|---------|
| net.connection | 65 |
| net.policy | 24 |
| net.statistics | 20 |
| **JS/NAPI 总计** | **109** |
| NDK API | 29 |
| NDK 类型 | 20 |
| **总计** | **158** |

**错误码统计**:

| 统计项 | 数量 |
|--------|------|
| Native 层错误码 | 66+ |
| 暴露给开发者的错误码（不含 0） | 12 |
| Native → JS 映射 | 32 |
| 错误消息映射 | 90+ |
| 错误码转字符串问题 | 18 处 |

### 5. 错误码转字符串问题的分布

**问题位置统计**:

| 文件 | 数量 |
|------|------|
| module_template.h | 4 处 |
| napi_common.cpp | 4 处 |
| statistics_observer_wrapper.cpp | 4 处 |
| policy_observer_wrapper.cpp | 6 处 |
| **总计** | **18 处** |

**影响**:
- 所有使用这些模板的 API 都会返回字符串类型错误码
- 违反 HarmonyOS API 规范
- 与其他 Kit 行为不一致

---

## v3.0 经验总结 (2026-02-13)

### 1. 文档下载与处理

**问题**: 文档 URL 直接访问时无法获取有效内容，需要使用专门的爬取工具

**解决方案**:
- 使用 skill 目录下的 `scripts/GetDoc.py` 爬取华为开发者文档
- 保存到项目目录下：`{project_path}/api_doc/` 和 `{project_path}/error_code_doc/`
- 使用 `-w 3` 参数控制爬取线程数

**命令示例**:
```bash
cd /path/to/skills/audit-error-codes/scripts
python3 GetDoc.py "https://developer.huawei.com/consumer/cn/doc/harmonyos-references/audio-arkts" -o /project/path/api_doc -f markdown -w 3
python3 GetDoc.py "https://developer.huawei.com/consumer/cn/doc/harmonyos-references/audio-arkts-errcode" -o /project/path/error_code_doc -f markdown -w 3
```

**经验**:
- GetDoc.py 会自动爬取关联页面，一次调用可下载完整文档集
- API 文档通常包含多个子页面（AudioRenderer, AudioCapturer 等）
- 错误码文档通常包含 5-10 个模块特定错误码

### 2. 错误码架构理解

**multimedia_audio_framework 的错误码架构**:

1. **Native 层错误码** (`audio_errors.h`):
   - 使用位移计算基准值
   - 错误码为负数（如 -62980096）
   - 定义了 52 个错误码

2. **NAPI 层错误码** (`napi_audio_error.h`):
   - 使用正数错误码（如 6800101）
   - 定义了 11 个错误码
   - 包含模块特定错误码和通用错误码

3. **错误码映射机制** (`napi_audio_error.cpp`):
   - `GetMessageByCode()` 函数负责映射
   - 使用 switch-case 匹配 Native 错误码
   - 未匹配的错误码全部映射为 6800301

**关键发现**:
- 只有 9/52 (17.3%) 的 Native 错误码有映射
- 82.7% 的错误码映射为通用系统错误
- 开发者在 JS 层只能看到 10 种错误码，而非 Native 层定义的 52 种

### 3. 三份报告的解耦设计

**问题**: 之前的版本将所有内容混合在一个报告中，导致报告过长且职责不清

**解决方案**: 分离为三个独立报告

1. **ERROR_CODE_ANALYSIS_REPORT.md**:
   - 专注于错误码定义和问题发现
   - 列出具体的代码位置和问题类型
   - 不提供修复建议

2. **API_CALL_CHAIN_AND_EXCEPTION_REPORT.md**:
   - 专注于 API 调用链路分析
   - 追踪从 JavaScript 到 Native 层的完整调用路径
   - 记录每一层的异常分支触发点

3. **DOC_CONSISTENCY_REPORT.md**:
   - 专注于文档与代码的一致性对比
   - 验证错误码定义是否一致
   - 分析错误码映射覆盖率

**经验**:
- 三份报告让读者可以快速定位到关心的内容
- 每份报告都有明确的职责和格式
- 便于不同角色的开发者按需查阅

### 4. 问题类型的精确定义

**关键区别**: 避免使用模糊的问题描述

| 问题类型 | 正确定义 | 误用示例 |
|---------|----------|----------|
| 错误码转字符串 | `std::to_string(code)` 传递给 `napi_throw_error` | "错误码类型错误" |
| 错误码精度降低 | 三元操作符将不同失败映射到同一错误码 | "错误码丢失" |
| 异常分支未抛出 | 检测到错误只记录日志 | "错误处理不完善" |

**经验**:
- 精确定义问题类型，便于分类和统计
- 使用具体代码模式作为问题识别依据
- 避免使用"大量"、"多处"等模糊描述

### 5. 文档一致性分析的原则

**关键原则：从开发者视角出发**

- ✅ **应该对比**: C++ 错误码 → JS/NAPI 错误码 → 暴露给开发者的错误码
- ❌ **不应该对比**: C++ 内部实现错误码与文档定义（开发者看不到）

**分析维度**:

1. **文档定义的错误码总数**: 从错误码文档提取
2. **代码定义的错误码总数**: 从代码头文件提取
3. **已映射的错误码**: 统计映射函数中的条目
4. **未映射的错误码**: 差值

**经验**:
- 只关注最终暴露给 API 使用者的错误码
- Native 内部的错误码映射是关键
- 必须有实际对比结果才能下一致性结论

### 6. 报告模板化

**问题**: 每次生成报告时格式不一致，需要重复编写相同结构

**解决方案**: 在 `templates/` 目录下提供三个报告模板

1. **ERROR_CODE_ANALYSIS_REPORT_TEMPLATE.md**
2. **API_CALL_CHAIN_AND_EXCEPTION_REPORT_TEMPLATE.md**
3. **DOC_CONSISTENCY_REPORT_TEMPLATE.md**

**经验**:
- 模板使用占位符（如 [Kit 名称]、[N] 个）便于替换
- 保持格式一致性，便于自动化处理
- 报告模板与 SKILL.md 解耦，避免 SKILL.md 过长

### 7. SKILL.md 简化原则

**问题**: 之前的 SKILL.md 包含大量详细内容和示例，超过 800 行

**简化原则**:
1. **核心步骤**: 只保留 10 个主要步骤
2. **问题模式**: 列出 4-5 个核心问题类型
3. **报告格式**: 简要说明格式要求，具体格式放入 templates
4. **参考链接**: 将详细内容移到 references 目录

**经验**:
- SKILL.md 作为快速参考，不应包含所有细节
- 详细的使用示例放在 EXAMPLES.md
- 经验总结放在 LESSONS_LEARNED.md
- 报告模板放在 templates 目录

### 8. 量化要求的明确化

**精确数量要求**:
- ❌ 避免: "大量调用"、"多处"、"多个"
- ✅ 使用: "268次"、"5处"、"2处"、"3个文件"

**函数调用统计**:
- ❌ 避免: "该函数被大量调用"
- ✅ 使用: "`ThrowExceptionError` 函数被调用 268 次"

**经验**:
- 精确数字让问题影响更清晰
- 便于后续问题追踪和修复验证
- 避免模糊描述导致的误解

---

## 具体技术发现

### 🔴 严重问题模式

#### 1. 错误码转字符串

**特征代码**:
```cpp
napi_throw_error(env, (std::to_string(code)).c_str(), messageValue.c_str());
```

**检测方法**:
```bash
grep -rn "napi_throw_error.*to_string" frameworks/
grep -rn "std::to_string.*errCode" frameworks/
```

**影响**:
- JavaScript 层接收字符串类型错误码
- 违反 HarmonyOS API 规范
- 开发者需要额外类型转换

**正确方法**:
```cpp
napi_create_error(env, nullptr, message);
napi_create_int32(env, code, &codeValue);
napi_set_named_property(env, result, "code", codeValue);
napi_throw(env, result);
```

#### 2. 错误码精度降低

**特征代码**:
```cpp
return GetAudioTime(timestamp, base) ? SUCCESS : ERR_OPERATION_FAILED;
```

**影响**:
- 不同失败原因返回同一错误码
- 开发者无法区分具体问题
- 降低错误诊断能力

**正确方法**:
```cpp
if (!GetAudioTime(timestamp, base)) {
    if (timestamp < 0) {
        return ERR_INVALID_PARAM;
    } else {
        return ERR_OPERATION_FAILED;
    }
}
return SUCCESS;
```

#### 3. 错误码映射不完整

**特征代码**:
```cpp
std::string NapiAudioError::GetMessageByCode(int32_t &code)
{
    std::string errMessage;
    switch (code) {
        case NAPI_ERR_INVALID_PARAM:
        case ERR_INVALID_PARAM:
            code = NAPI_ERR_INVALID_PARAM;
            break;
        default:
            code = NAPI_ERR_SYSTEM;  // 82.7% 的错误码进入这里
            break;
    }
    return errMessage;
}
```

**影响**:
- 43/52 个 Native 错误码映射为通用的系统错误
- 开发者只能看到 10 种错误码
- 无法区分文档中定义的多种错误场景

### ⚠️ 中等问题模式

#### 1. 硬编码错误码值

**特征代码**:
```cpp
static const std::set<uint32_t> ERROR_CODES = {62980096, 62980105, ...};
```

**影响**:
- 维护困难
- 代码可读性差
- 容易遗漏或重复

**正确方法**:
```cpp
static const std::set<uint32_t> ERROR_CODES = {
    ERR_IMAGE_GET_DATA_ABNORMAL,
    ERR_IMAGE_INVALID_PARAMETER,
    ...
};
```

---

## 最佳实践

### 1. API 清单收集

- ✅ 必须使用 extract_js_api.py 和 extract_c_api.py 脚本
- ✅ 脚本提取的 JSON 文件保存到 out_path
- ❌ 避免手动分析 API，会遗漏大量内容

### 2. 错误码表格输出

- ✅ 输出详细表格，包含所有字段
- ✅ 区分暴露给开发者的错误码和内部错误码
- ✅ 成功码（0）不计入错误码统计
- ❌ 避免使用"详见源码"等省略描述

### 3. 报告解耦

- 每份报告专注一个方面
- 避免在一个报告中混合所有内容
- 使用模板保持格式一致

### 4. 精确量化

- 使用具体数字
- 明确函数调用范围
- 避免模糊描述

### 5. 开发者视角

- 关注暴露给 API 使用者的错误码
- 不过度关注 C++ 内部实现
- 验证文档与 JS 层暴露错误码的一致性

### 6. 工具使用优化

- 使用 Explore 子代理进行深度分析
- 并行执行多个搜索任务
- 使用 GetDoc.py 处理文档下载

### 7. 文档处理流程

1. 下载文档保存到项目目录
2. 读取并解析文档内容
3. 提取错误码定义和描述
4. 与代码中的错误码进行对比
5. 生成文档一致性报告

---

## 已知限制

1. **文档格式**: GetDoc.py 目前只支持 Markdown 格式
2. **动态代码**: 无法分析运行时生成的代码
3. **第三方库**: 错误码可能来自第三方库，不在 kit 内
4. **性能**: 大型 kit 的 thorough 模式可能需要 10+ 分钟

---

*最后更新: 2026-02-23*
*基于 communication_netmanager_base kit 审核经验*
