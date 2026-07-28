任务：根据剧本场景规划分镜。

内容类型：
{content_type}

风格圣经：
{style_bible}

场景：
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
      "camera": "",
      "character_keys": [],
      "prop_keys": [],
      "duration_sec": 5
    }
  ]
}
```

每个分镜只能引用当前场景内已确认的人物和道具资产，镜头描述必须与 `style_bible.camera_language` 一致。
`duration_sec` 与整场镜头密度必须符合 `content_type` 对应的类型专属节奏；commerce 节奏未就绪时不要编造数值。
