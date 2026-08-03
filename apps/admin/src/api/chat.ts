import { useAuthStore } from "../stores/auth";

const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export type ChatCitation = {
  doc_id?: string;
  chunk_id?: string;
  score?: number;
  content?: string;
  source?: string;
};

export type AgentStep = {
  step_no: number;
  agent_id: string;
  type: "thought" | "tool" | string;
  tool_id?: string | null;
  args?: Record<string, unknown> | null;
  output?: string | null;
  duration_ms?: number | null;
  error?: string | null;
  request_id?: string;
};

export type StreamHandlers = {
  onDelta?: (text: string) => void;
  onCitation?: (c: ChatCitation) => void;
  onStep?: (step: AgentStep) => void;
  onUsage?: (usage: Record<string, number>) => void;
  onDone?: (payload: {
    session_id: string;
    request_id: string;
    run_id?: string;
    answer: string;
  }) => void;
  onError?: (payload: { code: string; message: string }) => void;
};

export type ChatSelection = {
  project_id?: string;
  selection?: {
    type?: string;
    id?: string;
    episode_id?: string;
    narrative_space_id?: string;
    video_segment_id?: string;
    shot_id?: string;
    title?: string;
  };
  // 兼容扁平写法：直接把 type/id 放在顶层
  type?: string;
  id?: string;
  episode_id?: string;
  narrative_space_id?: string;
  video_segment_id?: string;
  shot_id?: string;
  title?: string;
};

export async function streamChatCompletions(
  body: {
    slug: string;
    session_id?: string | null;
    message: string;
    selection?: ChatSelection | null;
    /** 指定则只跑该 Agent；不传为全链路 coordinator */
    agent_id?: string | null;
  },
  handlers: StreamHandlers,
  signal?: AbortSignal,
) {
  const token = useAuthStore.getState().accessToken;
  const resp = await fetch(`${baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    const text = await resp.text();
    throw new Error(text || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const part of parts) {
      const lines = part.split("\n");
      let event = "message";
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const data = JSON.parse(dataLines.join("\n"));
      if (event === "delta") handlers.onDelta?.(data.text || "");
      if (event === "citation") handlers.onCitation?.(data);
      if (event === "step") handlers.onStep?.(data);
      if (event === "usage") handlers.onUsage?.(data);
      if (event === "done") handlers.onDone?.(data);
      if (event === "error") handlers.onError?.(data);
    }
  }
}

export async function getAgentRun(runId: string) {
  const token = useAuthStore.getState().accessToken;
  const resp = await fetch(`${baseURL}/agent/runs/${runId}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json() as Promise<{
    id: string;
    request_id: string;
    status: string;
    answer?: string;
    steps: AgentStep[];
  }>;
}

export type ChatSessionItem = {
  id: string;
  slug: string;
  title: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export type ChatMessageItem = {
  id: string;
  role: string;
  content: string;
  token_count?: number | null;
  request_id?: string | null;
  created_at: string | null;
};

export async function listChatSessions(params: {
  slug?: string;
  page?: number;
  page_size?: number;
}) {
  const token = useAuthStore.getState().accessToken;
  const qs = new URLSearchParams();
  if (params.slug) qs.set("slug", params.slug);
  if (params.page) qs.set("page", String(params.page));
  if (params.page_size) qs.set("page_size", String(params.page_size));
  const resp = await fetch(`${baseURL}/sessions?${qs}`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json() as Promise<{
    items: ChatSessionItem[];
    total: number;
    page: number;
    page_size: number;
  }>;
}

export async function listChatMessages(sessionId: string) {
  const token = useAuthStore.getState().accessToken;
  const resp = await fetch(`${baseURL}/sessions/${sessionId}/messages`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json() as Promise<{ items: ChatMessageItem[] }>;
}
