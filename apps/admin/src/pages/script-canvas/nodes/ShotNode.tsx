import type { NodeProps } from "@xyflow/react";
import { VideoCameraOutlined } from "@ant-design/icons";
import { NodeActionBar } from "../components/NodeActionBar";
import { NodeCardHeader } from "../components/NodeCardHeader";
import { NodeCardShell } from "../components/NodeCardShell";
import { StatusBadges } from "../components/StatusBadges";
import { canvasTokens } from "../theme/tokens";
import { buildNodeActions, type NarrativeNodeData } from "./types";

/** 分镜节点：镜号 + beat 文案区（对齐参考 script 信息密度，单行简化）。 */
export function ShotNode({ data, selected }: NodeProps) {
  const d = data as NarrativeNodeData;
  const accent = canvasTokens.accent.shot;
  const size = canvasTokens.media.shot;
  const title = d.label || "分镜";

  return (
    <NodeCardShell selected={selected} minWidth={size.width + 24}>
      <NodeCardHeader
        kindLabel="分镜"
        title={title}
        accent={accent}
        icon={<VideoCameraOutlined />}
        badges={
          <StatusBadges recordStatus={d.record_status} status={d.status} />
        }
      />
      <div style={{ padding: "0 12px 8px" }}>
        <div
          style={{
            width: size.width,
            minHeight: size.height,
            borderRadius: canvasTokens.mediaRadius,
            background: canvasTokens.emptyBg,
            padding: 10,
            boxSizing: "border-box",
          }}
        >
          <div
            style={{
              fontSize: 10,
              color: accent,
              fontWeight: 600,
              marginBottom: 6,
            }}
          >
            BEAT
          </div>
          <div
            style={{
              fontSize: 12,
              color: canvasTokens.label,
              lineHeight: 1.45,
              display: "-webkit-box",
              WebkitLineClamp: 4,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            {d.beat || "暂无镜头描述"}
          </div>
        </div>
      </div>
      {d.error ? (
        <div style={{ padding: "0 12px 8px", color: "#DC2626", fontSize: 11 }}>
          {d.error}
        </div>
      ) : null}
      <NodeActionBar
        actions={buildNodeActions(d)}
        data={d}
        running={d.status === "running"}
      />
    </NodeCardShell>
  );
}
