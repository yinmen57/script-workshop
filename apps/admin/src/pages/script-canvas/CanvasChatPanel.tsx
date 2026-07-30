/**
 * 画布旁对话入口：与调试台共用 streamChatCompletions，
 * step 同步到画布节点（D3 双模式）。
 */
import { Button, Input, Space, Typography } from "antd";
import { useRef, useState } from "react";
import {
  streamChatCompletions,
  type AgentStep,
} from "../../api/chat";

const SLUG = "script-workshop";

type Props = {
  spaceId: string;
  projectId?: string;
  onStep: (step: AgentStep) => void;
};

export function CanvasChatPanel({ spaceId, projectId, onStep }: Props) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [answer, setAnswer] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setAnswer("");
    setStreaming(true);
    abortRef.current = new AbortController();
    const hint = [
      projectId ? `project_id=${projectId}` : "",
      `narrative_space_id=${spaceId}`,
      text,
    ]
      .filter(Boolean)
      .join("\n");
    try {
      await streamChatCompletions(
        { slug: SLUG, session_id: sessionId, message: hint },
        {
          onDelta: (t) => setAnswer((prev) => prev + t),
          onStep: (step) => onStep(step),
          onDone: (payload) => setSessionId(payload.session_id),
        },
        abortRef.current.signal,
      );
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  if (!open) {
    return (
      <Button size="small" onClick={() => setOpen(true)}>
        对话模式
      </Button>
    );
  }

  return (
    <div
      style={{
        width: 320,
        maxHeight: "70vh",
        overflow: "auto",
        background: "#fff",
        border: "1px solid #f0f0f0",
        borderRadius: 8,
        padding: 12,
      }}
    >
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 8 }}>
        <Typography.Text strong>对话模式</Typography.Text>
        <Button size="small" type="link" onClick={() => setOpen(false)}>
          收起
        </Button>
      </Space>
      <Typography.Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        与画布共用工具；轨迹 step 会刷新节点状态。
      </Typography.Paragraph>
      <div
        style={{
          minHeight: 80,
          maxHeight: 200,
          overflow: "auto",
          whiteSpace: "pre-wrap",
          fontSize: 13,
          marginBottom: 8,
          background: "#fafafa",
          padding: 8,
          borderRadius: 6,
        }}
      >
        {answer || (streaming ? "…" : "回复将显示在此")}
      </div>
      <Space.Compact style={{ width: "100%" }}>
        <Input
          value={input}
          disabled={streaming}
          placeholder="例如：为本空间生成成片提示词"
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => void send()}
        />
        <Button type="primary" loading={streaming} onClick={() => void send()}>
          发送
        </Button>
      </Space.Compact>
    </div>
  );
}
