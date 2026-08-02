为下面这一集判定叙事空间的语义边界。

## 集元数据

{episode}

## 规则粗切基线（仅供参考，可以推翻）

按地点与转场信号得到的初始分段，编号即段落区间：

{rough_spaces}

粗切只看字面信号，常见问题是同一场戏被切开、或两场戏被粘在一起。请按语义重新判定。

## 正文段落（共 {paragraph_count} 段）

{paragraphs}

## 输出要求

只输出 JSON 对象，不要 markdown 说明：

```json
{
  "spaces": [
    {
      "ordinal": 1,
      "title": "空间标题，用地点或这场戏的核心事件命名，不超过 20 字",
      "location": "地点名，取自正文或集元数据",
      "time_place": "时间 / 地点，如「深夜 / 精品酒店套房」",
      "summary": "这段戏发生了什么，40 字以内",
      "beat_type": "hook | setup | escalation | turn | climax | cliffhanger",
      "mood": "情绪基调，如「紧绷」「暧昧」「羞辱」",
      "boundary_reason": "为什么在这里断开，20 字以内",
      "start_paragraph": 1,
      "end_paragraph": 7
    }
  ]
}
```

硬性约束：

1. `start_paragraph` / `end_paragraph` 用上面正文的段号，从 1 到 {paragraph_count}
2. 全部空间的段号区间必须**连续覆盖 1 到 {paragraph_count}**，不得重叠、不得跳段、不得遗漏
3. `ordinal` 从 1 开始按出场顺序递增
4. 不输出正文内容
5. 一集的叙事空间数量应当与实际场次相当，通常是 2 到 8 个；切出十几个碎片说明你在按长度拆分，这是错的
