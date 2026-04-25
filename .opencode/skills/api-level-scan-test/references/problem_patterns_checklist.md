# API问题模式校验清单

> 本清单汇总自多个审核技能的实际分析案例，用于指导对各个API从开发者调用最外层入口到具体实现函数代码的全链路问题检测。
> 清单中的问题模式具有普适性，适用于HarmonyOS/OpenHarmony API的全面审核。

---

## 一、命名规范类问题

### 1. 命名不符合业务场景
**问题说明**: API命名未能准确表达核心功能，或与业界惯例不一致。

**案例**:
```typescript
// 反例：命名模糊，无法判断功能
function process(): void;
function handle(): void;

// 正例：命名清晰
function encodeAudio(): void;
function decodeVideo(): void;
```

**检查点**:
- [ ] API名称是否准确表达核心功能
- [ ] 是否与业界通用命名一致
- [ ] 是否与同模块其他接口保持风格一致

---

### 2. 使用否定表达式命名
**问题说明**: 接口命名使用否定形式，增加开发者认知负担。

**案例**:
```typescript
// 反例：否定表达式
function disableFeature(): void;
function isNotReady(): boolean;

// 正例：肯定表达式
function enableFeature(): void;
function isReady(): boolean;
```

**检查点**:
- [ ] 是否存在 disable/hide/stop/close/deactivate/remove 等否定词
- [ ] 是否可以转换为肯定表达
- [ ] 注意双重否定（如 isNotDisabled）

---

### 3. 使用非英语命名
**问题说明**: API命名使用拼音或其他非英语语言。

**案例**:
```typescript
// 反例：拼音命名
function chuangjianPlayer(): AVPlayer;
function bofang(): void;
```

**检查点**:
- [ ] 所有API名称是否为英语
- [ ] 是否存在拼音或中文字符

---

### 4. 语法词法错误
**问题说明**: API命名存在拼写错误或词性搭配不当。

**案例**:
```typescript
// 反例：拼写错误
function createPlayr(): void;  // Player拼写错误

// 反例：词性搭配不当
function player(): void;  // 动词位置使用名词
```

**检查点**:
- [ ] 单词拼写是否正确
- [ ] 动词是否使用原形
- [ ] 词性搭配是否合理（动词+名词结构）

---

### 5. 对仗词使用不准确
**问题说明**: API命名中未正确使用对仗词，导致接口不完整或语义混乱。

**常见对仗词**:
- add/remove, increase/decrease, open/close
- begin/end, insert/delete, show/hide
- create/destroy, lock/unlock, get/set
- start/stop, min/max, next/previous

**案例**:
```typescript
// 反例：有add无remove
function addListener(): void;
// 缺少 function removeListener(): void;

// 反例：对仗词不匹配
function beginTask(): void;
function finishTask(): void;  // 应为 endTask
```

**检查点**:
- [ ] 是否存在有get无set或反之
- [ ] 对仗词是否正确匹配
- [ ] 接口设计是否考虑对称性

---

### 6. 缩写使用不合理
**问题说明**: 使用非业界通用缩写或缩写格式不规范。

**业界通用缩写**:
- Information → Info, Configuration → Config
- Application → App, Identifier → ID/Id
- Document → Doc, Number → Num
- String → Str, Object → Obj

**案例**:
```typescript
// 反例：自定义缩写
function getUsrNm(): string;  // 应为 getUserName

// 正例：通用缩写
function getAppInfo(): AppInfo;
function getConfig(): Config;
```

**检查点**:
- [ ] 缩写是否为业界通用
- [ ] 驼峰命名首字母是否大写
- [ ] 全大写缩写是否使用正确

---

### 7. 函数名使用名词（非声明式风格）
**问题说明**: 普通函数使用名词命名，应使用动词或动宾结构。

**案例**:
```typescript
// 反例：普通函数使用名词
function user(): User;

// 正例：使用动词
function getUser(): User;
function createUser(): User;

// 例外：声明式UI组件/Builder模式可使用名词
@Component
struct Button { }  // 正例：声明式UI
```

**检查点**:
- [ ] 普通函数是否以动词开头
- [ ] 是否为声明式UI或Builder模式（例外情况）
- [ ] 动词是否使用原形

---

### 8. 数据类型名称使用动词
**问题说明**: 类、接口、枚举等数据类型名称使用动词，应使用名词。

**案例**:
```typescript
// 反例：类型名使用动词
interface Run { }
class Execute { }

// 正例：类型名使用名词
interface Runner { }
class Executor { }
```

**检查点**:
- [ ] 类名是否为名词
- [ ] 接口名是否为名词
- [ ] 枚举名是否为名词

---

### 9. 单复数与语义不匹配
**问题说明**: 函数名/参数名的单复数形式与返回值/实际含义不匹配。

**案例**:
```typescript
// 反例：返回数组但使用单数
function getItem(): Item[];  // 应为 getItems

// 反例：返回单个对象但使用复数
function getFirstItem(): Item;  // 正确，但若函数名为 getItems 则错误
```

**检查点**:
- [ ] 返回单个对象是否使用单数名词
- [ ] 返回数组是否使用复数名词
- [ ] 集合类型关注整体时是否使用单数

---

### 10. 使用有争议的命名
**问题说明**: 使用可能引起争议或违反规范的命名。

**需避免的词汇**:
- master/slave → 使用 primary/secondary
- blacklist/whitelist → 使用 blocklist/allowlist
- 宗教相关词汇、个人姓名、侮辱性词汇
- 其他公司品牌名、其他操作系统专有术语

**检查点**:
- [ ] 是否包含 master/slave
- [ ] 是否包含 blacklist/whitelist
- [ ] 是否包含其他公司品牌名
- [ ] 是否包含其他OS专有术语

---

## 二、接口设计类问题

### 11. 参数顺序不合理
**问题说明**: 参数排列不符合逻辑关系或使用习惯。

**参数排序原则**:
1. 核心参数（用户ID、文件路径、URL）在前
2. 必选参数在可选参数前
3. 输入参数在输出参数前
4. 保持与类似接口一致性

**案例**:
```typescript
// 反例：可选参数在必选参数前
function query(id?: number, name: string): void;

// 正例：必选参数在前
function query(name: string, id?: number): void;
```

**检查点**:
- [ ] 核心参数是否在前
- [ ] 必选参数是否在可选参数前
- [ ] 参数顺序是否便于记忆和使用

---

### 12. 模块划分不合理
**问题说明**: 模块职责不单一，耦合度过高。

**案例**:
```typescript
// 反例：一个模块处理多种不相关功能
class MediaManager {
    playAudio(): void;
    playVideo(): void;
    downloadFile(): void;  // 不应属于媒体模块
    connectNetwork(): void;  // 不应属于媒体模块
}
```

**检查点**:
- [ ] 模块是否只处理一类相关功能
- [ ] 内部方法是否有逻辑联系
- [ ] 模块依赖是否过多

---

## 三、同步异步规范类问题

### 13. 同步方法通过返回值返回执行状态
**问题说明**: 同步方法返回布尔值或错误码表示执行是否成功，而非抛出异常。

**案例**:
```typescript
// 反例：通过返回值表示成功/失败
function createUser(name: string): boolean {
    if (!name) return false;  // 应抛出异常
    return true;
}

// 正例：抛出异常
function createUser(name: string): User {
    if (!name) throw new BusinessError(401, "Parameter error");
    return new User(name);
}
```

**检查点**:
- [ ] 同步方法是否返回布尔值表示成功/失败
- [ ] 同步方法是否返回null表示失败
- [ ] 是否使用异常而非特殊返回值

---

### 14. 与业界同名的同步API提供不必要的异步版本
**问题说明**: 业界广泛使用的同步API（如console.log, on/off）提供了不必要的异步版本。

**检查点**:
- [ ] API名称和功能是否与业界知名API一致
- [ ] 业界是否只提供同步版本
- [ ] 是否提供了不必要的异步版本

---

### 15. 执行时长不确定的场景提供同步方式
**问题说明**: 网络请求、IO操作、用户交互等执行时长受外界影响的场景提供了同步API。

**必须只提供异步的场景**:
- 网络请求
- 定位、WiFi扫描、蓝牙扫描
- 用户交互
- 后台长时间任务

**案例**:
```typescript
// 反例：网络请求提供同步版本
function fetchSync(url: string): Response;  // 不应有同步版本

// 正例：只提供异步版本
function fetch(url: string): Promise<Response>;
```

**检查点**:
- [ ] 网络请求API是否只提供异步
- [ ] 定位等传感器API是否只提供异步
- [ ] 用户交互API是否只提供异步

---

### 16. 耗时操作未优先提供异步方式
**问题说明**: 图像/视频解码、大文件IO等耗时操作未优先提供异步API。

**应优先提供异步的场景**:
- 图像/视频解码
- 大文件读写
- 复杂IPC通信

**检查点**:
- [ ] IO操作是否优先提供异步
- [ ] 图像/视频解码是否优先提供异步
- [ ] 是否以同步为补充而非主要方式

---

## 四、错误码定义类问题

### 17. 异常定义不完整
**问题说明**: 可能的错误场景未在设计阶段定义对应的错误码。

**常见遗漏场景**:
- 系统接口未配对202错误码
- 需权限接口未配对201错误码
- 查询接口未考虑"未找到"场景
- 有参数约束的接口未声明相应错误码

**案例**:
```typescript
// 反例：查询接口未定义"未找到"异常
function queryUser(id: number): Promise<User>;
// 应添加 @throws {BusinessError} 查询用户不存在

// 反例：系统接口未声明202
@systemapi
function systemFunction(): void;
// 应添加 @throws {BusinessError} 202
```

**检查点**:
- [ ] 系统接口是否声明202
- [ ] 权限接口是否声明201
- [ ] 查询接口是否考虑"未找到"
- [ ] 异常是否正交（不重叠）

---

### 18. 错误码码值不符合规范
**问题说明**: 错误码值不符合HarmonyOS设计规范。

**通用错误码规范**:
| 错误码 | 含义 | 使用场景 |
|-------|------|---------|
| 201 | 权限校验失败 | 带@permission标签的API |
| 202 | 系统API权限校验失败 | 带@systemapi标签的API |
| 203 | 企业管理策略禁止 | - |
| 401 | 参数检查失败 | 无需声明 |
| 801 | 设备不支持此API | - |
| 804 | 模拟器不支持 | 无需声明 |

**业务自定义错误码格式**: SXXXXX（S=SysCap编号，XXXXX=5位自定义码）

**案例**:
```typescript
// 反例：自定义错误码格式错误
@throws {BusinessError} 123 - Custom error  // 应为 SXXXXX 格式

// 反例：401被显式声明
@throws {BusinessError} 401 - Parameter error  // 401无需声明
```

**检查点**:
- [ ] 通用错误码是否正确使用
- [ ] 自定义错误码是否符合SXXXXX格式
- [ ] 401/804是否被误声明

---

### 19. 错误码语义不一致
**问题说明**: 同一错误码在不同场景下语义不同，或不同错误码表达相同语义。

**案例**:
```typescript
// 反例：同一错误码语义混乱
// 场景1
@throws {BusinessError} 5400101 - No memory
// 场景2
@throws {BusinessError} 5400101 - Service unavailable
```

**检查点**:
- [ ] 同一错误码语义是否一致
- [ ] 不同错误码是否有不同语义
- [ ] 错误码与错误原因是否匹配

---

## 五、错误码实现类问题

### 20. 错误码转字符串类型（严重）
**问题说明**: Native层通过 `napi_throw_error` 抛出错误时，将错误码转换为字符串，导致JS层收到字符串类型错误码而非数字。

**特征代码**:
```cpp
// 反例：错误码转字符串
napi_throw_error(env, std::to_string(errCode).c_str(), "error message");
napi_create_string_utf8(env, std::to_string(ret).c_str(), NAPI_AUTO_LENGTH);
napi_create_error(env, std::to_string(code).c_str(), errorMessage);
```

**影响**: JavaScript层接收到字符串类型错误码（如"401"）而非数字（401），违反API规范。

**案例**:
```cpp
// frameworks/js/napi/featureAbility/data_ability/include/napi_rdb_error.h:47
napi_throw_error((env), std::to_string((error)->GetCode()).c_str(),
                 (error)->GetMessage().c_str());
```

**检查点**:
- [ ] Native层是否使用 `std::to_string()` 转换错误码
- [ ] `napi_throw_error` 第三个参数是否为字符串形式的数字
- [ ] JavaScript层接收到的错误码类型是否为number

---

### 21. 实现与声明不一致
**问题说明**: 代码中实际抛出的错误码未在JS Doc/接口声明中定义，或抛出场景与声明不匹配。

**案例**:
```typescript
// 声明
@throws {BusinessError} 401 - Parameter error
function readFile(path: string): string;

// 实现
function readFile(path: string): string {
    if (!fs.exists(path)) {
        throw new BusinessError(5400101, "File not found");  // 未在声明中定义
    }
}
```

**检查点**:
- [ ] 所有抛出的错误码是否非空
- [ ] 所有抛出的错误码是否在声明中
- [ ] 抛出场景是否与声明场景匹配

---

### 22. 错误码信息精度降低（严重）
**问题说明**: 多个不同的失败原因被映射到同一个错误码，导致开发者无法区分具体原因。

**特征代码**:
```cpp
// 反例：使用三元操作符简化错误判断
return decodeRet ? SUCCESS : ERR_IMAGE_DATA_UNSUPPORT;
return GetAudioTime(timestamp, base) ? SUCCESS : ERR_OPERATION_FAILED;
```

**典型案例**:
```cpp
// services/appmgr/src/app_mgr_service_inner.cpp:6903
return isCallingPerm ? ERR_OK : ERR_PERMISSION_DENIED;
// 使用三元操作符导致不同错误原因映射到同一错误码
```

**多对一映射问题统计**:
- 16000050错误码映射了53+个不同的Native错误码
- 201错误码映射了5种不同的权限拒绝场景
- 3301200错误码包含了多个不同类型的错误原因

**检查点**:
- [ ] 是否使用三元操作符简化错误判断
- [ ] 是否存在多对一的错误码映射
- [ ] 不同失败原因是否能被开发者区分

---

### 23. 异常分支未抛出错误码
**问题说明**: 异常情况只记录日志但未向上层抛出错误，导致错误丢失。

**特征代码**:
```cpp
// 反例：异常分支未抛出错误
if (ret != OK) {
    LOGE("operation failed");
    return;  // 错误丢失，应抛出错误码
}
```

**检查点**:
- [ ] 异常分支是否只记录日志
- [ ] 异常分支是否正确向上传递错误
- [ ] 是否存在静默返回的情况

---

### 24. 非标准错误码使用
**问题说明**: 使用负数错误码或其他非标准错误码值。

**特征代码**:
```cpp
// 反例：使用负数错误码
constexpr int ERR_CUSTOM = -1024;
#define NAPI_ERR_NO_WINDOW (-1)
#define NAPI_ERR_NO_PERMISSION (-100)
#define NAPI_ERR_INNER_DATA (-101)
```

**检查点**:
- [ ] 是否使用负数错误码
- [ ] 错误码值是否符合规范
- [ ] NDK层与JS层错误码值是否一致

---

### 25. 硬编码错误码
**问题说明**: 直接使用数字作为错误码，而非常量定义。

**特征代码**:
```cpp
// 反例：硬编码错误码
napi_throw_error(env, "123456", "error message");
return {123456, "error message"};

// 正例：使用常量
napi_throw_error(env, ERR_CUSTOM_FORMAT, "error message");
```

**检查点**:
- [ ] 是否直接使用数字作为错误码
- [ ] 是否使用常量定义

---

### 26. 错误码映射不完整
**问题说明**: Native层大量错误码被映射为通用错误码，导致信息丢失。

**特征代码**:
```cpp
// 反例：大量错误码进入default分支
default:
    code = NAPI_ERR_SYSTEM;  // 大量Native错误码被映射为通用系统错误码
    break;
```

**映射覆盖率参考**:
- 理想覆盖率：>90%
- 可接受覆盖率：70%-90%
- 需改进覆盖率：<70%

**案例**:
```
communication_netmanager_base:
- Native层错误码: 66+ 个
- 暴露给开发者错误码: 12 个（不含成功码）
- 映射覆盖率: 48.5%  // 需改进
```

**检查点**:
- [ ] Native错误码映射覆盖率是否足够
- [ ] 是否存在大量错误进入default分支
- [ ] 通用错误码是否被滥用

---

### 27. 异步接口同步抛出异常
**问题说明**: 异步接口（Promise/AsyncCallback）在非参数校验场景下同步抛出异常。

**案例**:
```typescript
// 反例：异步接口同步抛出非参数错误
async function fetchData(url: string): Promise<Data> {
    if (!url) throw new BusinessError(401, "...");  // 参数校验可同步抛出
    // 以下应在异步任务中抛出
    if (!networkAvailable) throw new BusinessError(5400103, "...");  // 错误
}
```

**检查点**:
- [ ] 参数校验外的错误是否在异步任务中抛出
- [ ] 是否通过回调或Promise返回错误
- [ ] 是否在主线程同步抛出业务错误

---

## 六、错误信息类问题

### 28. 错误信息为空或无效
**问题说明**: 抛出异常时错误消息为空或无效。

**特征代码**:
```cpp
// 反例：错误信息为空
if (param == nullptr) {
    ThrowError(ERR_INVALID_PARAM, "");  // 错误信息不能为空
    return;
}
```

**检查点**:
- [ ] 错误消息是否非空
- [ ] 错误消息是否有效（非空格、非占位符）

---

### 29. 错误信息过于泛泛
**问题说明**: 错误消息过于笼统，无法帮助开发者定位问题。

**案例**:
```cpp
// 反例：错误信息过于笼统
ThrowError(ERR_FAILED, "Operation failed");
ThrowError(ERR_ERROR, "Error occurred");
ThrowError(ERR_INTERNAL, "Internal error");

// 正例：错误信息具体
ThrowError(ERR_FILE_NOT_FOUND, "File not found: /path/to/file");
ThrowError(ERR_PERMISSION_DENIED, "Permission denied: need ohos.permission.READ_MEDIA");
```

**检查点**:
- [ ] 错误消息是否过于笼统
- [ ] 是否包含定位信息
- [ ] 是否能帮助开发者采取行动

---

### 30. 错误信息误导
**问题说明**: 错误消息与实际错误原因不符，误导开发者。

**案例**:
```cpp
// 反例：错误信息误导
if (serviceUnavailable) {
    ThrowError(ERR_NO_MEMORY, "No memory");  // 实际是服务不可用，非内存问题
}
```

**检查点**:
- [ ] 错误消息是否与错误原因匹配
- [ ] 是否存在语义不一致

---

### 31. 相同错误码不同分支错误消息重复
**问题说明**: 同一错误码在不同分支使用完全相同的错误消息，导致无法区分具体场景。

**案例**:
```cpp
// 反例：不同场景使用相同错误消息
if (fileNotFound) {
    ThrowError(5400101, "Operation failed");
}
if (permissionDenied) {
    ThrowError(5400101, "Operation failed");  // 相同消息，无法区分
}
```

**检查点**:
- [ ] 同一错误码不同分支是否有可区分的消息
- [ ] 是否能根据消息判断具体失败原因

---

### 32. 错误消息缺少定位信息
**问题说明**: 错误消息未包含参数名、文件路径等定位信息。

**案例**:
```cpp
// 反例：缺少定位信息
ThrowError(401, "Parameter error");

// 正例：包含定位信息
ThrowError(401, "Parameter error. Mandatory parameter 'url' is left unspecified.");
ThrowError(401, "The type of 'callback' must be AsyncCallback<AVPlayer>.");
```

**检查点**:
- [ ] 参数错误是否指明具体参数
- [ ] 是否包含必要的上下文信息
- [ ] 开发者能否快速定位问题

---

## 七、调用链分析类问题

### 33. 同步API静默失败（最严重）
**问题说明**: 同步API在Native层失败时返回 `undefined`，开发者收不到任何错误信息。

**特征代码**:
```cpp
// audio_player_napi.cpp
napi_value AudioPlayerNapi::CreateAudioPlayer(napi_env env, napi_callback_info info)
{
    napi_value result = nullptr;
    status = napi_new_instance(env, constructor, 0, nullptr, &result);
    if (status != napi_ok) {
        napi_get_undefined(env, &result);
        return result;  // 静默返回 undefined
    }
    return result;  // 构造函数失败也是 undefined
}
```

**开发者视角**:
```typescript
let player = media.createAudioPlayer();
// 如果失败，player = undefined
// 没有错误码，没有错误消息，无法定位问题！
```

**检查点**:
- [ ] 同步API失败时是否返回undefined
- [ ] 是否存在静默失败的代码路径
- [ ] 开发者能否收到错误信息

---

### 34. 构造函数失败未检测
**问题说明**: 构造函数失败后未通过 `CheckCtorResult` 机制检测并转换为错误。

**正确模式（异步API）**:
```cpp
// frameworks/js/common/common_napi.cpp
void MediaAsyncContext::CheckCtorResult(napi_env env, napi_value &result,
                                        MediaAsyncContext *ctx, napi_value &args)
{
    if (ctx->ctorFlag) {
        void *instance = nullptr;
        if (napi_unwrap(env, result, &instance) != napi_ok || instance == nullptr) {
            ctx->errFlag = true;
            CommonNapi::CreateError(env, MSERR_EXT_API9_NO_MEMORY,
                "The instance or memory has reached the upper limit...", result);
            args = result;
        }
    }
}
```

**检查点**:
- [ ] 构造函数API是否有错误检测机制
- [ ] 是否使用 `CheckCtorResult` 或类似机制
- [ ] 构造失败是否能正确传递给开发者

---

### 35. 调用链异常分支未覆盖
**问题说明**: API调用链上的异常分支未正确映射到开发者可接收的错误码。

**完整调用链分析**:
```
ArkTS/JS 暴露入口
    ↓
NAPI 注册函数
    ↓
NAPI 桥接函数
    ↓
Native 业务实现函数
    ↓
下游服务调用
```

**每个节点需检查**:
- 异常分支触发条件
- 触发后返回的错误码
- 错误信息来源
- 是否正确向上层传递

**检查点**:
- [ ] 调用链每个节点的异常分支是否识别
- [ ] 异常是否正确向上传递
- [ ] 是否存在错误丢失的情况

---

### 36. 服务层失败模式未识别
**问题说明**: 只分析到Native层，未追踪到服务层识别所有可能的失败模式。

**常见服务层失败原因**:
1. 服务不可用（服务未运行或崩溃）
2. 实例限制（超过最大并发实例数）
3. 权限拒绝（调用者缺少所需权限）
4. IPC失败（与服务通信失败）

**代码路径示例**:
```
PlayerFactory::CreatePlayer()
  → PlayerImpl::Init()
    → MediaServiceFactory::CreatePlayerService()
      → MediaClient::CreatePlayerService()
        → 检查服务可用性
        → 从mediaProxy_请求服务stub
        → 创建PlayerClient包装器
```

**检查点**:
- [ ] 是否追踪到服务层
- [ ] 服务层所有失败模式是否识别
- [ ] 服务层错误是否正确映射

---

## 八、文档一致性类问题

### 37. 错误码与文档不一致
**问题说明**: 代码中定义的错误码未在官方文档中记录，或与文档描述不符。

**典型案例**:
- 文档缺失错误码定义（有的缺失17个特有错误码）
- 66个代码中定义的错误码未在官方文档中列出
- 文档与代码错误消息不一致

**检查点**:
- [ ] 代码中所有开发者可见的错误码是否在文档中
- [ ] 文档错误码值与代码是否一致
- [ ] 文档错误消息与代码是否一致

---

### 38. JS Doc声明但未实际抛出
**问题说明**: JS Doc中声明了错误码，但代码中实际不会抛出该错误。

**案例**:
```typescript
// JS Doc声明
@throws {BusinessError} 5400101 - No memory
function createMediaSourceWithUrl(): MediaSource;

// 实际实现
function createMediaSourceWithUrl(): MediaSource {
    // 所有失败场景都静默返回 undefined
    // 开发者永远收不到 5400101 错误
}
```

**检查点**:
- [ ] JS Doc声明的错误码是否在代码中实际抛出
- [ ] 是否存在声明但未实现的错误码

---

### 39. JS Doc消息与代码消息不匹配
**问题说明**: JS Doc中的错误消息与代码实际返回的消息不一致。

**案例**:
```
JS Doc消息: "No memory"
代码实际消息: "The instance or memory has reached the upper limit, please recycle background playback"
```

**问题**:
1. 开发者在日志中搜索JS Doc消息找不到任何内容
2. JS Doc未提供足够的指导信息

**检查点**:
- [ ] JS Doc消息是否与代码消息一致
- [ ] JS Doc消息是否足够具体
- [ ] JS Doc是否包含处理建议

---

### 40. 跨语言错误码不一致
**问题说明**: 同功能接口在不同语言侧（ArkTS/NAPI/NDK）的错误码集合不一致。

**检查点**:
- [ ] 同功能接口各语言侧错误码集合是否一致
- [ ] Native错误原因映射到JS错误码时是否丢失信息
- [ ] 同一功能不同语言侧的错误消息语义是否一致

---

## 九、通用错误码使用检查清单

### 必须使用的通用错误码

| 错误码 | 触发条件 | 是否需要声明 |
|-------|---------|------------|
| 201 | 带@permission标签的API权限校验失败 | 需声明 |
| 202 | 带@systemapi标签的API权限校验失败 | 需声明 |
| 203 | 企业管理策略禁止 | 需声明 |
| 401 | 参数校验失败（数量/类型） | **无需声明** |
| 801 | 设备不支持此API | 需声明 |
| 804 | 模拟器不支持 | **无需声明** |

---

## 十、问题优先级定义

| 优先级 | 问题类型 | 影响 |
|-------|---------|-----|
| **P0（严重）** | 同步API静默失败、错误码转字符串、多对一映射 | 开发者完全无法定位问题 |
| **P1（高）** | 异常定义不完整、异常分支未抛出、错误信息为空 | 开发者难以定位问题 |
| **P2（中）** | 错误码与文档不一致、错误信息过于笼统 | 影响开发者体验 |
| **P3（低）** | 命名规范、参数顺序 | 影响API规范性 |

---

## 附录：问题统计参考

基于84个部件/Kit的分析报告统计：

| 问题类型 | 问题数量 | 占比 |
|---------|---------|-----|
| 错误码信息模糊（多对一映射） | 84 | 52.5% |
| 错误码String类型 | 37 | 23.1% |
| 错误码与文档不一致 | 25 | 15.6% |
| 错误码值非法 | 9 | 5.6% |
| 异常分支未返回错误码 | 4 | 2.5% |

**总计**: 160个问题

---

*本清单将持续更新，基于更多实际分析案例完善问题模式定义。*
