/**
 * 右栏对话：SSE 真流式 + 思考/工具时间线 + 按项目持久化会话。
 */
import { Button, Input, Space, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";
import {
  listChatMessages,
  streamChatCompletions,
  type AgentStep,
} from "../../../api/chat";
import type { WorkspaceSelection } from "./types";

const SLUG = "script-workshop";

type ChatMsg =
  | { role: "user" | "assistant"; content: string }
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
  // thought 等
  return String(step.output || "思考中…").slice(0, 240);
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

  // 切换项目：恢复本地 session，并拉历史
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
        // 会话失效则清除本地引用
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
          onDelta: (t) => {
            assistantBuf.current += t;
            const buf = assistantBuf.current;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last?.role === "assistant") {
                next[next.length - 1] = { role: "assistant", content: buf };
              }
              return next;
            });
          },
          onStep: (step) => {
            onStep?.(step);
            // thought 若与正在流式的 assistant 文本重复，仍保留时间线便于看见过程
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
            // 若全程无 token delta，用最终 answer 填满空助手气泡
            if (!assistantBuf.current && payload.answer) {
              assistantBuf.current = payload.answer;
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  next[next.length - 1] = {
                    role: "assistant",
                    content: payload.answer,
                  };
                }
                return next;
              });
            }
          },
          onError: (payload) => {
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: payload.message || "对话失败",
              },
            ]);
          },
        },
        abortRef.current.signal,
      );
    } catch (e) {
      if ((e as Error)?.name === "AbortError") return;
      const err = e instanceof Error ? e.message : "对话失败";
      setMessages((prev) => [...prev, { role: "assistant", content: err }]);
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
            描述目标即可，例如「把第 1 集语义切分」或「为当前空间规划分镜」。过程中会流式显示思考与工具步骤；刷新后自动恢复本项目会话。
          </Typography.Text>
        ) : (
          messages.map((m, i) => {
            if (m.role === "step") {
              const isTool =
                m.stepType === "tool" || m.stepType === "tool_start";
              return (
                <div
                  key={`step-${i}`}
                  className="script-workspace__msg script-workspace__msg--step"
                >
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    [{m.agentId || "?"}]{" "}
                    {isTool ? "工具" : "思考"}
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
            return (
              <div
                key={`${m.role}-${i}`}
                className={
                  m.role === "user"
                    ? "script-workspace__msg script-workspace__msg--user"
                    : "script-workspace__msg script-workspace__msg--assistant"
                }
              >
                {m.content ||
                  (streaming && m.role === "assistant" ? "思考中…" : "")}
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
              // 中文输入法组字中按 Enter 不发送
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
