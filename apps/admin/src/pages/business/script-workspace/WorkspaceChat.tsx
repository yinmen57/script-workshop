/**
 * 右栏对话：WebSocket 流式 + 思考/工具时间线 + 按项目持久化会话。
 * 思考过程挂在助手气泡上方，默认折叠缩略。
 */
import { Button, Collapse, Input, Space, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";
import {
  listChatMessages,
  streamChatCompletions,
  type AgentStep,
} from "../../../api/chat";
import type { WorkspaceSelection } from "./types";

const SLUG = "script-workshop";

type AssistantMsg = {
  role: "assistant";
  content: string;
  reasoning?: string;
};

type ChatMsg =
  | { role: "user"; content: string }
  | AssistantMsg
  | {
      role: "step";
      stepType: string;
      agentId?: string;
      toolId?: string;
      content: string;
      error?: string | null;
    };

type Props = {
  projectId: string | null;
  selection: WorkspaceSelection | null;
  onStep?: (step: AgentStep) => void;
};

function sessionStorageKey(projectId: string) {
  return `script-workshop:chat-session:${projectId}`;
}

function formatStepLine(step: AgentStep): string {
  if (step.type === "tool_start") {
    return `开始 ${step.tool_id || "tool"}`;
  }
  if (step.type === "tool") {
    const head = `完成 ${step.tool_id || "tool"}`;
    const dur = step.duration_ms != null ? ` · ${step.duration_ms}ms` : "";
    const body = step.error || step.output || "";
    return `${head}${dur}${body ? ` · ${String(body).slice(0, 160)}` : ""}`;
  }
  return String(step.output || "").slice(0, 240);
}

function reasoningLabel(text: string): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (!oneLine) return "思考过程";
  const preview = oneLine.slice(0, 48);
  return oneLine.length > 48
    ? `思考过程 · ${preview}…`
    : `思考过程 · ${preview}`;
}

/** 更新最近一条 assistant，避免 step 插在后面后 delta 画不上去 */
function patchLastAssistant(prev: ChatMsg[], content: string): ChatMsg[] {
  const next = [...prev];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === "assistant") {
      const cur = next[i] as AssistantMsg;
      next[i] = { role: "assistant", content, reasoning: cur.reasoning };
      return next;
    }
  }
  next.push({ role: "assistant", content });
  return next;
}

/** 把思考增量挂到最近一条助手气泡上 */
function appendAssistantReasoning(prev: ChatMsg[], chunk: string): ChatMsg[] {
  const next = [...prev];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === "assistant") {
      const cur = next[i] as AssistantMsg;
      next[i] = {
        role: "assistant",
        content: cur.content,
        reasoning: (cur.reasoning || "") + chunk,
      };
      return next;
    }
  }
  next.push({ role: "assistant", content: "", reasoning: chunk });
  return next;
}

export function WorkspaceChat({ projectId, selection, onStep }: Props) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const assistantBuf = useRef("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
    setInput("");
    assistantBuf.current = "";
    if (!projectId) {
      setSessionId(null);
      setMessages([]);
      return;
    }
    const saved = localStorage.getItem(sessionStorageKey(projectId));
    setSessionId(saved);
    setMessages([]);
    if (!saved) return;
    let cancelled = false;
    setLoadingHistory(true);
    void listChatMessages(saved)
      .then((res) => {
        if (cancelled) return;
        const restored: ChatMsg[] = (res.items || [])
          .filter((m) => m.role === "user" || m.role === "assistant")
          .map((m) => ({
            role: m.role as "user" | "assistant",
            content: m.content || "",
          }));
        setMessages(restored);
      })
      .catch(() => {
        if (cancelled) return;
        localStorage.removeItem(sessionStorageKey(projectId));
        setSessionId(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const startNewSession = () => {
    if (!projectId || streaming) return;
    localStorage.removeItem(sessionStorageKey(projectId));
    setSessionId(null);
    setMessages([]);
  };

  const stop = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);
  };

  const send = async () => {
    const text = input.trim();
    if (!text) return;
    if (!projectId) {
      message.warning("请先在顶栏选择项目，否则不会发起对话请求");
      return;
    }
    if (streaming) {
      message.info("上一轮仍在进行，可点「停止」后重试");
      return;
    }
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setStreaming(true);
    assistantBuf.current = "";
    abortRef.current = new AbortController();
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      await streamChatCompletions(
        {
          slug: SLUG,
          session_id: sessionId,
          message: text,
          selection: {
            project_id: projectId,
            selection: selection || {
              type: "project",
              id: projectId,
              project_id: projectId,
              title: "当前项目",
            },
          },
        },
        {
          onReasoning: (t) => {
            setMessages((prev) => appendAssistantReasoning(prev, t));
          },
          onDelta: (t) => {
            assistantBuf.current += t;
            const buf = assistantBuf.current;
            setMessages((prev) => patchLastAssistant(prev, buf));
          },
          onStep: (step) => {
            onStep?.(step);
            // 思考已挂在助手气泡上，不再单独占一行
            if (step.type === "reasoning") return;
            setMessages((prev) => [
              ...prev,
              {
                role: "step",
                stepType: step.type,
                agentId: step.agent_id,
                toolId: step.tool_id || undefined,
                content: formatStepLine(step),
                error: step.error,
              },
            ]);
          },
          onDone: (payload) => {
            setSessionId(payload.session_id);
            localStorage.setItem(
              sessionStorageKey(projectId),
              payload.session_id,
            );
            if (!assistantBuf.current && payload.answer) {
              assistantBuf.current = payload.answer;
              setMessages((prev) =>
                patchLastAssistant(prev, payload.answer),
              );
            }
          },
          onError: (payload) => {
            setMessages((prev) =>
              patchLastAssistant(prev, payload.message || "对话失败"),
            );
          },
        },
        abortRef.current.signal,
      );
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      const err = e instanceof Error ? e.message : "对话失败";
      setMessages((prev) => patchLastAssistant(prev, err));
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  return (
    <div className="script-workspace__right">
      <div className="script-workspace__panel-title">
        对话
        {selection ? (
          <span className="script-workspace__chip" style={{ marginLeft: 8 }}>
            {selection.type}:{selection.title || selection.id.slice(-6)}
          </span>
        ) : null}
        <Button
          size="small"
          type="link"
          disabled={!projectId || streaming}
          onClick={startNewSession}
          style={{ marginLeft: "auto" }}
        >
          新会话
        </Button>
      </div>
      <div className="script-workspace__chat-messages">
        {!projectId ? (
          <Typography.Text type="secondary">请先选择项目</Typography.Text>
        ) : loadingHistory ? (
          <Typography.Text type="secondary">正在恢复会话…</Typography.Text>
        ) : !messages.length ? (
          <Typography.Text type="secondary">
            描述目标即可，例如「把第 1 集语义切分」。过程经 WebSocket
            流式显示思考与工具步骤；刷新后自动恢复本项目会话。
          </Typography.Text>
        ) : (
          messages.map((m, i) => {
            if (m.role === "step") {
              const isTool =
                m.stepType === "tool" || m.stepType === "tool_start";
              const label = isTool ? "工具" : "步骤";
              return (
                <div
                  key={`step-${i}`}
                  className="script-workspace__msg script-workspace__msg--step"
                >
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    [{m.agentId || "?"}] {label}
                    {m.toolId ? ` · ${m.toolId}` : ""}
                  </Typography.Text>
                  <div style={{ whiteSpace: "pre-wrap", marginTop: 2 }}>
                    {m.content}
                  </div>
                  {m.error ? (
                    <Typography.Text type="danger" style={{ fontSize: 12 }}>
                      {m.error}
                    </Typography.Text>
                  ) : null}
                </div>
              );
            }
            if (m.role === "assistant") {
              return (
                <div
                  key={`assistant-${i}`}
                  className="script-workspace__msg script-workspace__msg--assistant"
                >
                  {m.reasoning ? (
                    <Collapse
                      ghost
                      size="small"
                      className="script-workspace__reasoning"
                      items={[
                        {
                          key: "reasoning",
                          label: reasoningLabel(m.reasoning),
                          children: (
                            <div className="script-workspace__reasoning-body">
                              {m.reasoning}
                            </div>
                          ),
                        },
                      ]}
                    />
                  ) : null}
                  <div className="script-workspace__assistant-body">
                    {m.content ||
                      (streaming ? (m.reasoning ? "等待回复…" : "…") : "")}
                  </div>
                </div>
              );
            }
            return (
              <div
                key={`user-${i}`}
                className="script-workspace__msg script-workspace__msg--user"
              >
                {m.content}
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
      <div className="script-workspace__chat-input">
        <Space.Compact style={{ width: "100%" }}>
          <Input
            value={input}
            disabled={!projectId}
            placeholder={projectId ? "输入指令…" : "请先选择项目后再发送"}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => {
              if (e.nativeEvent.isComposing) return;
              void send();
            }}
          />
          {streaming ? (
            <Button danger onClick={stop}>
              停止
            </Button>
          ) : (
            <Button
              type="primary"
              disabled={!projectId}
              onClick={() => void send()}
            >
              发送
            </Button>
          )}
        </Space.Compact>
      </div>
    </div>
  );
}
