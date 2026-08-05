import { api } from "./client";

export type PageResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type AppItem = {
  slug: string;
  name: string;
  description?: string;
  workspace_path: string;
  coordinator_agent_id?: string;
  agent_count?: number;
  load_status: string;
  validation_error?: string | null;
  loaded_at?: string | null;
};

export type WorkspaceAgent = {
  agent_id: string;
  name: string;
  role: "coordinator" | "specialist" | string;
  description?: string;
  system_prompt_path: string;
  allowed_tools: string[];
  namespaces: string[];
  max_steps: number;
  thinking?: boolean;
  /** 调试台单测内置触发提示词 */
  sample_prompts?: string[];
  source_path: string;
  prompts: Array<{
    prompt_key: string;
    source_path: string;
    content: string;
  }>;
};

export type WorkspaceKnowledge = {
  namespace: string;
  dir: string;
  description: string;
  entry_count: number;
  source_path: string;
  used_by_agents: string[];
  indexed: boolean;
  chunk_count?: number | null;
  dimension?: number | null;
  indexed_at?: string | null;
};

export type AgentWorkspace = {
  slug: string;
  name: string;
  description?: string;
  workspace_path: string;
  coordinator_agent_id: string;
  collaboration_mode?: string;
  load_status: string;
  validation_error?: string | null;
  loaded_at?: string | null;
  max_steps?: number;
  model: { primary?: string; timeout_ms?: number };
  agents: WorkspaceAgent[];
  knowledge: WorkspaceKnowledge[];
  tools: Array<{
    id: string;
    name: string;
    description?: string;
    risk_level: string;
    entrypoint: string;
    source_path: string;
    parameters: Record<string, unknown>;
  }>;
};

export async function listApps() {
  const { data } = await api.get<PageResult<AppItem>>("/apps");
  return data;
}

export async function getWorkspace(slug: string) {
  const { data } = await api.get<AgentWorkspace>(`/apps/${slug}`);
  return data;
}
