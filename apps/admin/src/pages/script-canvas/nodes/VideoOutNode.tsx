import type { NodeProps } from "@xyflow/react";
import { PlayCircleOutlined } from "@ant-design/icons";
import { MediaPlaceholder } from "../components/MediaPlaceholder";
import { NodeActionBar } from "../components/NodeActionBar";
import { NodeCardHeader } from "../components/NodeCardHeader";
import { NodeCardShell } from "../components/NodeCardShell";
import { StatusBadges } from "../components/StatusBadges";
import { canvasTokens } from "../theme/tokens";
import { buildNodeActions, type NarrativeNodeData } from "./types";

/** 成片节点：16:9 预览区 + 主按钮生视频。 */
export function VideoOutNode({ data, selected }: NodeProps) {
  const d = data as NarrativeNodeData;
  const accent = canvasTokens.accent.video_out;
  const size = canvasTokens.media.video_out;
  const title = d.label || d.title || "成片视频";

  return (
    <NodeCardShell selected={selected} minWidth={size.width + 24}>
      <NodeCardHeader
        kindLabel="成片"
        title={title}
        accent={accent}
        icon={<PlayCircleOutlined />}
        badges={
          <StatusBadges recordStatus={d.record_status} status={d.status} />
        }
      />
      <div style={{ padding: "0 12px 8px" }}>
        <MediaPlaceholder
          width={size.width}
          height={size.height}
          hint="生成并确认提示词后可出片"
          accent={accent}
          previewUrl={d.preview_url}
        />
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
