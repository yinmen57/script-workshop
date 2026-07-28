## 一致性锁定句式

在基于参考图做续图、扩展分镜时，必须在提示词末尾追加一致性锁定句，否则角色长相、服装、环境会在多张图之间漂移。
标准句式：Maintain identical character designs, clothing, environment, art style and color palette as the reference image. High quality, cinematic.
锁定的五个维度是：角色设计、服装、环境、美术风格、色板。做局部改动（如只改光影）时还要追加 Maintain exact same composition, characters, and scene.

---

## 剧情推演四格的结构

从一张参考图推演四格剧情时，四格按叙事功能划分，而不是随机取四个瞬间：
第一格 initial moment，角色处于起始位置，动作发生前的平静状态。
第二格 action begins，角色开始与环境或另一个人产生互动。
第三格 dramatic peak，张力或意外的关键时刻，配合富有表现力的肢体语言。
第四格 resolution，事件之后的余波，角色做出反应或重新安定。
四格统一用 1:1 比例、2K 分辨率，并全部追加一致性锁定句。

---

## 角色三视图的提示词写法

生成角色转身图（turnaround sheet / model sheet）时，用一张横向宽图排一行四个画面，从左到右依次是：全身正面、全身右侧面、全身背面、放大的面部特写。
必须显式写出负向约束，否则模型会自作主张改比例或改排版：不要换行到第二行、不要用 2x2 网格、不要堆叠画面；严格保持参考图的体型，不要拉长腿部、不要收窄腰部、不要让身体变瘦、不要改变头身比、不要夸张曲线、不要风格化比例。
三个全身视图必须完整显示从头到脚，自然站姿、居中、无遮挡、四肢不被裁切、不用极端透视。
还要排除：不要多余角色、不要多余道具、不要场景背景、不要戏剧化动作姿势、不要文字标签、不要水印。输出用 16:9 比例、2K 分辨率。

---

## 时间推演提示词的写法

向后推演（3 秒后）：要求模型延续角色的自然动作，并给出可判定的具体推理示例——如果角色正在伸手拿东西，现在应该已经拿到手里；如果正在走路，应该已经向前移动了几步。
向前推演（5 秒前）：角色处于当前动作发生之前的位置——如果现在坐着，之前应该是站着或正在走近；如果手里拿着物品，之前还没有拿起它。
两种推演都必须保持环境、光照、美术风格、角色设计完全一致，只改变动作与位置。

---

## 带货的产品替换任务铁律

本条只适用于 content_type 为 commerce 的脚本。把旧产品替换为新产品，是查找替换任务，不是重新创作任务。不能改变故事情节、不能增删场景、不能改变角色。
五条硬约束：scenes 数组长度必须与原脚本完全相同；每个场景的 shot_number、duration、timestamp、shot_type 原样保留；roles 中 character、prop、scene、creature 类型的角色原样保留且 role_name 与 role_description 不能改；场景的整体叙事线与人物行为逻辑与原脚本一致；lighting 与 sound_effect 保持不变。
执行替换时温度取 0.3 而不是常规生成的 0.7，降低模型自由发挥的空间。

---

## 带货的产品替换操作范围

本条只适用于 content_type 为 commerce 的脚本。需要改动的只有六处：roles 中 role_type 为 product 的条目改 role_name 与 role_description；title 改为包含新产品名的标题；每个场景中出现旧产品名的字段（character1_name、character2_name、scene_description、dialogue、character_action、storyboard_prompt、video_motion_prompt）替换为新产品名与描述；dialogue 围绕新产品卖点重写但模仿原脚本的语气与长度；storyboard_prompt 中涉及旧产品外观的描述改为新产品外观；character_action 在产品形态不同时微调持握与展示动作。
不涉及产品的场景（开场空镜、角色情绪镜头）保持原文不变或仅做微调。原脚本中的宠物、配角等非产品角色必须原样保留。
新产品品类与原产品不同时（如原产品是唇线笔、新产品是湿巾纸），合理调整持握方式、展示动作、使用场景，但场景数量和节奏不变。

---

## 多模态输入的模式差异

从文字生成脚本时直接给出剧本内容即可。
从参考视频生成脚本时，视频以 video_url 传入并设置 fps 为 1.0 抽帧。content_type 为 commerce 时还要提示模型：这是创作参考视频，用户将用自己的产品和角色替换原内容，所以 product 类型的 role 要用通用品类名而非视频中的具体品牌名。
从角色图片生成脚本时，图片以 image_url 数组传入，模型需要根据角色外貌特征生成包含这些角色的分镜。
