**通用错误码**
| error code | 中文错误说明 | error message | 错误描述 | 可能原因|  处理步骤 |
| ---------- | ------------- | ---------- | ------- | ------ | ------ |
| 201 | 权限校验失败 | Permission verification failed. The application does not have the permission required to call the API. | 权限校验失败，应用无权限使用该API，需要申请权限。| 该错误码表示权限校验失败，通常为没有权限，却调用了需要权限的API。 | 请检查是否有调用API的权限。 |
| 202 | 系统API权限校验失败 | Permission verification failed. A non-system application calls a system API. | 权限校验失败，非系统应用使用了系统API。 | 非系统应用，使用了系统API，请校验是否使用了系统API。 | 请检查是否调用了系统API，并且去掉。 |
| 203 | 企业管理策略禁止使用此系统功能 | This function is prohibited by enterprise management policies. | 企业管理策略禁止使用此系统功能。 | 试图操作已被设备管理应用禁用的系统功能。 | 请使用getDisallowedPolicy接口检查该系统功能是否被禁用，并使用setDisallowedPolicy接口解除禁用状态 |
| 401 | 参数检查失败 | Parameter error. Possible causes: 1. Mandatory parameters are left unspecified; 2. Incorrect parameter types; 3. Parameter verification failed. | 1.必填参数为空。2.参数类型不正确。3.参数校验失败。无论是同步还是异步接口，此类异常大部分都通过同步的方式抛出。 | 1. 必选参数没有传入 2. 参数类型错误 (Type Error) 3. 参数数量错误 (Argument Count Error) 4. 空参数错误 (Null Argument Error) 5. 参数格式错误 (Format Error) 6. 参数值范围错误 (Value Range Error) | 请检查必选参数是否传入，或者传入的参数类型是否错误。对于参数校验失败，阅读参数规格约束，按照可能原因进行排查。 |
| 801 | 该设备不支持此API | Capability not supported. Failed to call the API due to limited device capabilities. | 该设备不支持此API，因此无法正常调用。 | 可能出现该错误码的场景为：该设备已支持该API所属的Syscap，但是并不支持此API。 | 应避免在该设备上使用此API，或在代码中通过判断来规避异常场景下应用在不同设备上运行所产生的影响。 |