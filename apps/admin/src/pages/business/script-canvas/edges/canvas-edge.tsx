/**
 * 依赖边：蓝色虚线流动 + 透明热区（样式在 theme/canvas.css）。
 */
import { getBezierPath, type EdgeProps } from "@xyflow/react";

export function CanvasEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
}: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  return (
    <>
      <path
        id={id}
        d={edgePath}
        className="react-flow__edge-path script-canvas-edge"
        markerEnd={markerEnd}
      />
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={selected ? 28 : 20}
        style={{ pointerEvents: "stroke" }}
      />
    </>
  );
}
