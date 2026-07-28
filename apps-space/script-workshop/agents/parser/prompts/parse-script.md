任务：解析以下剧本，并只输出 JSON。

剧本：
{script_text}

输出 Schema：
```json
{
  "content_type": "narration_comic",
  "style_bible": {
    "era": "",
    "visual_style": "",
    "color_palette": [],
    "tone": "",
    "camera_language": ""
  },
  "characters": [
    {
      "name": "",
      "character_key": "",
      "appearance_anchor": "",
      "costume_baseline": "",
      "personality_tags": []
    }
  ],
  "props": [
    {
      "name": "",
      "prop_type": "",
      "owner_name": null,
      "scope": "owned",
      "prop_key": "",
      "visual_anchor": "",
      "status": "ready"
    }
  ],
  "scenes": [
    {"ordinal": 1, "name": "", "summary": "", "characters": [], "props": []}
  ]
}
```

规则：`content_type` 只能是 `narration_comic` 或 `commerce`，先判定类型再提取资产；`character_key` 由人物名规范化得到；`prop_key` 必须包含归属、类型和名称。归属无法关联到人物时填 `owner_name: null`、`status: "needs_review"`。
