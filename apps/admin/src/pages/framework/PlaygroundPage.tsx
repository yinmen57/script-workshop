import {
  Button,
  Card,
  Input,
  Select,
  Space,
  Timeline,
  Typography,
  message,
} from "antd";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getAgentRun,
  streamChatCompletions,
  type AgentStep,
  type ChatCitation,
} from "../../api/chat";
import { getWorkspace } from "../../api/resources";
import { CANVAS_STEP_CHANNEL } from "../business/script-canvas/sync/applyAgentStep";

type Msg = { role: "user" | "assistant"; content: string };

const FULL_CHAIN = "";

function formatStep(step: AgentStep): { color?: string; children: ReactNode } {
  if (step.type === "tool_start") {
    return {
      color: "blue",
      children: (
        <div>
          <Typography.Text strong>
            [{step.agent_id}] 开始工具 {step.tool_id}
          </Typography.Text>
          <pre style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", fontSize: 12 }}>
            入参: {JSON.stringify(step.args ?? {}, null, 2)}
          </pre>
        </div>
      ),
    };
  }
  if (step.type === "tool") {
    return {
      color: step.error ? "red" : "blue",
      children: (
        <div>
          <Typography.Text strong>
            [{step.agent_id}] 工具 {step.tool_id}
            {step.duration_ms != null ? ` · ${step.duration_ms}ms` : ""}
          </Typography.Text>
          <pre style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", fontSize: 12 }}>
            入参: {JSON.stringify(step.args ?? {}, null, 2)}
          </pre>
          <pre style={{ margin: "4px 0 0", whiteSpace: "pre-wrap", fontSize: 12 }}>
            返回: {step.output || "-"}
          </pre>
          {step.error ? (
            <Typography.Text type="danger">错误: {step.error}</Typography.Text>
          ) : null}
        </div>
      ),
    };
  }
  return {
    color: "gray",
    children: (
      <div>
        <Typography.Text strong>[{step.agent_id}] 思考</Typography.Text>
        <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{step.output || "-"}</div>
      </div>
    ),
  };
}

export function PlaygroundPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const agentId = searchParams.get("agent_id") || FULL_CHAIN;

  const workspace = useQuery({
    queryKey: ["workspace", slug],
    queryFn: () => getWorkspace(slug),
    enabled: Boolean(slug),
  });

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [citations, setCitations] = useState<ChatCitation[]>([]);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [requestId, setRequestId] = useState<string>("");
  const [runId, setRunId] = useState<string>("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // 切换 Agent 时清空会话，避免与全链路 / 其他 Agent 历史串台
  useEffect(() => {
    setSessionId(null);
    setMessages([]);
    setCitations([]);
    setSteps([]);
    setRequestId("");
    setRunId("");
  }, [agentId, slug]);

  const agentOptions = [
    { value: FULL_CHAIN, label: "全链路（coordinator + handoff）" },
    ...(workspace.data?.agents || []).map((a) => ({
      value: a.agent_id,
      label: `${a.name}（${a.agent_id}）${
        a.role === "coordinator" ? " · 协调" : " · 单测"
      }`,
    })),
  ];

  const selectedAgent = (workspace.data?.agents || []).find(
    (a) => a.agent_id === agentId,
  );
  const titleSuffix = selectedAgent
    ? ` · ${selectedAgent.agent_id}`
    : agentId
      ? ` · ${agentId}`
      : " · 全链路";

  const onAgentChange = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) {
      next.set("agent_id", value);
    } else {
      next.delete("agent_id");
    }
    setSearchParams(next, { replace: true });
  };

  const send = async () => {
    if (!slug || !input.trim()) {
      message.warning("缺少应用空间或问题为空");
      return;
    }
    const userText = input.trim();
    setInput("");
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userText },
      { role: "assistant", content: "" },
    ]);
    setCitations([]);
    setSteps([]);
    setStreaming(true);
    abortRef.current = new AbortController();

    try {
      await streamChatCompletions(
        {
          slug,
          session_id: sessionId,
          message: userText,
          agent_id: agentId || null,
        },
        {
          onDelta: (text) => {
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last?.role === "assistant") {
                next[next.length - 1] = { ...last, content: last.content + text };
              }
              return next;
            });
          },
          onCitation: (c) => setCitations((prev) => [...prev, c]),
          onStep: (step) => {
            setSteps((prev) => [...prev, step]);
            if (slug === "script-workshop" && step.type === "tool") {
              const args = (step.args || {}) as Record<string, unknown>;
              const bc = new BroadcastChannel(CANVAS_STEP_CHANNEL);
              bc.postMessage({
                spaceId:
                  typeof args.narrative_space_id === "string"
                    ? args.narrative_space_id
                    : null,
                projectId:
                  typeof args.project_id === "string" ? args.project_id : null,
                step,
              });
              bc.close();
            }
          },
          onDone: (payload) => {
            setSessionId(payload.session_id);
            setRequestId(payload.request_id);
            if (payload.run_id) setRunId(payload.run_id);
          },
          onError: (err) => message.error(err.message || err.code),
        },
        abortRef.current.signal,
      );
    } catch (e: unknown) {
      if ((e as Error).name !== "AbortError") {
        message.error((e as Error).message || "请求失败");
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const reloadRun = async () => {
    const id = runId || requestId;
    if (!id) {
      message.warning("尚无 run / request");
      return;
    }
    try {
      const data = await getAgentRun(id);
      setRunId(data.id);
      setSteps(data.steps || []);
      message.success("已加载历史轨迹");
    } catch (e: unknown) {
      message.error((e as Error).message || "加载轨迹失败");
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button onClick={() => navigate("/apps")}>返回应用空间</Button>
        <Button onClick={() => navigate(`/apps/${slug}`)}>查看配置</Button>
        <Button onClick={reloadRun} disabled={!runId && !requestId}>
          刷新轨迹
        </Button>
        <Select
          style={{ minWidth: 280 }}
          value={agentId}
          options={agentOptions}
          onChange={onAgentChange}
          disabled={streaming || workspace.isLoading}
          placeholder="选择调试目标"
        />
      </Space>
      <Typography.Title level={3}>
        调试台 · {slug}
        {titleSuffix}
      </Typography.Title>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {selectedAgent?.role === "specialist"
          ? "单 Agent 模式：仅加载该 Agent 工具，无 delegate_to_*。"
          : "全链路 / 协调模式：coordinator 可通过 handoff 委派专业 Agent。"}{" "}
        session: {sessionId || "-"} / run: {runId || "-"} / request: {requestId || "-"}
      </Typography.Paragraph>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 16 }}>
        <Card title="对话" styles={{ body: { minHeight: 420 } }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 16 }}>
            {messages.map((m, idx) => (
              <div key={idx}>
                <Typography.Text strong>{m.role === "user" ? "用户" : "助手"}</Typography.Text>
                <div style={{ whiteSpace: "pre-wrap" }}>
                  {m.content || (streaming ? "..." : "")}
                </div>
              </div>
            ))}
          </div>
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={3}
            placeholder={
              selectedAgent
                ? `向 ${selectedAgent.name} 发任务…`
                : "输入问题（全链路由协调 Agent 调度）"
            }
            disabled={streaming}
          />
          <Space style={{ marginTop: 12 }}>
            <Button type="primary" loading={streaming} onClick={send}>
              发送（流式）
            </Button>
            <Button disabled={!streaming} onClick={() => abortRef.current?.abort()}>
              取消
            </Button>
          </Space>
        </Card>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <Card title="运行轨迹" styles={{ body: { maxHeight: 360, overflow: "auto" } }}>
            {steps.length === 0 ? (
              <Typography.Text type="secondary">等待工具调用与思考步骤…</Typography.Text>
            ) : (
              <Timeline items={steps.map((s) => formatStep(s))} />
            )}
          </Card>
          <Card title="引用" styles={{ body: { maxHeight: 200, overflow: "auto" } }}>
            {citations.length === 0 ? (
              <Typography.Text type="secondary">暂无引用</Typography.Text>
            ) : (
              citations.map((c, i) => (
                <div key={`${c.chunk_id}-${i}`} style={{ marginBottom: 12 }}>
                  <Typography.Text type="secondary">
                    #{i + 1} score={c.score?.toFixed?.(4) ?? c.score}
                  </Typography.Text>
                  <div style={{ whiteSpace: "pre-wrap" }}>{c.content}</div>
                </div>
              ))
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
