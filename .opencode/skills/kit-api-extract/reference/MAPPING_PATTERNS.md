# NAPI/ANI 映射模式知识库

本文件记录 HarmonyOS/OpenHarmony 中 JS API 到 C++ 实现的各种映射模式。
每次使用 kit-api-extract skill 后，若发现新模式，应追加到此文件。

---

发现新模式时，按以下格式在下方添加：

```markdown
    ### 模式N：{模式名称}

    **描述**：{简要描述映射机制}

    **正则表达式**：{可用于 grep/搜索的正则}

    **代码结构**：
    ```cpp
    {示例代码}
    ```
    **关键文件位置**：{通常出现的目录路径模式}
```

---

### 模式1：DECLARE_NAPI_FUNCTION 宏注册

**描述**：最传统的 NAPI 函数注册方式，通过宏将 JS 方法名映射到 C++ 函数。通常出现在 `napi_property_descriptor` 数组中。

**正则表达式**：`DECLARE_NAPI_FUNCTION\s*\(\s*"([^"]+)"\s*,\s*(\w+)`

**代码结构**：
```cpp
napi_property_descriptor properties[] = {
    DECLARE_NAPI_FUNCTION("getWant", NAPI_PAGetWant),
    DECLARE_NAPI_FUNCTION("startAbility", NAPI_PAStartAbility),
    DECLARE_NAPI_FUNCTION("getBundleInfo", GetBundleInfo),
};
```

**关键文件位置**：`frameworks/js/napi/<module>/` 或 `interfaces/kits/napi/src/`

---

### 模式2：napi_create_function 动态注册

**描述**：通过 `napi_create_function` 动态创建 NAPI 函数并挂载到 exports 对象，不使用宏。

**正则表达式**：`napi_create_function\s*\(\s*(?:env|Env)\s*,\s*"([^"]+)"\s*,\s*[^,]+,\s*(\w+)`

**代码结构**：
```cpp
NAPI_CALL(env, napi_create_function(env, "isCanceled", NAPI_AUTO_LENGTH, Task::IsCanceled, NULL, &isCanceledFunc));
NAPI_CALL(env, napi_set_named_property(env, exports, "isCanceled", isCanceledFunc));
```

**关键文件位置**：`frameworks/js/napi/` 下各子模块

---

### 模式3：nm_modname 模块名注册

**描述**：NAPI 模块通过 `.nm_modname` 字段注册模块名，将 JS 的 `@ohos.xxx.yyy` 映射到具体代码仓。通常出现在 `native_module.cpp` 或 `*_module.cpp` 中。

**正则表达式**：`\.nm_modname\s*=\s*"([^"]+)"`

**代码结构**：
```cpp
static napi_module _module = {
    .nm_version = 1,
    .nm_flags = 0,
    .nm_filename = nullptr,
    .nm_modname = "ability.featureAbility",
    .nm_register_func = FeatureAbilityInit,
    ...
};
```

**用途**：用于模块→代码仓映射（Phase 2 map 阶段）

---

### 模式4：napi_define_class 类注册

**描述**：通过 `napi_define_class` 注册 JS 类，类的方法在 `napi_property_descriptor` 中声明。常见于面向对象的 API（如 DeviceManager、AVPlayer）。

**正则表达式**：`napi_define_class\s*\([^;]+Constructor`

**代码结构**：
```cpp
napi_property_descriptor desc[] = {
    DECLARE_NAPI_FUNCTION("getDeviceName", GetDeviceName),
    DECLARE_NAPI_FUNCTION("authenticateDevice", AuthenticateDevice),
};
NAPI_CALL(env, napi_define_class(env, "DeviceManager", NAPI_AUTO_LENGTH, Constructor, nullptr,
    sizeof(desc) / sizeof(desc[0]), desc, nullptr, &result));
```

**关键文件位置**：`interfaces/kits/js/` 或 `interfaces/kits/js4.0/`

---

### 模式5：napi_define_properties 批量导出

**描述**：通过 `napi_define_properties` 将一组 NAPI 属性/方法批量绑定到 exports 对象。常与 `DECLARE_NAPI_FUNCTION` 或 `DECLARE_NAPI_GETTER` 配合使用。

**正则表达式**：`napi_define_properties\s*\(`

**代码结构**：
```cpp
napi_property_descriptor desc[] = {
    DECLARE_NAPI_FUNCTION("function1", Func1),
    DECLARE_NAPI_FUNCTION("function2", Func2),
};
napi_define_properties(env, exports, sizeof(desc) / sizeof(desc[0]), desc);
```

**关键文件位置**：`frameworks/js/napi/` 下各子模块

---

### 模式6：on/off 事件分发模式

**描述**：多个 JS API（如 onAdd/offAdd/onUpdate 等）并非独立注册的 NAPI 函数，而是通过通用的 `on(type, callback)` / `off(type, callback?)` 入口分发。`type` 参数区分不同事件类型，内部维护独立的 listener 列表。

**正则表达式**：`DECLARE_NAPI_FUNCTION\s*\(\s*"(on|off)"\s*,\s*(Register|Unregister)\)`

**代码结构**：
```cpp
napi_property_descriptor properties[] = {
    DECLARE_NAPI_FUNCTION("on", Register),
    DECLARE_NAPI_FUNCTION("off", Unregister),
};

napi_value Register(napi_env env, napi_callback_info info) {
    // 解析 type 参数
    if (type == "add") { addListeners.push_back(callback); }
    else if (type == "update") { updateListeners.push_back(callback); }
    else if (type == "remove") { removeListeners.push_back(callback); }
}
```

**JS API 到 C++ 的映射**：
- `onAdd(cb)` → `on("add", cb)` → `Register` (type="add")
- `offAdd(cb)` → `off("add", cb)` → `Unregister` (type="add")

**关键文件位置**：`interfaces/kits/js/bundle_monitor/` 等事件监听模块

---

### 模式7：BindNativeFunction / BindNativeFunctionInObj（OHOS 特有封装）

**描述**：OHOS 提供的 `BindNativeFunction` 和 `BindNativeFunctionInObj` 辅助函数，封装了 `napi_define_properties` 调用。不使用 DECLARE_NAPI_FUNCTION 宏。

**正则表达式**：`BindNativeFunction\s*\(\s*(?:env|context)\s*,\s*(?:exports|obj)\s*,\s*"([^"]+)"\s*,\s*(\w+)`

**代码结构**：
```cpp
BindNativeFunction(env, exports, "register", JsContinuationManager::Register);
BindNativeFunction(env, exports, "unregister", JsContinuationManager::Unregister);
```

**关键文件位置**：`interfaces/kits/napi/` 或 `frameworks/js/napi/` 下各模块

---

### 模式8：纯 JS/ABC 模块（无 C++ nm_register_func）

**描述**：部分模块（如 InsightIntentExecutor、ApplicationStateChangeCallback）是纯 JS/ArkTS 类，通过嵌入的 .js 或 .abc 字节码注册，没有 C++ 的 nm_register_func。其方法在 JS 层定义，C++ 侧通过函数名字符串反射调用。

**识别特征**：
- `native_module.cpp` 中无 `nm_register_func` 或使用空/默认注册
- 模块目录下有 `.js` 文件
- C++ 侧有 `JsXxx` 类通过 `JS_FUNC_NAME` 数组按名称调用 JS 方法

**代码结构**：
```cpp
// native_module.cpp - 无 nm_register_func
static napi_module _module = {
    .nm_modname = "app.ability.InsightIntentExecutor",
    // 无 nm_register_func - 纯 JS 模块
};

// C++ 侧通过函数名调用 JS 方法
const std::vector<std::string> JS_FUNC_NAME_FOR_MODE = {
    "onExecuteInUIAbilityForegroundMode",
    "onExecuteInUIAbilityBackgroundMode",
    ...
};
```

**关键文件位置**：`frameworks/js/napi/insight_intent/` 等生命周期回调模块

### 模式9：CallObjectMethod 生命周期回调（反射调用 JS 方法）

**描述**：生命周期回调 API（如 onAcceptWant、onNewProcessRequest、onAuth 等）不在 C++ 侧通过 NAPI 宏注册。相反，C++ 通过 `napi_get_named_property` + `napi_call_function` 或 `CallObjectMethod` 按方法名字符串反射调用 ETS/JS 层的回调函数。模块通常为纯 JS/ABC 模块（无 nm_register_func）。

**正则表达式**：`CallObjectMethod\s*\(\s*"(on\w+)"` 或 `napi_get_named_property\s*\([^,]+,\s*\w+,\s*"(on\w+)"`

**代码结构**：
```cpp
// C++ 侧通过名字字符串调用 JS 方法
napi_value method = nullptr;
napi_get_named_property(env, obj, "onAcceptWant", &method);
napi_call_function(env, obj, method, argc, argv, &result);

// 或使用封装的 CallObjectMethod
auto result = CallObjectMethod("onAuth", argv, ARGC_TWO);
```

**JS API 到 C++ 的映射**：
- `onAcceptWant(want)` → C++ `CallAcceptOrRequestSync("onAcceptWant")` → `js_ability_stage.cpp`
- `onAuth(proxy, data)` → C++ `CallObjectMethod("onAuth")` → `js_agent_extension.cpp`

**关键文件位置**：`frameworks/native/appkit/` 和 `frameworks/js/napi/app/` 下的生命周期模块

---

### 模式10：ETS+ANI 绑定（ani_native_function）

**描述**：部分新模块（如 autoStartupManager、abilityManager 的事件监听）使用 ETS+ANI 双层架构。模块既有 NAPI 层（通过 BindNativeFunction 注册 on/off 通用入口），也有 ANI/ETS 层通过 `ani_native_function` 注册。运行时根据 VM 类型选择 NAPI 或 ANI 实现。

**正则表达式**：`ani_native_function\s*\(`

**代码结构**：
```cpp
// NAPI 层（兼容模式）
BindNativeFunction(env, exportObj, "on", JsAutoStartupManager::On);

// ANI 层（新架构）
ani_native_function aniFunc = {
    .name = "on",
    .func = reinterpret_cast<void*>(JsAutoStartupManager::On),
};
```

**关键文件位置**：`frameworks/js/napi/ability_auto_startup_manager/`、`frameworks/js/napi/ability_manager/`

---

### 模式11：Taihe IDL 绑定模式

**描述**：通过 `.taihe` IDL 文件定义接口，由 Taihe 框架自动生成绑定代码。使用 `TH_EXPORT_CPP_API_xxx` 宏导出实现函数。不使用传统 NAPI 注册机制。

**正则表达式**：`TH_EXPORT_CPP_API_\w+` 或 `.taihe` 文件中的 `interface` 定义

**代码结构**：
```taihe
// ohos.app.ability.continueManager.taihe
interface ContinueManager {
    void onPrepareContinue(Context context, AsyncCallback<ContinueResultInfo> callback);
    void offPrepareContinue(Context context, AsyncCallback<ContinueResultInfo>? callback);
}
```

```cpp
// 实现文件 ohos.app.ability.continueManager.impl.cpp
TH_EXPORT_CPP_API_OnPrepareContinueInner(params) {
    // 实现代码
    AniContinueManager::OnContinueStateCallback(...);
}
```

**关键文件位置**：`interfaces/taihe/` 目录下的 `.taihe` 文件和 `src/` 下的 `.impl.cpp` 文件

---

### 模式12：纯 JS 实现模块（NAPI 模块 + JS 门面）

**描述**：部分模块（如 dataUriUtils、sendableContextManager）在 NAPI 层注册了模块入口（有 nm_modname），但具体的 API 实现在 .js 文件中。JS 文件作为门面，部分方法直接用 JS 实现（纯字符串操作等），部分通过 `requireInternal` 调用底层 C++ 实现。

**正则表达式**：`.js` 文件中直接定义函数，或 `requireInternal` 调用

**代码结构**：
```javascript
// ability_data_uri_utils.js — 纯 JS 实现
function attachId(uri, id) {
    return uri + '/' + id;
}

// sendable_context_manager.js — 混合模式
const internal = requireInternal('sendable_context_manager');
function convertFromContext(context) {
    return internal.convertFromContext(context);
}
```

**关键文件位置**：`frameworks/js/napi/` 下各模块中的 `.js` 文件

---

### 模式13：双层 __context_impl__ 注入模式

**描述**：某些纯 JS/ABC 模块（如 InsightIntentContext）在 JS 层定义接口，但实际 C++ 实现对象通过 `__context_impl__` 属性由框架内部注入。JS 层通过 `this.__context_impl__.methodName()` 调用 C++ 实现，C++ 侧通过 `BindNativeFunction` 在注入的对象上注册方法。

**正则表达式**：`__context_impl__\.`

**代码结构**：
```javascript
// insight_intent_context.js
class InsightIntentContext {
    setReturnModeForUIAbilityForeground(returnMode) {
        this.__context_impl__.setReturnModeForUIAbilityForeground(returnMode);
    }
}
```

**关键文件位置**：`frameworks/js/napi/insight_intent_context/` 等 Context 类模块


### 模式14：JSI NativeModule Bridge（ArkUI 组件属性绑定）

**描述**：ArkUI 组件的属性 API（如 width、height、onClick 等）不通过传统 NAPI 的 nm_modname 注册，而是通过 JSI (JS Interface) 层的 `arkts_native_*_bridge.cpp` 文件进行绑定。每个组件有对应的 bridge 文件和 modifier 文件。

**正则表达式**：`arkts_native_(\w+)_bridge\.cpp`

**代码结构**：
```cpp
// arkts_native_text_bridge.cpp — JSI 绑定入口
ArkUI_NativeModuleAPI* module = GetArkUINodeModifiers();
module->textModifier->setTextFont(node, value);
```

**映射链路**：
```
.d.ts 声明 → arkts_native_*_bridge.cpp (JSI绑定)
          → node_*_modifier.h/cpp (Framework声明+实现)
          → frameworks/core/components_ng/pattern/*/ (业务逻辑)
```

**关键文件位置**：
- Bridge: `arkui_ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/nativeModule/`
- Modifier: `arkui_ace_engine/frameworks/core/interfaces/native/node/`

---

### 模式15：UIContext JS Bridge（requireNapi 加载模式）

**描述**：`@ohos.arkui.UIContext` 是一个 JS 桥接类，通过 `globalThis.requireNapi('xxx')` 加载底层 NAPI 模块。

**正则表达式**：`globalThis\.requireNapi\(['"]([^'"]+)['"]\)`

**代码结构**：
```javascript
class Font {
    constructor(instanceId) {
        this.ohos_font = globalThis.requireNapi('font');
    }
    registerFont(options) {
        __JSScopeUtil__.syncInstanceId(this.instanceId_);
        this.ohos_font.registerFont(options);
    }
}
```

**关键文件位置**：`arkui_ace_engine/frameworks/bridge/declarative_frontend/engine/jsUIContext.js`

---

### 模式16：ANI 双层绑定（window_window_manager 模式）

**描述**：window_window_manager 仓库中的 display、screen、PiPWindow 模块使用 ANI 而非传统 NAPI 进行绑定。

**正则表达式**：`ANI_Constructor\s*\(|Namespace_BindNativeFunctions\s*\(`

**关键文件位置**：`window_window_manager/interfaces/kits/ani/`



### 模式17：自定义模板方法注册 (Method<>/GetProperty<>/GetSetProperty<>)

**描述**：ArkGraphics3D 不使用标准 DECLARE_NAPI_FUNCTION 宏，而是通过自定义模板函数指针将 JS 方法名映射到 C++ 类成员函数。每个模板接收 NAPI 上下文类型、类名和成员函数指针，在 napi_define_class 的属性描述符数组中注册。

**正则表达式**：`Method<.*,\s*(\w+),\s*&\w+::(\w+)>|GetProperty<.*,\s*(\w+),\s*&\w+::(\w+)>|GetSetProperty<.*,\s*(\w+)`

**代码结构**：
```cpp
napi_property_descriptor descs[] = {
    Method<NapiApi::FunctionContext<>, SceneJS, &SceneJS::GetNodeByPath>("getNodeByPath"),
    GetProperty<NapiApi::Array, SceneJS, &SceneJS::GetAnimations>("animations"),
    GetSetProperty<NapiApi::Object, SceneJS, &SceneJS::GetEnvironment, &SceneJS::SetEnvironment>("environment"),
};
napi_define_class(env, "Scene", NAPI_AUTO_LENGTH, SceneJS::Constructor, ...);
```

**关键文件位置**：`graphic_graphic_3d/kits/js/src/` 下各 `*JS.cpp` 文件，模板定义在 `kits/js/include/` 下的辅助头文件中

---

### 模式18：napi_default_jsproperty + FromJs() 数据持有者模式

**描述**：几何定义类(CustomGeometry, CubeGeometry 等)的 getter/setter 属性全部声明为 `napi_default_jsproperty`，C++ 层不拦截属性访问。数据在 JS 引擎中存储，仅在 createGeometry 调用时通过 `FromJs()` 静态方法一次性读取和验证。这是一种"延迟消费"模式。

**正则表达式**：`napi_default_jsproperty.*\n.*napi_default_jsproperty` 或 `FromJs\s*\(.*napi_env.*napi_value`

**代码结构**：
```cpp
napi_property_descriptor desc[] = {
    {"vertices", nullptr, nullptr, nullptr, nullptr, nullptr, napi_default_jsproperty, nullptr},
    {"indices", nullptr, nullptr, nullptr, nullptr, nullptr, napi_default_jsproperty, nullptr},
};
napi_define_class(env, "CustomGeometry", NAPI_AUTO_LENGTH, defaultCtor, ...);

static std::unique_ptr<Geometry> FromJs(napi_env env, napi_value obj) {
    auto vertices = GetArrayProperty<Vec3>(env, obj, "vertices");
    auto indices = GetArrayProperty<int>(env, obj, "indices");
}
```

**关键文件位置**：`graphic_graphic_3d/kits/js/src/geometry_definition/` 下各文件

---

### 模式19：MakeTROMethod / DeclareMethod 多态注册模式

**描述**：ArkGraphics3D 中根据类的继承层级使用不同的方法注册辅助宏：
- `MakeTROMethod` — 用于继承自 TrueRootObject 的类(NodeImpl, SceneResourceImpl)
- `DeclareMethod/DeclareGetSet` — 用于继承自 BaseObject 的类(AnimationJS, ShaderJS, EffectJS)
- `ECMethod` — 用于非 BaseObject 的 Container 类(NodeContainerJS, EffectsContainerJS)

**正则表达式**：`MakeTROMethod\s*\(|DeclareMethod\s*\(|ECMethod\s*\(`

**代码结构**：
```cpp
// MakeTROMethod — TrueRootObject 子类
napi_property_descriptor nodeDescs[] = {
    MakeTROMethod(NodeImpl, GetNodeByPath),
};

// DeclareMethod — BaseObject 子类
static DeclareMethod<AnimationJS>(env, proto, "start", &AnimationJS::Start);

// ECMethod — Container 类
ECMethod("append", NodeContainerJS::Append),
```

**关键文件位置**：`graphic_graphic_3d/kits/js/src/` 下各 `*JS.cpp` 文件

### 模式20：JSI 静态方法绑定（ArkUI 早期组件绑定）

**描述**：Web 等早期 ArkUI 组件不使用 `arkts_native_*_bridge.cpp`（模式14），而是通过 `JSWeb::JSBind()` + `JSClass<JSWeb>::StaticMethod()` / `CustomMethod()` 进行 JSI 绑定。这是 ArkUI 框架中较早期的组件属性/事件注册方式。每个组件有对应的 `js_*.cpp` 文件，通过 `JSBind` 静态方法注册所有属性和事件。

**正则表达式**：`JSClass<JS\w+>::(StaticMethod|CustomMethod)\s*\(` 或 `JS\w+::JSBind\s*\(`

**代码结构**：
```cpp
// js_web.cpp — Web 组件绑定
void JSWeb::JSBind(Bridge& bridge)
{
    JSClass<JSWeb>::StaticMethod("webviewController", &JSWeb::CreateWebviewController);
    JSClass<JSWeb>::StaticMethod("onSslErrorEventReceive", &JSWeb::JsOnSslErrorEventReceive);
    JSClass<JSWeb>::CustomMethod("javaScriptProxy", &JSWeb::JsJavaScriptProxy);
    ...
}

// js_web_controller.cpp — WebController 绑定
void JSWebController::JSBind()
{
    JSClass<JSWebController>::StaticMethod("runJavaScript", &JSWebController::RunJavaScript);
    ...
}
```

**映射链路**：
```
.d.ts/ets 声明 → js_*.cpp (JSI 绑定，JSClass::StaticMethod/CustomMethod)
              → *_model.h / *_model_ng.h (Framework 声明)
              → frameworks/core/components_ng/pattern/*/ (业务逻辑)
```

**关键文件位置**：`arkui_ace_engine/frameworks/bridge/declarative_frontend/jsview/js_web.cpp`

---

### 模式21：DECLARE_NAPI_FUNCTION_WRITABLE（可写属性函数注册）

**描述**：Camera Kit 使用 `DECLARE_NAPI_FUNCTION_WRITABLE` 宏注册方法，与标准 `DECLARE_NAPI_FUNCTION` 类似但注册后的属性描述符为可写（writable）。常见于需要在运行时动态替换的 NAPI 方法。

**正则表达式**：`DECLARE_NAPI_FUNCTION_WRITABLE\s*\(\s*"([^"]+)"\s*,\s*(\w+)`

**代码结构**：
```cpp
napi_property_descriptor camera_input_props[] = {
    DECLARE_NAPI_FUNCTION_WRITABLE("open", Open),
    DECLARE_NAPI_FUNCTION_WRITABLE("close", Close),
    DECLARE_NAPI_FUNCTION("release", Release),
};
```

**关键文件位置**：`multimedia_camera_framework/frameworks/js/camera_napi/src/input/camera_input_napi.cpp`

---

### 模式22：DECLARE_NAPI_STATIC_FUNCTION（静态方法注册）

**描述**：用于注册类的静态方法（不需要实例化即可调用）。Camera Kit 的 `CameraPicker.pick()` 使用此模式。

**正则表达式**：`DECLARE_NAPI_STATIC_FUNCTION\s*\(\s*"([^"]+)"\s*,\s*(\w+)`

**代码结构**：
```cpp
napi_property_descriptor camera_picker_static_props[] = {
    DECLARE_NAPI_STATIC_FUNCTION("pick", Pick),
    DECLARE_NAPI_PROPERTY("PickerResult", ...),
};
```

**关键文件位置**：`multimedia_camera_framework/frameworks/js/camera_napi/src/picker/camera_picker_napi.cpp`

---

### 模式23：双层 NAPI 动态加载架构（camera_napi_base + camera_napi_ex）

**描述**：Camera Kit 使用了双层 NAPI 架构。基础层 `camera_napi_base` 提供公共 API，扩展层 `camera_napi_ex` 通过动态加载机制提供系统级 API（`@systemapi` 标记）。`camera_napi_ex` 由 `dynamic_loader/camera_napi_ex_manager.cpp` 和 `camera_napi_ex_proxy.cpp` 管理加载。

**识别特征**：
- 同一代码仓有两个 NAPI 目录：`camera_napi/` 和 `camera_napi_for_sys/`
- BUILD.gn 中有 `camera_napi_base` 和 `camera_napi_ex` 两个独立 target
- `camera_napi_ex` 的 Init 函数在运行时通过动态加载注册
- 扩展层的类名通常带 `ForSys` 后缀

**代码结构**：
```cpp
// camera_napi/src/native_module_ohos_camera.cpp — 基础层
static napi_value Export(napi_env env, napi_value exports) {
    CameraManagerNapi::Init(env, exports);  // 公共 API
    CameraSessionNapi::Init(env, exports);  // 公共 session
}

// camera_napi_for_sys/src/mode/profession_session_napi.cpp — 扩展层
// 通过动态加载注册系统级 API
napi_value ProfessionSessionNapi::Init(napi_env env, napi_value exports) {
    // 注册专业模式等系统级接口
}
```

**关键文件位置**：
- 基础层：`multimedia_camera_framework/frameworks/js/camera_napi/`
- 扩展层：`multimedia_camera_framework/frameworks/js/camera_napi_for_sys/`
- 动态加载：`multimedia_camera_framework/frameworks/js/camera_napi/src/dynamic_loader/`

---

### 模式24：MergeAllDesc 合并描述符模式（NFC 标签多类导出）

**描述**：NFC 标签模块中，各标签子类（NfcATag、NfcBTag、NfcFTag、NfcVTag、IsoDepTag 等）的方法通过 `MergeAllDesc` 函数将基类 `g_baseClassDesc` 的方法与各子类的描述符合并，实现多类方法到单一 NAPI 模块的导出。基类方法对应 tagSession 模块，子类方法对应 nfctech 模块。

**正则表达式**：`MergeAllDesc\s*\(`

**代码结构**：
```cpp
// nfc_napi_tag.cpp
napi_property_descriptor g_baseClassDesc[] = {
    DECLARE_NAPI_FUNCTION("connect", Connect),
    DECLARE_NAPI_FUNCTION("close", Close),
    DECLARE_NAPI_FUNCTION("transmit", Transmit),
};

// 各标签子类
napi_property_descriptor nfcADesc[] = {
    DECLARE_NAPI_FUNCTION("getAtqa", GetAtqa),
    DECLARE_NAPI_FUNCTION("getSak", GetSak),
};

// 合并基类和子类描述符
napi_property_descriptor* allDesc = MergeAllDesc(g_baseClassDesc, nfcADesc);
napi_define_class(env, "NfcATag", NAPI_AUTO_LENGTH, Constructor, ...);
```

**关键文件位置**：`communication_nfc/frameworks/js/napi/tag/nfc_napi_tag.cpp` 及各 `nfc_napi_tag*.cpp` 子文件

---

### 模式25：Sys* 前缀系统 API 变体模式

**描述**：`@system.xxx` 系列系统 API 的 C++ 实现函数使用 `Sys` 前缀命名（如 `SysStartBLEScan`），与同名标准 API 的函数（如 `StartBLEScan`）共存于同一 NAPI 模块中。两种 API 通过不同的 JS 方法名注册到同一个 exports 对象。

**正则表达式**：`DECLARE_NAPI_FUNCTION\s*\(\s*"[^"]*"\s*,\s*Sys\w+`

**代码结构**：
```cpp
// napi_bluetooth_ble.cpp
napi_property_descriptor desc[] = {
    DECLARE_NAPI_FUNCTION("startBLEScan", StartBLEScan),      // @ohos.bluetooth.ble
    DECLARE_NAPI_FUNCTION("stopBLEScan", StopBLEScan),        // @ohos.bluetooth.ble
    DECLARE_NAPI_FUNCTION("startBLEScan", SysStartBLEScan),   // @system.bluetooth (条件编译)
    DECLARE_NAPI_FUNCTION("stopBLEScan", SysStopBLEScan),     // @system.bluetooth (条件编译)
};
```

**关键文件位置**：`communication_bluetooth/frameworks/js/napi/src/ble/napi_bluetooth_ble.cpp`

---

### 模式26：nm_modname 无独立模块的 API（注册在其他模块下）

**描述**：部分 JS API 模块（如 nfctech、tagSession）在 NAPI 层没有独立的 nm_modname 注册，而是将其 API 方法注册到相关联的模块中。例如 nfctech 的各标签类型方法注册在 "nfc.tag" 模块下，通过 napi_define_class 的类名区分。声明文件中的模块名（nfctech）与实际 NAPI 模块名（nfc.tag）不同。

**识别特征**：
- API 声明文件的模块名（如 `nfctech`）在 DataBases 中找不到对应的 nm_modname
- API 方法实际注册在功能相近的模块中（如 `nfc.tag`）
- 通过 napi_define_class 的类名或 JS 方法名匹配定位

**搜索策略**：当 nm_modname 搜索无结果时，在相关功能模块的 NAPI 入口文件中搜索 API 方法名。

---

### 模式27：dlopen/dlsym 动态加载 SDK 模式

**描述**：NAPI 层通过 `dlopen` 在运行时加载外部 SDK 共享库（如 `/system/lib64/platformsdk/libxxx.z.so`），再通过 `dlsym` 按函数名获取函数指针进行调用。SDK 本身不在当前代码仓中，实际业务逻辑完全委托给外部库。常配合条件编译宏（如 `#ifdef FEATURE_ENABLE`）控制是否启用。

**正则表达式**：`dlopen\s*\(.*\.so` 或 `dlsym\s*\(\s*\w+\s*,\s*"(\w+)"`

**代码结构**：
```cpp
// NAPI 函数实现
napi_value ScanFile(napi_env env, napi_callback_info info) {
    void* handle = dlopen("/system/lib64/platformsdk/libdia_sdk.z.so", RTLD_LAZY);
    auto func = (FuncType)dlsym(handle, "IdentifySensitiveFileC");
    func(policyC, policyLength, &filePath, &matchResults, &matchResultLength);
    dlclose(handle);
}
```

**映射链路**：
```
.d.ts 声明 → NAPI (dlopen + dlsym) → 外部 SDK .so（不在 DataBases 中）
```

**识别特征**：
- `impl_file_path` 为空或仅指向 NAPI 文件本身
- `Framework_decl_file` 为空（无中间 Framework 层）
- NAPI 代码中包含 `dlopen`/`dlsym` 调用
- 可能有 `#ifdef` 条件编译包裹

**关键文件位置**：`interfaces/kits/*/napi/src/` 下使用 dlopen 的 NAPI 文件

---

### 模式28：纯 ABC 字节码模块（ArkUI 组件 ABC 加载）

**描述**：部分 ArkUI 组件（如 PhotoPickerComponent、AlbumPickerComponent）作为纯 ABC（ArkUI Bytecode）模块实现。C++ 入口文件仅注册 nm_modname 并通过 NAPI 框架加载嵌入的 .abc 字节码文件。实际的业务逻辑完全在 .ets/.js 源文件中实现，不经过 C++ NAPI 层。

**正则表达式**：`\.nm_modname\s*=\s*"file\.(Photo|Album)Picker"` 或 `requireInternalFile`

**代码结构**：
```cpp
// photopickercomponent.cpp — ABC 加载器入口
static napi_value Import(napi_env env, napi_value exports) {
    // 仅加载嵌入的 ABC 字节码，无 C++ 业务逻辑
}

// photopickercomponent.js — 编译后的 JS facade
class PickerController {
    setData(dataType, data) { ... }
    addData(dataType, data) { ... }
}
```

**映射链路**：
```
.d.ets 声明 → photopickercomponent.cpp (ABC 加载器，nm_modname)
           → photopickercomponent.js (编译后的 JS facade)
           → PhotoPickerComponent.ets (原始 ETS 源码)
```

**识别特征**：
- NAPI 入口文件非常简短（< 100 行），只有 Import 函数
- 存在同名的 .js 或 .abc 文件
- 无 DECLARE_NAPI_FUNCTION 或 napi_define_class 调用
- 组件类方法在 JS/ETS 层实现

**关键文件位置**：`multimedia_media_library/frameworks/js/src/photopickercomponent.cpp`、`albumpickercomponent.cpp`

---

### 模式29：napi_define_sendable_class 可发送类注册

**描述**：sendable 模块（如 @ohos.file.sendablePhotoAccessHelper）使用 `napi_define_sendable_class` 注册可发送类（Sendable Class）。这是 HarmonyOS 对标准 napi_define_class 的扩展，用于跨线程安全传递的类对象。每个可发送类有独立的 NAPI 实现文件。

**正则表达式**：`napi_define_sendable_class\s*\(`

**代码结构**：
```cpp
// native_module_ohos_photoaccess_helper_sendable.cpp — 模块入口
napi_value Export(napi_env env, napi_value exports) {
    SendablePhotoAccessHelper::Init(env, exports);
    SendableFileAssetNapi::Init(env, exports);
    SendableFetchFileResultNapi::Init(env, exports);
    SendablePhotoAlbumNapi::Init(env, exports);
}

// sendable_photo_access_helper_napi.cpp — 类注册
napi_value Init(napi_env env, napi_value exports) {
    napi_property_descriptor properties[] = {
        DECLARE_NAPI_FUNCTION("getAssets", GetAssets),
        DECLARE_NAPI_FUNCTION("createAsset", CreateAsset),
    };
    napi_define_sendable_class(env, "PhotoAccessHelper", ...);
}
```

**映射链路**：
```
.d.ets 声明 → native_module_ohos_photoaccess_helper_sendable.cpp (模块入口)
           → sendable_*_napi.cpp (可发送类实现)
           → UserFileClient (DataShare IPC 业务逻辑)
```

**识别特征**：
- 模块名包含 "sendable" 关键字
- 使用 `napi_define_sendable_class` 而非 `napi_define_class`
- 类名通常以 "Sendable" 前缀开头
- 业务逻辑委托给 UserFileClient/DataShare IPC 层

**关键文件位置**：`multimedia_media_library/frameworks/js/src/sendable/`

---

### 模式30：napi_define_properties 视图属性 + napi_define_class 控制器双重注册

**描述**：MovingPhotoView 等组件使用双重注册模式：视图属性通过 `napi_define_properties` 注册到模块 exports，控制器通过 `napi_define_class` 注册为可导出类。两个模块（static 和 dynamic）共享同一 C++ 后端。组件位于 arkui_ace_engine 仓而非功能仓。

**正则表达式**：`napi_define_properties\s*\(.*movingphoto` 或 `JsCreate|JsMuted|JsAutoPlay`

**代码结构**：
```cpp
// movingphoto_napi.cpp — NAPI 入口
napi_property_descriptor viewDescs[] = {
    DECLARE_NAPI_FUNCTION("create", JsCreate),
    DECLARE_NAPI_FUNCTION("muted", JsMuted),
    DECLARE_NAPI_FUNCTION("autoPlay", JsAutoPlay),
};
napi_define_properties(env, exports, ...);

// MovingPhotoViewController 注册
napi_define_class(env, "MovingPhotoViewController", NAPI_AUTO_LENGTH, Constructor, ...);
```

**映射链路**：
```
.d.ts 声明 → movingphoto_napi.cpp (NAPI 属性+类注册)
           → MovingPhotoModelNG (ArkUI 组件模型)
           → frameworks/core/components_ng/ (业务逻辑)
```

**识别特征**：
- 两个模块（如 MovingPhotoView.static 和 movingphotoview）映射到同一 C++ 模块
- 组件在 arkui_ace_engine 仓而非功能仓
- 视图属性和控制器分别用不同的 NAPI 注册方式

**关键文件位置**：`arkui_ace_engine/component_ext/movingphoto/`

---

### 模式31：NAPI + Taihe/ANI 双轨绑定 (dynamic/static 分离)

**描述**：同一模块的 API 分为 dynamic 和 static 两套并行实现。Dynamic API 使用传统 NAPI 注册（DECLARE_NAPI_FUNCTION / DECLARE_NAPI_STATIC_FUNCTION），Static API 使用 Taihe IDL + ANI 运行时（TH_EXPORT_CPP_API_xxx 宏）。两套实现共享相同的底层业务逻辑（如 MotionClient, BoomerangManager -> IntentionManager -> IPC Client）。常见于 MultimodalAwarenessKit。

**正则表达式**：`TH_EXPORT_CPP_API_\w+.*Inner` 或 `@since\s+\d+\s+static` (JSDoc 标记)

**代码结构**：
```cpp
// NAPI 层 (dynamic 模式) — frameworks/js/napi/<module>/src/*_napi.cpp
napi_property_descriptor desc[] = {
    DECLARE_NAPI_STATIC_FUNCTION("on", SubscribeMotion),
    DECLARE_NAPI_STATIC_FUNCTION("off", UnSubscribeMotion),
};
napi_define_properties(env, exports, sizeof(desc) / sizeof(desc[0]), desc);

// Taihe IDL 层 (static 模式) — frameworks/ets/<module>/idl/*.taihe
// ohos.multimodalAwareness.motion.taihe
interface Motion {
    void onOperatingHandChanged(Callback<OperatingHandStatus> callback);
    void offOperatingHandChanged(Callback<OperatingHandStatus>? callback);
}

// Taihe 实现 — frameworks/ets/<module>/src/*.impl.cpp
TH_EXPORT_CPP_API_OnOperatingHandChangedInner(params) {
    AniMotionEvent::AddCallback(OPERATING_HAND_TYPE);
}
```

**JS API 到 C++ 的映射**：
- dynamic: `on("operatingHandChanged", cb)` → NAPI `SubscribeMotion` → `MotionClient::SubscribeCallback`
- static: `onOperatingHandChanged(cb)` → Taihe `OnOperatingHandChangedInner` → `AniMotionEvent::AddCallback` → `MotionClient::SubscribeCallback`

**识别特征**：
- JSDoc 中有 `@since N dynamic` 和 `@since N static` 标记
- NAPI 入口在 `frameworks/js/napi/` 下，Taihe 入口在 `frameworks/ets/` 下
- Static API 的 JS 方法名通过 `sts_inject` 注入桥接到 `*Inner` C++ 函数
- `@gen_promise` 注解自动生成 Promise 包装

**映射链路**：
```
.d.ts 声明 (dynamic/static 标记)
  ├── dynamic: → frameworks/js/napi/<module>/*_napi.cpp (NAPI 注册)
  │            → frameworks/native/src/*_manager.cpp (Facade)
  │            → intention/*/client/src/*_client.cpp (IPC Client)
  └── static:  → frameworks/ets/<module>/idl/*.taihe (Taihe IDL)
               → frameworks/ets/<module>/src/*.impl.cpp (Taihe 实现)
               → frameworks/ets/<module>/src/ani_*_manager.cpp (ANI Manager)
               → 同上底层业务逻辑
```

**关键文件位置**：
- NAPI: `msdp_device_status/frameworks/js/napi/<module>/src/`
- Taihe IDL: `msdp_device_status/frameworks/ets/<module>/idl/*.taihe`
- Taihe 实现: `msdp_device_status/frameworks/ets/<module>/src/*.impl.cpp`
- ANI Manager: `msdp_device_status/frameworks/ets/<module>/src/ani_*_manager.cpp`

---

### 模式32：NExporter 类继承体系（NVal::DeclareNapiFunction）

**描述**：hilog 等模块使用 `NExporter` 类继承体系进行 NAPI 绑定，不同于标准的 DECLARE_NAPI_FUNCTION 宏。子类继承 `NExporter`，在 `Export()` 静态方法中通过 `NVal::DeclareNapiFunction()` 注册函数，模块入口使用 `NAPI_MODULE(name, Export)`。

**正则表达式**：`NExporter|NVal::DeclareNapiFunction|NAPI_MODULE\s*\(`

**代码结构**：
```cpp
// hilog_napi.cpp
class HilogNapi : public NExporter {
public:
    static napi_value Export(napi_env env, napi_value exports) {
        NVal::DeclareNapiFunction(env, exports, {"debug", HilogNapiBase::Debug});
        NVal::DeclareNapiFunction(env, exports, {"info", HilogNapiBase::Info});
    }
};

// module.cpp
NAPI_MODULE(hilog, HilogNapi::Export)
```

**关键文件位置**：`hiviewdfx_hilog/interfaces/js/kits/napi/src/hilog/src/`

---

### 模式33：双 nm_modname 前后端分离（JS facade + Native backend）

**描述**：部分模块（如 jsLeakWatcher）注册两个独立的 nm_modname：一个用于 ABC/TS 字节码加载器（JS 门面），另一个用于 C++ NAPI 后端（底层功能）。JS 门面通过 `requireNapi()` 调用 C++ 后端。

**正则表达式**：`requireNapi\s*\(\s*['"][^']*[Nn]ative['"]` 或双 nm_modname 注册

**代码结构**：
```javascript
// js_leak_watcher.ts — JS 门面
const native = requireNapi('hiviewdfx.jsleakwatchernative');
export function enable(isEnable) { /* JS 逻辑 */ }
export function dump(filePath) { return native.dumpRawHeap(filePath); }
```

```cpp
// js_leak_watcher_module.cpp — ABC 加载器
.nm_modname = "hiviewdfx.jsLeakWatcher"

// js_leak_watcher_napi.cpp — C++ 后端
.nm_modname = "jsLeakWatcherNative"
BindNativeFunction(env, exports, "dumpRawHeap", DumpRawHeap);
```

**关键文件位置**：`hiviewdfx_hichecker/interfaces/js/kits/napi/js_leak_watcher/`

---

### 模式34：GenericCallback + IPC Handler 分发（数据驱动通用回调）

**描述**：所有 JS API 共用一个 `GenericCallback` 函数作为 NAPI 入口，通过 `FrontendMethodDef` 结构体区分不同 API。参数序列化为 JSON 后通过 IPC（`ApiTransactor`）发送到后端服务进程，由 `FrontendApiServer` 的 handler 映射表分发到具体处理函数。常见于测试框架（testfwk_arkxtest）。

**正则表达式**：`FrontendMethodDef|GenericCallback|FrontendApiServer`

**代码结构**：
```cpp
// API 定义表
static const std::vector<FrontendMethodDef> METHOD_DEFS = {{
    { "Driver.click", "xx,y", false, true, false, false },
    { "PerfTest.create", "s", true, false, false, false },
}};

// 通用 NAPI 回调
napi_value GenericCallback(napi_env env, napi_callback_info info) {
    // 序列化参数 -> ApiTransactor IPC -> 后端处理
}

// 后端 Handler 注册
void RegisterApiHandlers() {
    handler_["Driver.click"] = [](json& params) { UiDriver::PerformTouch(...); };
}
```

**映射链路**：
```
.d.ts 声明 -> uitest_napi.cpp (GenericCallback, 数据驱动注册)
           -> ApiTransactor IPC -> FrontendApiServer handler 分发
           -> ui_driver.cpp / perf_test.cpp (业务逻辑)
```

**JS API 到 C++ 的映射**：
- `Driver.click(x, y)` -> `GenericCallback("Driver.click")` -> IPC -> handler -> `UiDriver::PerformTouch`
- 旧 API 自动映射：`By.id` -> `old2NewApiMap_` -> `On.accessibilityId`

**识别特征**：
- 所有 API 共用同一个 `GenericCallback` 回调函数
- `FrontendMethodDef` 结构体定义 API 名称、参数签名、static/fast 等属性
- IPC 通信到独立服务进程
- 后端通过 handler 映射表分发

**关键文件位置**：`testfwk_arkxtest/uitest/napi/uitest_napi.cpp`、`testfwk_arkxtest/perftest/napi/src/perftest_napi.cpp`

---

### 模式35：ExtensionAbility CallObjectMethod（反向调用：C++ → JS 回调）

**描述**：CryptoExtensionAbility 等扩展能力模块的 API（如 onOpenResource、onAuthUkeyPin）是 ExtensionAbility 生命周期回调方法。调用方向与标准 NAPI 相反：不是 JS 调用到 C++，而是 C++ 服务端通过 napi_get_named_property + napi_call_function 反射调用到 JS Extension 实例的方法。

**正则表达式**：`CallJsMethod\s*\(\s*"on\w+"` 或 `OHOS_EXTENSION_GetExtensionModule`

**代码结构**：
```cpp
// crypto_ext_module.cpp — 模块注册（非标准 napi_module）
NAPI_security_CryptoExtensionAbility_AutoRegister() {
    // 注册 security.CryptoExtensionAbility，加载嵌入的 JS/ABC 字节码
}

// hks_ext_module_loader.cpp — Extension 入口
extern "C" void* OHOS_EXTENSION_GetExtensionModule() {
    return HksCryptoExtAbility::Create(runtime);
    // 当 runtime 为 JS 时，创建 JsHksCryptoExtAbility
}

// js_hks_crypto_ext_ability.cpp — C++ 到 JS 桥接
int32_t JsHksCryptoExtAbility::OpenRemoteHandle(...) {
    return CallJsMethod("onOpenResource", ...);
}

int32_t CallJsMethod(const std::string& methodName, ...) {
    napi_get_named_property(env, jsObj, methodName.c_str(), &method);
    napi_call_function(env, jsObj, method, argc, argv, &result);
    // 处理 Promise 结果：napi_is_promise -> then -> 条件变量同步等待
}
```

**映射链路**：
```
.d.ts 声明 (onXxx 方法)
  → crypto_ext_module.cpp (模块注册，加载 JS/ABC)
  → crypto_extension_ability.js (JS 基类存根，开发者覆写)
  → hks_ext_module_loader.cpp (OHOS_EXTENSION_GetExtensionModule)
  → js_hks_crypto_ext_ability.cpp (C++ → JS 桥接，CallJsMethod)
  → hks_crypto_ext_stub_impl.cpp (IPC Stub，委托到 Extension 实例)
```

**JS API 到 C++ 的映射**：
- onOpenResource(...) → JsHksCryptoExtAbility::OpenRemoteHandle → CallJsMethod("onOpenResource")
- onAuthUkeyPin(...) → JsHksCryptoExtAbility::AuthUkeyPin → CallJsMethod("onAuthUkeyPin")

**识别特征**：
- API 方法名以 on 开头，属于 ExtensionAbility 回调
- component_map.json 中没有 nm_modname 映射
- 使用 OHOS_EXTENSION_GetExtensionModule() 而非标准 napi_module
- C++ 侧使用 napi_get_named_property + napi_call_function 反射调用 JS 方法
- 支持通过 napi_is_promise 处理异步 Promise 返回值

**关键文件位置**：security_huks/interfaces/js/crypto_extension_module/（模块注册）、security_huks/services/huks_standard/huks_service/extension/ability_native/（实现）

---

### 模式36：VM-Builtin Bridge（NAPI 薄桥接 → VM 内建类）

**描述**：@arkts.collections 等模块使用极薄的 NAPI 桥接层，从全局作用域获取预注册的 VM 内建类并重新导出。NAPI 层不包含任何业务逻辑，实际实现在 arkcompiler_ets_runtime 的 builtins 中作为静态 C++ 函数注册。

**正则表达式**：`RegisterSendableContainers|InitArkTSCollections|BUILTIN_SHARED_\w+_PROTOTYPE_FUNCTIONS`

**代码结构**：
```cpp
// native_module_collections.cpp — NAPI 薄桥接
napi_value Init(napi_env env, napi_value exports) {
    napi_value sendableArray = GetGlobalBuiltin(env, "SendableArray");
    napi_set_named_property(env, exports, "Array", sendableArray);
}
// builtins.cpp — VM 启动时注册
void Builtins::RegisterSendableContainers() { /* 注册全局内建类 */ }
// builtins_shared_array.cpp — 实际 VM 内建实现
BUILTIN_SHARED_ARRAY_PROTOTYPE_FUNCTIONS(...) { /* push, pop, splice... */ }
```

**关键文件位置**：
- NAPI 桥接: `commonlibrary_ets_utils/js_util_module/collections/native_module_collections.cpp`
- VM 内建: `arkcompiler_ets_runtime/ecmascript/builtins/builtins_shared_*.cpp`

---

### 模式37：ArkPrivate.Load 高性能内建（容器/Buffer 快速路径）

**描述**：FastBuffer、容器类高性能变体通过 ArkPrivate.Load() 加载，绕过 NAPI 直接使用 VM 内建。JS 门面通过 globalThis.ArkPrivate.Load() 获取原生对象，NAPI 模块 Init 为空。

**正则表达式**：`ArkPrivate\.Load\s*\(|CONTAINER_FASTBUFFER_PROTOTYPE_FUNCTIONS`

**代码结构**：
```javascript
const FastBufferInner = globalThis.ArkPrivate.Load(ArkPrivate.FastBuffer);
class FastBuffer extends FastBufferInner { /* 覆盖部分方法 */ }
```

**关键文件位置**：
- `commonlibrary_ets_utils/js_api_module/fastbuffer/` + `arkcompiler_ets_runtime/ecmascript/containers/containers_buffer.cpp`

---

### 模式38：napi_module_with_js 混合 NAPI + 嵌入式 JS/ABC

**描述**：url、uri、xml 等模块使用 napi_module_with_js，同时嵌入 JS/ABC 字节码。C++ NAPI 层注册核心类，嵌入 JS/ABC 为 static API 变体提供包装。

**正则表达式**：`napi_module_with_js|nm_get_js_code|nm_get_abc_code`

**关键文件位置**：`commonlibrary_ets_utils/js_api_module/{url,uri,xml}/`

---

### 模式39：纯 ETS 反射模块（无 NAPI/C++ 层）

**描述**：@ohos.transfer 等模块完全在 ETS 层实现，使用反射机制进行类型转换。

**正则表达式**：`Class\.ofCaller|getLinker\(\)\.loadClass`

**关键文件位置**：`commonlibrary_ets_utils/base_sdk/transfer/`
