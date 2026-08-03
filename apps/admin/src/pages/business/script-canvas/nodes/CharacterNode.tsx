import type { NodeProps } from "@xyflow/react";
import { UserOutlined } from "@ant-design/icons";
import { MediaPlaceholder } from "../components/MediaPlaceholder";
import { NodeActionBar } from "../components/NodeActionBar";
import { NodeCardHeader } from "../components/NodeCardHeader";
import { NodeCardShell } from "../components/NodeCardShell";
import { StatusBadges } from "../components/StatusBadges";
import { canvasTokens } from "../theme/tokens";
import { buildNodeActions, type NarrativeNodeData } from "./types";

/** 人物节点：竖图媒体区（对齐参考 image 壳）。 */
export function CharacterNode({ data, selected }: NodeProps) {
  const d = data as NarrativeNodeData;
  const accent = canvasTokens.accent.character;
  const size = canvasTokens.media.character;
  const title = d.label || d.entity_id || "人物";

  return (
    <NodeCardShell selected={selected} minWidth={size.width + 24}>
      <NodeCardHeader
        kindLabel="人物"
        title={title}
        accent={accent}
        icon={<UserOutlined />}
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
