import {
  Button,
  Card,
  Input,
  Select,
  Space,
  Tag,
  Timeline,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getAgentRun,
  streamChatCompletions,
  type AgentStep,
  type ChatCitation,
  type ChatSelection,
} from "../../api/chat";
import {
  getScriptStructure,
  listScriptProjects,
  listVideoSegments,
  type NarrativeSpace,
} from "../../api/business/scriptBiz";
import { getWorkspace } from "../../api/resources";
import { CANVAS_STEP_CHANNEL } from "../business/script-canvas/sync/applyAgentStep";
import {
  listFixtures,
  removeFixture,
  upsertFixture,
  type PlaygroundFixture,
} from "./playgroundFixtures";

type Msg = { role: "user" | "assistant"; content: string };

const FULL_CHAIN = "";
const BIZ_SLUG = "script-workshop";

function patchLastAssistant(prev: Msg[], content: string): Msg[] {
  const next = [...prev];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === "assistant") {
      next[i] = { role: "assistant", content };
      return next;
    }
  }
  next.push({ role: "assistant", content });
  return next;
}

function formatStep(step: AgentStep): { color?: string; children: ReactNode } {
  if (step.type === "reasoning") {
    return {
      color: "purple",
      children: (
        <div>
          <Typography.Text strong>[{step.agent_id}] 思考过程</Typography.Text>
          <div style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>
            {step.output || "-"}
          </div>
        </div>
      ),
    };
  }
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

function buildSelection(args: {
  projectId?: string;
  spaceId?: string;
  segmentId?: string;
  spaces: NarrativeSpace[];
  segmentTitle?: string;
}): ChatSelection | null {
  const { projectId, spaceId, segmentId, spaces, segmentTitle } = args;
  if (!projectId) return null;
  if (segmentId && spaceId) {
    const space = spaces.find((s) => s.id === spaceId);
    return {
      project_id: projectId,
      selection: {
        type: "video_segment",
        id: segmentId,
        video_segment_id: segmentId,
        narrative_space_id: spaceId,
        episode_id: space?.episode_id,
        title: segmentTitle || "视频片段",
      },
    };
  }
  if (spaceId) {
    const space = spaces.find((s) => s.id === spaceId);
    return {
      project_id: projectId,
      selection: {
        type: "narrative_space",
        id: spaceId,
        narrative_space_id: spaceId,
        episode_id: space?.episode_id,
        title: space?.title || "叙事空间",
      },
    };
  }
  return {
    project_id: projectId,
    selection: {
      type: "project",
      id: projectId,
      project_id: projectId,
      title: "当前项目",
    },
  };
}

export function PlaygroundPage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const agentId = searchParams.get("agent_id") || FULL_CHAIN;
  const isBizApp = slug === BIZ_SLUG;

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

  const [projectId, setProjectId] = useState<string | undefined>();
  const [spaceId, setSpaceId] = useState<string | undefined>();
  const [segmentId, setSegmentId] = useState<string | undefined>();
  const [fixtures, setFixtures] = useState<PlaygroundFixture[]>([]);
  const [fixtureId, setFixtureId] = useState<string | undefined>();

  useEffect(() => {
    setFixtures(listFixtures(slug));
    setFixtureId(undefined);
  }, [slug]);

  // 切换 Agent 时清空会话，避免与全链路 / 其他 Agent 历史串台
  useEffect(() => {
    setSessionId(null);
    setMessages([]);
    setCitations([]);
    setSteps([]);
    setRequestId("");
    setRunId("");
  }, [agentId, slug]);

  const projects = useQuery({
    queryKey: ["script-projects"],
    queryFn: listScriptProjects,
    enabled: isBizApp,
  });

  const structure = useQuery({
    queryKey: ["script-structure", projectId],
    queryFn: () => getScriptStructure(projectId!),
    enabled: isBizApp && Boolean(projectId),
  });

  const spaces = useMemo(() => {
    const items: NarrativeSpace[] = [];
    for (const ep of structure.data?.items || []) {
      for (const ns of ep.narrative_spaces || []) {
        items.push(ns);
      }
    }
    return items;
  }, [structure.data]);

  const spaceOptions = useMemo(
    () =>
      (structure.data?.items || []).flatMap((ep) =>
        (ep.narrative_spaces || []).map((ns) => ({
          value: ns.id,
          label: `第${ep.ordinal}集 · ${ns.title || ns.id.slice(-6)}`,
        })),
      ),
    [structure.data],
  );

  const segments = useQuery({
    queryKey: ["script-segments", projectId, spaceId],
    queryFn: () => listVideoSegments(projectId!, spaceId),
    enabled: isBizApp && Boolean(projectId) && Boolean(spaceId),
  });

  const selection = useMemo(
    () =>
      buildSelection({
        projectId,
        spaceId,
        segmentId,
        spaces,
        segmentTitle: segments.data?.items.find((s) => s.id === segmentId)?.title,
      }),
    [projectId, spaceId, segmentId, spaces, segments.data],
  );

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
  const coordinatorAgent = (workspace.data?.agents || []).find(
    (a) => a.role === "coordinator",
  );
  // 全链路时展示协调 Agent 的内置提示词
  const samplePrompts =
    selectedAgent?.sample_prompts ||
    (!agentId ? coordinatorAgent?.sample_prompts : undefined) ||
    [];
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

  const applyFixture = (id: string) => {
    const fx = fixtures.find((f) => f.id === id);
    if (!fx) return;
    setFixtureId(id);
    const sel = fx.selection;
    const nested = sel.selection;
    const pid = sel.project_id || nested?.id;
    setProjectId(typeof pid === "string" ? pid : undefined);
    const ns =
      nested?.narrative_space_id ||
      (nested?.type === "narrative_space" ? nested.id : undefined);
    setSpaceId(typeof ns === "string" ? ns : undefined);
    const vs =
      nested?.video_segment_id ||
      (nested?.type === "video_segment" ? nested.id : undefined);
    setSegmentId(typeof vs === "string" ? vs : undefined);
    if (fx.sample_message) setInput(fx.sample_message);
    if (fx.agent_id != null) {
      onAgentChange(fx.agent_id || "");
    }
    message.success(`已应用夹具：${fx.name}`);
  };

  const saveFixture = () => {
    if (!selection?.project_id) {
      message.warning("请先选择项目再保存夹具");
      return;
    }
    const defaultName =
      (fixtureId
        ? fixtures.find((f) => f.id === fixtureId)?.name
        : "") || `夹具 ${new Date().toLocaleString()}`;
    const name = window.prompt("夹具名称", defaultName);
    if (name == null) return;
    const finalName = name.trim() || defaultName;
    const saved = upsertFixture(slug, {
      id: fixtureId,
      name: finalName,
      agent_id: agentId || null,
      sample_message: input,
      selection,
    });
    setFixtures(listFixtures(slug));
    setFixtureId(saved.id);
    message.success("夹具已保存");
  };

  const deleteFixture = () => {
    if (!fixtureId) {
      message.warning("请先选择夹具");
      return;
    }
    removeFixture(slug, fixtureId);
    setFixtures(listFixtures(slug));
    setFixtureId(undefined);
    message.success("已删除夹具");
  };

  const send = async () => {
    if (!slug || !input.trim()) {
      message.warning("缺少应用空间或问题为空");
      return;
    }
    if (isBizApp && !projectId) {
      message.info("未选项目：纯对话可用，业务工具通常需要先选项目");
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
          selection: selection || null,
        },
        {
          onReasoning: (text) => {
            setSteps((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last?.type === "reasoning") {
                next[next.length - 1] = {
                  ...last,
                  output: (last.output || "") + text,
                };
                return next;
              }
              next.push({
                step_no: next.length + 1,
                agent_id: agentId || "router",
                type: "reasoning",
                output: text,
              });
              return next;
            });
          },
          onDelta: (text) => {
            setMessages((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i -= 1) {
                if (next[i].role === "assistant") {
                  next[i] = {
                    role: "assistant",
                    content: next[i].content + text,
                  };
                  return next;
                }
              }
              return patchLastAssistant(prev, text);
            });
          },
          onCitation: (c) => setCitations((prev) => [...prev, c]),
          onStep: (step) => {
            setSteps((prev) => [...prev, step]);
            if (slug === "script-workshop" && step.type === "tool") {
              const args = (step.args || {}) as Record<string, unknown>;
              const bc = new BroadcastChannel(CANVAS_STEP_CHANNEL);
              bc.postMessage({
                segmentId:
                  typeof args.video_segment_id === "string"
                    ? args.video_segment_id
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
        可配置测试上下文与命名夹具。 session: {sessionId || "-"} / run:{" "}
        {runId || "-"} / request: {requestId || "-"}
      </Typography.Paragraph>

      <Card title="测试上下文" size="small" style={{ marginBottom: 16 }}>
        {isBizApp ? (
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            <Space wrap>
              <Select
                style={{ width: 220 }}
                placeholder="项目"
                allowClear
                loading={projects.isLoading}
                value={projectId}
                options={(projects.data?.items || []).map((p) => ({
                  value: p.id,
                  label: p.name,
                }))}
                onChange={(v) => {
                  setProjectId(v);
                  setSpaceId(undefined);
                  setSegmentId(undefined);
                }}
              />
              <Select
                style={{ width: 280 }}
                placeholder="叙事空间"
                allowClear
                disabled={!projectId}
                loading={structure.isLoading}
                value={spaceId}
                options={spaceOptions}
                onChange={(v) => {
                  setSpaceId(v);
                  setSegmentId(undefined);
                }}
              />
              <Select
                style={{ width: 220 }}
                placeholder="视频片段（可选）"
                allowClear
                disabled={!spaceId}
                loading={segments.isLoading}
                value={segmentId}
                options={(segments.data?.items || []).map((s) => ({
                  value: s.id,
                  label: `${s.ordinal}. ${s.title || s.id.slice(-6)}`,
                }))}
                onChange={setSegmentId}
              />
            </Space>
            <Space wrap>
              <Select
                style={{ width: 240 }}
                placeholder="命名测试夹具"
                allowClear
                value={fixtureId}
                options={fixtures.map((f) => ({
                  value: f.id,
                  label: f.name,
                }))}
                onChange={(id) => {
                  if (id) applyFixture(id);
                  else setFixtureId(undefined);
                }}
              />
              <Button onClick={() => fixtureId && applyFixture(fixtureId)} disabled={!fixtureId}>
                应用夹具
              </Button>
              <Button type="primary" ghost onClick={saveFixture}>
                保存当前为夹具
              </Button>
              <Button danger onClick={deleteFixture} disabled={!fixtureId}>
                删除夹具
              </Button>
            </Space>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              发送时注入 selection
              {selection
                ? `：${selection.selection?.type || "project"} / ${selection.selection?.id || selection.project_id}`
                : "（未选项目）"}
              。夹具保存在本机浏览器。
            </Typography.Text>
          </Space>
        ) : (
          <Typography.Text type="secondary">
            当前应用无业务 selection；可直接对话调试 Agent。
          </Typography.Text>
        )}
      </Card>

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
          {samplePrompts.length > 0 ? (
            <div style={{ marginBottom: 12 }}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                内置单测提示词（点击填入，可再编辑后发送）：
              </Typography.Text>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                {samplePrompts.map((p) => (
                  <Tag
                    key={p}
                    style={{ cursor: streaming ? "not-allowed" : "pointer", marginInlineEnd: 0 }}
                    onClick={() => {
                      if (streaming) return;
                      setInput(p);
                    }}
                  >
                    {p.length > 36 ? `${p.slice(0, 36)}…` : p}
                  </Tag>
                ))}
              </div>
            </div>
          ) : null}
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
            <Button type="primary" loading={streaming} onClick={() => void send()}>
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
