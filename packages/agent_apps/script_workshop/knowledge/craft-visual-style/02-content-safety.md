## 真人素材的硬性限制

图片中检测到真人面部时，视频生成会被直接拒绝，错误码属于 PrivacyInformation 类。
不支持直接使用真人照片作为生成素材，必须改用虚拟形象素材。
因此角色参考图的准备环节就要排除真人照片，不要等到提交生成任务时才发现。

---

## 内容安全审核红线

素材或提示词触发内容安全审核时会返回 SensitiveContent 类错误，表现为 content safety、moderation、sensitive 等关键字。
处理方式是修改素材或提示词后重试，不是重复提交同样内容。
提示词编写阶段就要避免暴力、成人、政治敏感描述，以及可能被识别为侵权的具体品牌名。

---

## 参考素材的规格限制

参考视频分辨率过高会报 video pixel count 错误，建议不超过 720p。
参考图片分辨率过高会报 image pixel count 错误，需要先压缩。
文件体积过大报 file size / too large，同样需要压缩。
支持的文件格式为 JPG、PNG、MP4、MOV，其他格式会报 format / codec / unsupported 错误。
参考视频时长不符合要求会报 duration 相关错误。

---

## 常见接口错误的判定与应对

InvalidParameter 表示提交的参数不符合要求，要检查素材与生成设置的组合是否合法（例如给 Seedream 5.0 传了 4K）。
asset not found / invalid 表示引用的素材不存在或已失效，需要重新选择素材。
download fail / timeout 表示素材文件下载失败，要检查素材 URL 是否仍然有效。
resolution 相关错误表示分辨率档位与模型版本不匹配。
401 与 403 是服务认证失败，429 是服务繁忙需要退避重试，5xx 是服务端暂时不可用需要稍后重试。
rate limit / too many 表示请求过于频繁，quota / insufficient 表示服务额度不足。

---

## 生成失败时的排查顺序

先看错误码归类再决定是否重试：认证类（401/403）、额度类（quota）、参数类（InvalidParameter、resolution）属于确定性失败，原样重试没有意义，必须先改配置或素材。
限流类（429、rate limit）与服务端类（5xx）属于瞬时失败，退避后重试即可。
审核类（SensitiveContent、PrivacyInformation）必须换素材或改提示词，重试同样内容一定继续失败。
