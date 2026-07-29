任务：从以下剧本材料中提取风格圣经、人物与归属道具，并只输出 JSON。
集与叙事空间已由规则解析完成，不要输出 scenes。

材料：
{script_text}

输出 Schema：
```json
{
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
  ]
}
```

规则：`character_key` 由人物名规范化得到；`prop_key` 必须包含归属、类型和名称。归属无法关联到人物时填 `owner_name: null`、`status: "needs_review"`。
