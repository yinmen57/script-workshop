import type { NodeProps } from "@xyflow/react";
import { GiftOutlined } from "@ant-design/icons";
import { MediaPlaceholder } from "../components/MediaPlaceholder";
import { NodeActionBar } from "../components/NodeActionBar";
import { NodeCardHeader } from "../components/NodeCardHeader";
import { NodeCardShell } from "../components/NodeCardShell";
import { StatusBadges } from "../components/StatusBadges";
import { canvasTokens } from "../theme/tokens";
import { buildNodeActions, type NarrativeNodeData } from "./types";

/** 道具节点：方图媒体区。 */
export function PropNode({ data, selected }: NodeProps) {
  const d = data as NarrativeNodeData;
  const accent = canvasTokens.accent.prop;
  const size = canvasTokens.media.prop;
  const title = d.label || d.entity_id || "道具";

  return (
    <NodeCardShell selected={selected} minWidth={size.width + 24}>
      <NodeCardHeader
        kindLabel="道具"
        title={title}
        accent={accent}
        icon={<GiftOutlined />}
        badges={
          <StatusBadges recordStatus={d.record_status} status={d.status} />
        }
      />
      <div style={{ padding: "0 12px 8px" }}>
        <MediaPlaceholder
          width={size.width}
          height={size.height}
          hint="确认后生成物料图"
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
