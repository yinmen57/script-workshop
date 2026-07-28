任务：为一个分镜生成视频提示词。

风格圣经：
{style_bible}

分镜：
{shot}

人物参考图：
{character_image_refs}

道具参考图：
{prop_image_refs}

只输出 JSON：
```json
{
  "prompt_text": "",
  "duration_sec": 5,
  "reference_image_ids": []
}
```

描述必须包含动作、镜头、光线和节奏；人物与道具外观必须与参考图一致，不得互换私有道具。
