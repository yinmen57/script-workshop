import type { ReactNode } from "react";
import { Handle, Position } from "@xyflow/react";
import { canvasTokens } from "../theme/tokens";

type Props = {
  selected?: boolean;
  children: ReactNode;
  minWidth?: number;
};

/**
 * 节点外壳：透明外框 + 内容区；左右连接点（样式见 theme/canvas.css）。
 */
export function NodeCardShell({ selected, children, minWidth = 200 }: Props) {
  return (
    <div
      style={{
        position: "relative",
        minWidth,
        borderRadius: canvasTokens.cardRadius,
        background: "transparent",
        overflow: "visible",
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="script-canvas-handle"
      />
      <div
        style={{
          background: "#fff",
          borderRadius: canvasTokens.cardRadius,
          border: `1px solid ${selected ? "transparent" : canvasTokens.panelBorder}`,
          boxShadow: selected
            ? canvasTokens.selectedRing
            : canvasTokens.panelShadow,
          overflow: "hidden",
        }}
      >
        {children}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="script-canvas-handle"
      />
    </div>
  );
}
