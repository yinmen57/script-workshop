/** 工作台选中对象：传给右侧对话的结构化 selection。 */

export type WorkspaceTab = "video" | "material";

/** 顶层模式：工作台（事实编辑）与知识库（检索副本）分离 */
export type WorkspaceMode = "workspace" | "knowledge";

export type SelectionType =
  | "project"
  | "episode"
  | "narrative_space"
  | "video_segment"
  | "shot"
  | "character"
  | "prop"
  | "scene_space"
  | "material_prompt"
  | "material_image";

export type WorkspaceSelection = {
  type: SelectionType;
  id: string;
  project_id: string;
  episode_id?: string;
  narrative_space_id?: string;
  video_segment_id?: string;
  shot_id?: string;
  title?: string;
};

export type ChatSelectionPayload = {
  project_id: string;
  selection: WorkspaceSelection;
};
