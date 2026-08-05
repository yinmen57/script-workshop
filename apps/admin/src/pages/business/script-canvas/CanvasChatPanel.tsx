/**
 * 画布旁对话入口：与调试台共用 streamChatCompletions，
 * step 同步到画布节点（双模式）。
 * 选中上下文以 selection 结构化传递，不再拼进用户原文。
 */
import { Button, Collapse, Input, Space, Typography } from "antd";
import { useRef, useState } from "react";
import {
  streamChatCompletions,
  type AgentStep,
} from "../../../api/chat";

function reasoningLabel(text: string): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (!oneLine) return "思考过程";
  const preview = oneLine.slice(0, 48);
  return oneLine.length > 48
    ? `思考过程 · ${preview}…`
    : `思考过程 · ${preview}`;
}

const SLUG = "script-workshop";

type Props = {
  segmentId: string;
  narrativeSpaceId?: string;
  projectId?: string;
  onStep: (step: AgentStep) => void;
};

export function CanvasChatPanel({
  segmentId,
  narrativeSpaceId,
  projectId,
  onStep,
}: Props) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [answer, setAnswer] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    setAnswer("");
    setReasoning("");
    setStreaming(true);
    abortRef.current = new AbortController();
    try {
      await streamChatCompletions(
        {
          slug: SLUG,
          session_id: sessionId,
          message: text,
          selection: {
            project_id: projectId,
            selection: {
              type: "video_segment",
              id: segmentId,
              video_segment_id: segmentId,
              narrative_space_id: narrativeSpaceId,
              title: "当前画布视频片段",
            },
          },
        },
        {
          onReasoning: (t) => setReasoning((prev) => prev + t),
          onDelta: (t) => setAnswer((prev) => prev + t),
          onStep: (step) => onStep(step),
          onDone: (payload) => setSessionId(payload.session_id),
          onError: (err) => setAnswer(err.message || "对话失败"),
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
        与画布共用工具；当前视频片段（≤15s）已作为 selection 传入。
      </Typography.Paragraph>
      {projectId ? (
        <Typography.Text type="secondary" style={{ fontSize: 11, display: "block", marginBottom: 8 }}>
          选中：片段 {segmentId}
        </Typography.Text>
      ) : null}
      <div
        style={{
          minHeight: 80,
          maxHeight: 280,
          overflow: "auto",
          fontSize: 13,
          marginBottom: 8,
          background: "#fafafa",
          padding: 8,
          borderRadius: 6,
        }}
      >
        {reasoning ? (
          <Collapse
            ghost
            size="small"
            style={{ marginBottom: 6 }}
            items={[
              {
                key: "reasoning",
                label: (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {reasoningLabel(reasoning)}
                  </Typography.Text>
                ),
                children: (
                  <div
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: 12,
                      color: "#64748b",
                      maxHeight: 140,
                      overflow: "auto",
                    }}
                  >
                    {reasoning}
                  </div>
                ),
              },
            ]}
          />
        ) : null}
        <div style={{ whiteSpace: "pre-wrap" }}>
          {answer ||
            (streaming ? (reasoning ? "等待回复…" : "…") : "回复将显示在此")}
        </div>
      </div>
      <Space.Compact style={{ width: "100%" }}>
        <Input
          value={input}
          disabled={streaming}
          placeholder="例如：为本片段生成成片提示词"
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
