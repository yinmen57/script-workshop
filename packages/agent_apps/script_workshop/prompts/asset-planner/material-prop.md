任务：为归属道具生成可用于物料图的提示词。

风格圣经：
{style_bible}

道具：
{prop}

输出 JSON：
```json
{
  "prompt_text": "",
  "negative_prompt": "",
  "asset_view": "prop"
}
```

要求：必须保留 `owner_name`、`prop_key` 与 `visual_anchor`，突出可识别的材质、颜色、损耗和专属标识。不得把不同角色的同类道具混为一个通用道具。
