## 分镜脚本的 17 个标准字段

分镜脚本每一行（一个镜头）由 17 个字段构成，字段名与中文列名对应关系固定：
shot_number 镜号、duration 时长、scene_description 画面描述、character1_name 角色1、character1_description 角色描述1、character2_name 角色2、character2_description 角色描述2、reference 参考、shot_type 景别、character_action 角色动作、emotion 情绪、scene_tag 场景标签、lighting 光影氛围、sound_effect 音效、dialogue 对白、storyboard_prompt 分镜提示词、video_motion_prompt 视频运动提示词。
生成脚本时必须输出全部字段，无内容的字段留空字符串而不是省略该字段。

---

## 脚本 JSON 的顶层结构

脚本必须是包含 title、content_type、roles、scenes 四个顶层字段的 JSON 对象：
title 为脚本标题；content_type 为内容类型枚举，取值 narration_comic 或 commerce，判定规则见内容类型机制条目；roles 为需要独立视觉参考的实体数组；scenes 为镜头数组。
输出时严格只返回 JSON，不要添加任何额外说明文字，不要用 markdown 代码块包裹。roles 中每个元素含 role_name、role_type、role_description；scenes 中每个元素含 17 个标准字段加 timestamp。

---

## scenes 的时长与时间轴规则

duration 是秒数，粒度到 0.5 秒，允许一位小数；timestamp 是该场景的起始秒数，从 0 开始按前序场景 duration 累加，即 timestamp(n) = timestamp(n-1) + duration(n-1)，同样允许小数。这两条是通用规则。
duration 的取值区间和整片镜头数按 content_type 分别规定，只查该类型专属条目。narration_comic 查解说漫节奏条目；commerce 的节奏口径尚未整理，不得套用解说漫数值，应标记 needs_review。
duration 是分镜的叙事时长，不是一次视频生成任务的时长。视频模型支持一次生成包含多个镜头，连续分镜会按场景与角色一致的条件打包成镜头组再提交，分组规则见镜头语言部分。

---

## 场景与角色的引用一致性

scenes 中的 character1_name 与 character2_name 必须与 roles 数组里的 role_name 完全一致，不能出现 roles 中不存在的名字。
当某个 product 类型的角色（商品）在该场景中被展示时，要把商品名写入 character1_name 或 character2_name 来建立引用关系。
scene_description 需要清晰交代该场景出现了哪些角色和物品，以及它们之间的互动关系。
character1_description 用于写该角色在这一场景中的特定状态（换装、特定姿态），而不是重复 roles 里的通用外貌描述。

---

## storyboard_prompt 的写法要求

storyboard_prompt 是直接送给 AI 图片生成模型的提示词，必须足够详细，包含六个要素：主体、动作、构图、光影、风格、氛围。
只写「一个女孩站着」这类信息量不足的描述会导致生成结果不可控。要写成可直接使用的完整画面描述，把景别、机位、光线方向、色调、画质风格都交代清楚。

---

## video_motion_prompt 的写法要求

video_motion_prompt 是送给 AI 视频生成模型的运镜提示词，描述镜头如何运动以及运动速度。
常用运镜词：推镜、拉镜、平移、环绕、固定、跟拍。需要同时交代速度感（缓慢推进、快速跟随），只写运动方式不写速度会让生成的镜头节奏失控。
