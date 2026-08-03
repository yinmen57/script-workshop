# 剧本工坊（script-workshop）

业务 Agent 应用插件，由 `business.apps.bootstrap` 注册进框架。

```text
script_workshop/
  app.py                 # 应用名 / 模型 / coordinator
  agents/*.py            # 每个 Agent 一份 SPEC
  prompts/<agent_id>/    # system.md + 任务模板
  tools.py               # 业务工具实现
  tool_meta.py           # 工具 ID 与描述
  knowledge/             # 知识库语料 + manifest.yaml
```

改 Agent：编辑 `agents/<name>.py` 与对应 `prompts/`。  
改工具：编辑 `tools.py` / `tool_meta.py`。  
索引知识库：`python scripts/index_knowledge.py --slug script-workshop`
