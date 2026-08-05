/**
 * 对话 SSE event:step → 画布节点状态（双模式）。
 * 工具 id 与画布按钮共用同一套业务能力。
 */
import type { Node } from "@xyflow/react";
import type { AgentStep } from "../../../../api/chat";
import type { NarrativeNodeData } from "../nodes/types";

export const CANVAS_STEP_CHANNEL = "script-canvas-steps";

export type CanvasStepMessage = {
  segmentId?: string | null;
  projectId?: string | null;
  step: AgentStep;
};

/** 工具开始前可先标 running；当前 SSE 多为完成后一步，直接标终态。 */
export function applyAgentStepToNodes(
  nodes: Node[],
  step: AgentStep,
  opts: { segmentId: string; projectId?: string },
): Node[] {
  if (step.type !== "tool" || !step.tool_id) return nodes;
  const args = (step.args || {}) as Record<string, unknown>;
  const argSeg =
    typeof args.video_segment_id === "string" ? args.video_segment_id : null;
  // 带片段参数时只同步当前画布
  if (argSeg && argSeg !== opts.segmentId) return nodes;

  const status: NarrativeNodeData["status"] = step.error ? "failed" : "done";
  const error = step.error || undefined;
  const tool = step.tool_id;

  const matchKinds = (kinds: NarrativeNodeData["kind"][]) =>
    nodes.map((n) => {
      const data = n.data as NarrativeNodeData;
      if (!kinds.includes(data.kind)) return n;
      return {
        ...n,
        data: { ...data, status, error },
      };
    });

  if (tool === "generate-material-prompts" || tool === "render-material-image") {
    return matchKinds(["character", "prop"]);
  }
  if (tool === "plan-shots") {
    return matchKinds(["shot"]);
  }
  if (
    tool === "generate-video-prompts" ||
    tool === "render-video" ||
    tool === "confirm-video-prompt"
  ) {
    return matchKinds(["video_out"]);
  }
  return nodes;
}
