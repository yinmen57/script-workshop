/**
 * 善舞风格生成确认节点：引用素材 + 可编辑提示词 + 底栏确认并生成。
 * 用于独立确认画布，画布上仅挂本节点。
 */
import type { NodeProps } from "@xyflow/react";
import { Button, Input, Space, Typography } from "antd";
import { NodeCardShell } from "../components/NodeCardShell";
import { canvasTokens } from "../theme/tokens";

export type GenerationConfirmData = {
  kind: "video" | "image";
  title: string;
  promptText: string;
  negativePrompt?: string;
  refItems: Array<{ id: string; label: string; url?: string }>;
  recordStatus?: string;
  specLabel: string;
  busy?: boolean;
  jobMessage?: string;
  onPromptChange?: (text: string) => void;
  onSave?: () => void;
  onConfirmGenerate?: () => void;
};

const CARD_WIDTH = 520;

export function GenerationConfirmNode({ data, selected }: NodeProps) {
  const d = data as GenerationConfirmData;
  const confirmed = d.recordStatus === "confirmed";
  const primaryLabel = confirmed ? "生成" : "确认并生成";

  return (
    <NodeCardShell selected={selected} minWidth={CARD_WIDTH}>
      <div
        style={{
          width: CARD_WIDTH,
          background: "#fff",
        }}
      >
        <div
          style={{
            padding: "14px 16px 8px",
            borderBottom: `1px solid ${canvasTokens.panelBorder}`,
          }}
        >
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {d.kind === "video" ? "成片生成确认" : "物料生图确认"}
          </Typography.Text>
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              color: canvasTokens.title,
              marginTop: 4,
            }}
          >
            {d.title || "生成节点"}
          </div>
        </div>

        <div style={{ padding: "12px 16px" }} className="nodrag nopan">
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            引用素材
          </Typography.Text>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 8,
              marginTop: 8,
              marginBottom: 12,
            }}
          >
            {(d.refItems || []).length === 0 ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                暂无引用素材
              </Typography.Text>
            ) : (
              d.refItems.map((item) => (
                <div
                  key={item.id}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "4px 10px",
                    borderRadius: 999,
                    background: "#F5F6F8",
                    border: `1px solid ${canvasTokens.panelBorder}`,
                    fontSize: 12,
                  }}
                >
                  {item.url ? (
                    <img
                      src={item.url}
                      alt=""
                      style={{
                        width: 22,
                        height: 22,
                        borderRadius: 4,
                        objectFit: "cover",
                      }}
                    />
                  ) : null}
                  <span>{item.label}</span>
                  <span style={{ color: canvasTokens.connection }}>连线</span>
                </div>
              ))
            )}
          </div>

          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            提示词
          </Typography.Text>
          <Input.TextArea
            className="nodrag nopan"
            value={d.promptText}
            disabled={confirmed || d.busy}
            onChange={(e) => d.onPromptChange?.(e.target.value)}
            rows={10}
            style={{ marginTop: 8, fontSize: 13 }}
          />
          {d.negativePrompt ? (
            <Typography.Paragraph
              type="secondary"
              style={{ fontSize: 11, marginTop: 8, marginBottom: 0 }}
            >
              负向：{d.negativePrompt}
            </Typography.Paragraph>
          ) : null}
        </div>

        <div
          className="nodrag nopan"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            padding: "10px 16px",
            borderTop: `1px solid ${canvasTokens.panelBorder}`,
            background: "#FAFBFC",
          }}
        >
          <div style={{ fontSize: 12, color: canvasTokens.muted }}>
            {d.specLabel}
            {d.jobMessage ? (
              <div style={{ marginTop: 2, color: canvasTokens.brand }}>
                {d.jobMessage}
              </div>
            ) : null}
          </div>
          <Space>
            {!confirmed ? (
              <Button size="small" disabled={d.busy} onClick={() => d.onSave?.()}>
                保存修改
              </Button>
            ) : null}
            <Button
              type="primary"
              size="small"
              loading={d.busy}
              style={{
                background: canvasTokens.brand,
                borderColor: canvasTokens.brand,
                borderRadius: 999,
                minWidth: 108,
              }}
              onClick={() => d.onConfirmGenerate?.()}
            >
              {primaryLabel}
            </Button>
          </Space>
        </div>
      </div>
    </NodeCardShell>
  );
}
