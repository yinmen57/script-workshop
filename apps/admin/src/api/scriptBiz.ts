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
  beat_type?: string;
  mood?: string;
  boundary_reason?: string;
  segment_source?: string;
  status: string;
  record_status?: string;
};

export type VideoSegment = {
  id: string;
  project_id: string;
  narrative_space_id: string;
  ordinal: number;
  title: string;
  summary?: string;
  shot_ids?: string[];
  source_text?: string;
  duration_sec?: number | null;
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

export type JobRun = {
  id: string;
  project_id: string;
  kind: string;
  dedupe_key: string;
  label: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled" | string;
  progress: number;
  payload?: Record<string, unknown> | null;
  result?: Record<string, unknown> | null;
  error?: string | null;
  deduped?: boolean;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
};

export async function getJob(jobId: string) {
  const { data } = await api.get<JobRun>(`/script-biz/jobs/${jobId}`);
  return data;
}

export async function listProjectJobs(
  projectId: string,
  params?: { status?: string; limit?: number },
) {
  const { data } = await api.get<{ items: JobRun[]; total: number }>(
    `/script-biz/projects/${projectId}/jobs`,
    { params },
  );
  return data;
}

/** 投递后轮询至终态；失败抛错。 */
export async function waitJob(
  jobId: string,
  options?: { intervalMs?: number; timeoutMs?: number },
) {
  const interval = options?.intervalMs ?? 1500;
  const timeout = options?.timeoutMs ?? 600000;
  const started = Date.now();
  while (true) {
    const job = await getJob(jobId);
    if (job.status === "done") return job;
    if (job.status === "failed") {
      throw new Error(job.error || "作业失败");
    }
    if (job.status === "cancelled") {
      throw new Error("作业已取消");
    }
    if (Date.now() - started > timeout) {
      throw new Error(`作业等待超时：${jobId}`);
    }
    await new Promise((r) => setTimeout(r, interval));
  }
}

export async function parseScriptProject(
  projectId: string,
  body: { script_text?: string; title?: string },
) {
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/parse`,
    body,
  );
  return waitJob(data.id);
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

export async function segmentScriptStructure(
  projectId: string,
  body?: { script_text?: string },
) {
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/structure/segment`,
    body || {},
  );
  return waitJob(data.id);
}

export async function indexProjectKnowledge(projectId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/knowledge/index`,
  );
  return waitJob(data.id);
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
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/shots/plan`,
  );
  return waitJob(data.id);
}

export async function planSpaceShots(spaceId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/narrative-spaces/${spaceId}/shots/plan`,
  );
  return waitJob(data.id);
}

export async function confirmShot(shotId: string) {
  const { data } = await api.post<ShotPlan>(`/script-biz/shots/${shotId}/confirm`);
  return data;
}

export type SceneSpace = {
  id: string;
  project_id: string;
  canonical_key: string;
  name: string;
  anchor?: string;
  reference_image_url?: string | null;
  record_status?: string;
};

export type VideoPrompt = {
  id: string;
  project_id: string;
  video_segment_id: string;
  narrative_space_id: string;
  prompt_text: string;
  negative_prompt?: string;
  ref_image_ids?: string[];
  duration_sec?: number | null;
  version: number;
  status: string;
  record_status?: string;
};

export type MaterialImage = {
  id: string;
  project_id: string;
  url: string;
  label?: string;
  origin: string;
  source_kind?: string | null;
  source_id?: string | null;
  prompt?: string;
  series_wide?: boolean;
  record_status?: string;
};

export type RecordRevision = {
  id: string;
  target_type: string;
  target_id: string;
  revision_no: number;
  snapshot: Record<string, unknown>;
  change_reason: string;
  created_by?: string | null;
  created_at?: string | null;
};

export async function listSceneSpaces(projectId: string) {
  const { data } = await api.get<{ items: SceneSpace[]; total: number }>(
    `/script-biz/projects/${projectId}/scene-spaces`,
  );
  return data;
}

export async function updateNarrativeSpace(
  spaceId: string,
  body: Partial<
    Pick<
      NarrativeSpace,
      "title" | "summary" | "time_place" | "source_text" | "estimated_duration_sec"
    > & { ordinal?: number }
  >,
) {
  const { data } = await api.patch<NarrativeSpace>(
    `/script-biz/narrative-spaces/${spaceId}`,
    body,
  );
  return data;
}

export async function deleteNarrativeSpace(spaceId: string) {
  const { data } = await api.delete<{ deleted: boolean; id: string }>(
    `/script-biz/narrative-spaces/${spaceId}`,
  );
  return data;
}

export async function listVideoSegments(
  projectId: string,
  narrativeSpaceId?: string,
) {
  const { data } = await api.get<{ items: VideoSegment[]; total: number }>(
    `/script-biz/projects/${projectId}/video-segments`,
    { params: narrativeSpaceId ? { narrative_space_id: narrativeSpaceId } : {} },
  );
  return data;
}

export async function planProjectVideoSegments(projectId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/video-segments/plan`,
  );
  return waitJob(data.id);
}

export async function planSpaceVideoSegments(spaceId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/narrative-spaces/${spaceId}/video-segments/plan`,
  );
  return waitJob(data.id);
}

export async function confirmVideoSegment(segmentId: string) {
  const { data } = await api.post<VideoSegment>(
    `/script-biz/video-segments/${segmentId}/confirm`,
  );
  return data;
}

export async function listVideoPrompts(
  projectId: string,
  narrativeSpaceId?: string,
) {
  const { data } = await api.get<{ items: VideoPrompt[]; total: number }>(
    `/script-biz/projects/${projectId}/video-prompts`,
    { params: narrativeSpaceId ? { narrative_space_id: narrativeSpaceId } : {} },
  );
  return data;
}

export async function generateProjectVideoPrompts(projectId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/video-prompts/generate`,
  );
  return waitJob(data.id);
}

export async function generateSpaceVideoPrompt(spaceId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/narrative-spaces/${spaceId}/video-prompts/generate`,
  );
  return waitJob(data.id);
}

export async function generateSegmentVideoPrompt(segmentId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/video-segments/${segmentId}/video-prompts/generate`,
  );
  return waitJob(data.id);
}

export async function confirmVideoPrompt(promptId: string) {
  const { data } = await api.post<VideoPrompt>(
    `/script-biz/video-prompts/${promptId}/confirm`,
  );
  return data;
}

export async function listMaterialImages(
  projectId: string,
  params?: { source_kind?: string; source_id?: string },
) {
  const { data } = await api.get<{ items: MaterialImage[]; total: number }>(
    `/script-biz/projects/${projectId}/material-images`,
    { params },
  );
  return data;
}

export async function registerMaterialImage(
  projectId: string,
  body: {
    url: string;
    label?: string;
    origin?: "generated" | "uploaded" | "imported";
    source_kind?: string;
    source_id?: string;
    prompt?: string;
    series_wide?: boolean;
  },
) {
  const { data } = await api.post<MaterialImage>(
    `/script-biz/projects/${projectId}/material-images`,
    body,
  );
  return data;
}

export async function listRevisions(targetType: string, targetId: string) {
  const { data } = await api.get<{ items: RecordRevision[]; total: number }>(
    "/script-biz/revisions",
    { params: { target_type: targetType, target_id: targetId } },
  );
  return data;
}

export async function revertRevision(revisionId: string) {
  const { data } = await api.post<{
    target_type: string;
    target_id: string;
    revision_id: string;
  }>(`/script-biz/revisions/${revisionId}/revert`);
  return data;
}

export async function generateMaterialPrompts(projectId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/projects/${projectId}/material-prompts/generate`,
  );
  return waitJob(data.id);
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

export type VideoJob = {
  id: string;
  project_id: string;
  video_prompt_id: string;
  narrative_space_id: string;
  provider_job_id?: string | null;
  status: string;
  oss_uri?: string | null;
  result_url?: string | null;
  error?: string | null;
  duration_sec?: number | null;
};

export async function renderMaterialImage(promptId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/material-prompts/${promptId}/render`,
  );
  return waitJob(data.id, { timeoutMs: 360000 });
}

export async function renderVideoPrompt(promptId: string) {
  const { data } = await api.post<JobRun>(
    `/script-biz/video-prompts/${promptId}/render`,
  );
  return waitJob(data.id, { timeoutMs: 720000 });
}

export async function listVideoJobs(
  projectId: string,
  narrativeSpaceId?: string,
) {
  const { data } = await api.get<{ items: VideoJob[]; total: number }>(
    `/script-biz/projects/${projectId}/video-jobs`,
    { params: narrativeSpaceId ? { narrative_space_id: narrativeSpaceId } : {} },
  );
  return data;
}

export async function getSdBalance() {
  const { data } = await api.get<{
    balance: Record<string, unknown>;
    credits?: number | null;
  }>("/script-biz/sd/balance");
  return data;
}

export type CanvasSnapshot = {
  id: string;
  narrative_space_id: string;
  project_id?: string;
  nodes: unknown[];
  edges: unknown[];
  viewport?: { x: number; y: number; zoom: number } | null;
  version: number;
  bootstrapped?: boolean;
  space?: { id: string; title?: string; time_place?: string };
};

export async function getCanvas(spaceId: string) {
  const { data } = await api.get<CanvasSnapshot>(
    `/script-biz/narrative-spaces/${spaceId}/canvas`,
  );
  return data;
}

export async function saveCanvas(
  spaceId: string,
  body: {
    nodes: unknown[];
    edges: unknown[];
    viewport?: { x: number; y: number; zoom: number } | null;
  },
) {
  const { data } = await api.put<CanvasSnapshot>(
    `/script-biz/narrative-spaces/${spaceId}/canvas`,
    body,
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
  options?: { title?: string },
) {
  const form = new FormData();
  form.append("file", file);
  if (options?.title) form.append("title", options.title);
  const { data } = await api.post<UploadScriptResult>(
    `/script-biz/projects/${projectId}/scripts/upload`,
    form,
    { timeout: 120000 },
  );
  return data;
}
