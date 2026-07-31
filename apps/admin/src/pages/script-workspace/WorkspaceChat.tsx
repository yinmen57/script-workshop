/**
 * 右栏对话：多轮消息 + step 轨迹，携带结构化 selection。
 */
import { Button, Input, Space, Typography } from "antd";
import { useRef, useState } from "react";
import {
  streamChatCompletions,
  type AgentStep,
} from "../../api/chat";
import type { WorkspaceSelection } from "./types";

const SLUG = "script-workshop";

type ChatMsg =
  | { role: "user" | "assistant"; content: string }
  | { role: "step"; content: string };

type Props = {
  projectId: string | null;
  selection: WorkspaceSelection | null;
  onStep?: (step: AgentStep) => void;
};

export function WorkspaceChat({ projectId, selection, onStep }: Props) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const assistantBuf = useRef("");

  const send = async () => {
    const text = input.trim();
    if (!text || streaming || !projectId) return;
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
            const label = step.tool_id || step.type || "step";
            const detail = step.error || step.output || "";
            setMessages((prev) => [
              ...prev,
              {
                role: "step",
                content: `${label}${detail ? ` · ${String(detail).slice(0, 120)}` : ""}`,
              },
            ]);
          },
          onDone: (payload) => setSessionId(payload.session_id),
        },
        abortRef.current.signal,
      );
    } catch (e) {
      const err = e instanceof Error ? e.message : "对话失败";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: err },
      ]);
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
      </div>
      <div className="script-workspace__chat-messages">
        {!projectId ? (
          <Typography.Text type="secondary">请先选择项目</Typography.Text>
        ) : !messages.length ? (
          <Typography.Text type="secondary">
            描述目标即可，例如「把第 1 集语义切分」或「为当前空间规划分镜」。模糊目标会先走工具选择 Agent。
          </Typography.Text>
        ) : (
          messages.map((m, i) => (
            <div
              key={`${m.role}-${i}`}
              className={
                m.role === "user"
                  ? "script-workspace__msg script-workspace__msg--user"
                  : m.role === "step"
                    ? "script-workspace__msg script-workspace__msg--step"
                    : "script-workspace__msg script-workspace__msg--assistant"
              }
            >
              {m.content || (streaming && m.role === "assistant" ? "…" : "")}
            </div>
          ))
        )}
      </div>
      <div className="script-workspace__chat-input">
        <Space.Compact style={{ width: "100%" }}>
          <Input
            value={input}
            disabled={streaming || !projectId}
            placeholder={projectId ? "输入指令…" : "请先选择项目"}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => void send()}
          />
          <Button
            type="primary"
            loading={streaming}
            disabled={!projectId}
            onClick={() => void send()}
          >
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  );
}
