/** 画布节点数据契约（与 bootstrap / 自动保存共用）。 */
export type NarrativeNodeKind = "character" | "prop" | "shot" | "video_out";

export type NarrativeNodeData = {
  kind: NarrativeNodeKind;
  entity_id?: string;
  video_prompt_id?: string;
  video_segment_id?: string;
  narrative_space_id?: string;
  label?: string;
  beat?: string;
  title?: string;
  /** 物料图 / 成片预览（有则展示） */
  preview_url?: string;
  record_status?: string;
  status?: "idle" | "running" | "done" | "failed" | string;
  error?: string;
  onAction?: (action: string, data: NarrativeNodeData) => void;
};

export type NodeAction = {
  key: string;
  label: string;
  primary?: boolean;
};

export function buildNodeActions(d: NarrativeNodeData): NodeAction[] {
  const actions: NodeAction[] = [];
  if (d.kind === "character" || d.kind === "prop") {
    if (d.record_status !== "confirmed") {
      actions.push({ key: "confirm_asset", label: "确认" });
    }
    actions.push({ key: "gen_material", label: "生成物料提示词" });
    actions.push({
      key: "open_material_confirm",
      label: "查看物料提示词",
      primary: true,
    });
  }
  if (d.kind === "shot") {
    if (d.record_status !== "confirmed") {
      actions.push({ key: "confirm_shot", label: "确认" });
    }
    actions.push({ key: "plan_shots", label: "重规划分镜" });
  }
  if (d.kind === "video_out") {
    if (!d.video_prompt_id) {
      actions.push({
        key: "gen_video_prompt",
        label: "生成成片提示词",
        primary: true,
      });
    } else {
      actions.push({
        key: "open_video_confirm",
        label: "确认并生成",
        primary: true,
      });
    }
  }
  return actions;
}
