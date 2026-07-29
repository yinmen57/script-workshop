任务：根据叙事空间正文规划分镜（成片单位已由规则切好，本任务只出镜头级描述）。

风格圣经：
{style_bible}

叙事空间：
{scene}

可用人物资产：
{character_assets}

可用道具资产：
{prop_assets}

只输出 JSON：
```json
{
  "shots": [
    {
      "ordinal": 1,
      "beat": "",
      "scene_text": "",
      "camera": {"shot_type": "", "description": ""},
      "character_keys": [],
      "prop_keys": [],
      "duration_sec": 2
    }
  ]
}
```

规则：
- 每个分镜只能引用上方资产列表里的 `character_key` / `prop_key`；
- `camera.shot_type` 使用标准景别（近景、特写、中景、全景、大远景、俯拍、仰拍）；
- 镜头描述须与 `style_bible.camera_language` 一致；
- `duration_sec` 通常 1.5–4 秒（2 秒为基准）；全部分镜时长之和不得超过叙事空间的 `estimated_duration_sec`（若有，且通常 ≤15 秒）。
