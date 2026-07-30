import type { NodeTypes } from "@xyflow/react";
import { CharacterNode } from "./CharacterNode";
import { PropNode } from "./PropNode";
import { ShotNode } from "./ShotNode";
import { VideoOutNode } from "./VideoOutNode";

export type { NarrativeNodeData, NarrativeNodeKind } from "./types";
export { buildNodeActions } from "./types";

/** 叙事空间画布节点类型注册表。 */
export const narrativeNodeTypes: NodeTypes = {
  character: CharacterNode,
  prop: PropNode,
  shot: ShotNode,
  video_out: VideoOutNode,
};
