## Seedream 图片生成的支持分辨率

不同版本支持的分辨率档位不同，选错会直接被接口拒绝：
doubao-seedream-4-5-251128 支持 1K、2K、4K。
doubao-seedream-5-0-260128 支持 2K、3K，不支持 1K 和 4K。
默认档位取 2K，两个版本都支持。

---

## 2K 档位各比例的像素值

1:1 为 2048x2048；16:9 为 2848x1600；9:16 为 1600x2848；4:3 为 2304x1728；3:4 为 1728x2304；3:2 为 2496x1664；2:3 为 1664x2496。
比例缺省时回落到 1:1。分镜四格与角色格图常用 1:1，横版成片画面用 16:9，竖版短视频用 9:16。

---

## 3K 档位各比例的像素值

1:1 为 3072x3072；16:9 为 4096x2304；9:16 为 2304x4096；4:3 为 3456x2592；3:4 为 2592x3456；3:2 为 3744x2496；2:3 为 2496x3744。
3K 仅 Seedream 5.0 支持。注意 3K 的 16:9 与 4K 的 16:9 像素值相同，都是 4096x2304。

---

## 1K 与 4K 档位各比例的像素值

1K：1:1 为 1024x1024；16:9 为 1280x720；9:16 为 720x1280；4:3 为 1152x864；3:4 为 864x1152；3:2 为 1248x832；2:3 为 832x1248。
4K：1:1 为 4096x4096；16:9 为 4096x2304；9:16 为 2304x4096；4:3 为 4096x3072；3:4 为 3072x4096；3:2 为 4096x2736；2:3 为 2736x4096。
1K 与 4K 仅 Seedream 4.5 支持。

---

## 图片生成的请求参数规范

调用图片生成时 size 传具体像素值字符串（如 2848x1600）而不是 2K 这样的档位关键词，档位与比例需要先换算成像素值。
response_format 固定为 url，watermark 默认 false。
单图生成时 sequential_image_generation 设为 disabled；需要一次生成多张时设为 auto，并通过 sequential_image_generation_options 的 max_images 指定数量。
图生图时把参考图 URL 数组传给 image 参数。

---

## 视频生成的请求参数规范

视频生成为异步任务：先创建任务拿到 task id，再轮询任务状态获取结果。
参数默认值：generate_audio 为 true 生成音频，ratio 为 adaptive 自适应比例，resolution 为 720p，duration 为 5 秒，watermark 为 false。
生成结果的视频 URL 有效期为 24 小时，需要在有效期内下载转存，超时后链接失效。

---

## 电影级光影校正的提示词模板

对已有画面做光影与调色升级时，标准提示词包含五组要素：
黄金时刻暖色调 Golden hour warm tones；有层次的戏剧化阴影 dramatic shadows with depth；胶片颗粒质感 film grain texture；高对比与冷暖分离的电影色板 rich contrast, cinematic color palette with warm highlights and cool shadows；专业电影摄影质感 professional film photography quality, anamorphic lens flare, shallow depth of field。
必须追加 Maintain exact same composition, characters, and scene，否则模型会连构图一起改掉。输出用 16:9 比例、2K 分辨率。
