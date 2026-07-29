import { api } from "./client";

export type ScriptProject = {
  id: string;
  name: string;
  status: string;
  style_bible?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type CharacterAsset = {
  id: string;
  name: string;
  character_key: string;
  appearance_anchor: string;
  costume_baseline?: string;
  status: string;
  record_status?: string;
};

export type PropAsset = {
  id: string;
  prop_key: string;
  prop_type: string;
  prop_name: string;
  visual_anchor: string;
  owner_name?: string | null;
  scope: string;
  status: string;
  record_status?: string;
};

export type MaterialPrompt = {
  id: string;
  target_type: string;
  target_id: string;
  prompt_text: string;
  negative_prompt?: string;
  version: number;
  status: string;
  record_status?: string;
};

export type NarrativeSpace = {
  id: string;
  project_id: string;
  episode_id: string;
  ordinal: number;
  title: string;
  summary?: string;
  time_place?: string;
  source_text?: string;
  estimated_duration_sec?: number | null;
  status: string;
  record_status?: string;
};

export type Episode = {
  id: string;
  project_id: string;
  ordinal: number;
  title: string;
  status: string;
  record_status?: string;
  narrative_spaces: NarrativeSpace[];
};

export async function listScriptProjects() {
  const { data } = await api.get<{ items: ScriptProject[]; total: number }>(
    "/script-biz/projects",
  );
  return data;
}

export async function createScriptProject(body: { name: string }) {
  const { data } = await api.post<ScriptProject>("/script-biz/projects", body);
  return data;
}

export async function getScriptProject(projectId: string) {
  const { data } = await api.get<ScriptProject>(`/script-biz/projects/${projectId}`);
  return data;
}

export async function parseScriptProject(
  projectId: string,
  body: { script_text?: string; title?: string },
) {
  const { data } = await api.post<{
    project: ScriptProject;
    characters: CharacterAsset[];
    props: PropAsset[];
    structure?: { items: Episode[]; total: number };
  }>(`/script-biz/projects/${projectId}/parse`, body);
  return data;
}

export async function getScriptAssets(projectId: string) {
  const { data } = await api.get<{
    project: ScriptProject;
    characters: CharacterAsset[];
    props: PropAsset[];
  }>(`/script-biz/projects/${projectId}/assets`);
  return data;
}

export async function confirmScriptAsset(
  projectId: string,
  body: { target_type: "character" | "prop"; target_id: string },
) {
  const { data } = await api.post<{
    project: ScriptProject;
    characters: CharacterAsset[];
    props: PropAsset[];
  }>(`/script-biz/projects/${projectId}/assets/confirm`, body);
  return data;
}

export async function getScriptStructure(projectId: string) {
  const { data } = await api.get<{ items: Episode[]; total: number }>(
    `/script-biz/projects/${projectId}/structure`,
  );
  return data;
}

export async function parseScriptStructure(
  projectId: string,
  body?: { script_text?: string },
) {
  const { data } = await api.post<{
    parsed: { episode_count: number; narrative_space_count: number };
    structure: { items: Episode[]; total: number };
  }>(`/script-biz/projects/${projectId}/structure/parse`, body || {});
  return data;
}

export async function confirmNarrativeSpace(spaceId: string) {
  const { data } = await api.post<NarrativeSpace>(
    `/script-biz/narrative-spaces/${spaceId}/confirm`,
  );
  return data;
}

export type ShotPlan = {
  id: string;
  project_id: string;
  narrative_space_id: string;
  ordinal: number;
  scene_text?: string;
  beat?: string;
  character_ids?: string[];
  prop_ids?: string[];
  camera?: Record<string, unknown> | null;
  duration_sec?: number | null;
  status: string;
  record_status?: string;
};

export async function listShots(
  projectId: string,
  narrativeSpaceId?: string,
) {
  const { data } = await api.get<{ items: ShotPlan[]; total: number }>(
    `/script-biz/projects/${projectId}/shots`,
    { params: narrativeSpaceId ? { narrative_space_id: narrativeSpaceId } : {} },
  );
  return data;
}

export async function planProjectShots(projectId: string) {
  const { data } = await api.post<{
    spaces: unknown[];
    space_count: number;
    total: number;
  }>(`/script-biz/projects/${projectId}/shots/plan`);
  return data;
}

export async function planSpaceShots(spaceId: string) {
  const { data } = await api.post<{
    narrative_space_id: string;
    items: ShotPlan[];
    total: number;
  }>(`/script-biz/narrative-spaces/${spaceId}/shots/plan`);
  return data;
}

export async function confirmShot(shotId: string) {
  const { data } = await api.post<ShotPlan>(`/script-biz/shots/${shotId}/confirm`);
  return data;
}

export async function generateMaterialPrompts(projectId: string) {
  const { data } = await api.post<{
    items: MaterialPrompt[];
    total: number;
    skipped_confirmed?: number;
  }>(`/script-biz/projects/${projectId}/material-prompts/generate`);
  return data;
}

export async function listMaterialPrompts(projectId: string) {
  const { data } = await api.get<{ items: MaterialPrompt[]; total: number }>(
    `/script-biz/projects/${projectId}/material-prompts`,
  );
  return data;
}

export async function confirmMaterialPrompt(projectId: string, promptId: string) {
  const { data } = await api.post<MaterialPrompt>(
    `/script-biz/projects/${projectId}/material-prompts/${promptId}/confirm`,
  );
  return data;
}

export type ScriptDocument = {
  id: string;
  project_id: string;
  title: string;
  version: number;
  parse_status: string;
  source_filename?: string | null;
  source_format?: string | null;
  source_uri?: string | null;
  raw_text?: string;
  created_at?: string | null;
};

export type UploadScriptResult = {
  document: ScriptDocument;
  markdown_chars: number;
  source_filename: string;
  source_format: string;
  source_uri?: string | null;
  knowledge?: {
    namespace: string;
    indexed: number;
    dimension: number;
  } | null;
};

export async function listScriptDocuments(projectId: string) {
  const { data } = await api.get<{ items: ScriptDocument[]; total: number }>(
    `/script-biz/projects/${projectId}/scripts`,
  );
  return data;
}

export async function uploadScriptFile(
  projectId: string,
  file: File,
  options?: { title?: string; index_knowledge?: boolean },
) {
  const form = new FormData();
  form.append("file", file);
  if (options?.title) form.append("title", options.title);
  if (options?.index_knowledge === false) form.append("index_knowledge", "false");
  const { data } = await api.post<UploadScriptResult>(
    `/script-biz/projects/${projectId}/scripts/upload`,
    form,
    { timeout: 120000 },
  );
  return data;
}
