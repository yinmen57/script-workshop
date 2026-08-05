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
  type: "thought" | "tool" | "tool_start" | "reasoning" | string;
  tool_id?: string | null;
  args?: Record<string, unknown> | null;
  output?: string | null;
  duration_ms?: number | null;
  error?: string | null;
  request_id?: string;
};

export type StreamHandlers = {
  onDelta?: (text: string) => void;
  /** 模型思考过程（如方舟 DeepSeek reasoning_content） */
  onReasoning?: (text: string) => void;
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
  type?: string;
  id?: string;
  episode_id?: string;
  narrative_space_id?: string;
  video_segment_id?: string;
  shot_id?: string;
  title?: string;
};

function resolveChatWsUrl(token: string): string {
  const path = `${baseURL.replace(/\/$/, "")}/chat/ws?token=${encodeURIComponent(token)}`;
  if (path.startsWith("ws://") || path.startsWith("wss://")) return path;
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path.replace(/^http/, "ws");
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path.startsWith("/") ? "" : "/"}${path}`;
}

/**
 * WebSocket 流式对话。关闭连接或 abort 即取消当前轮次。
 */
export async function streamChatCompletions(
  body: {
    slug: string;
    session_id?: string | null;
    message: string;
    selection?: ChatSelection | null;
    agent_id?: string | null;
  },
  handlers: StreamHandlers,
  signal?: AbortSignal,
) {
  const token = useAuthStore.getState().accessToken;
  if (!token) {
    throw new Error("未登录");
  }
  if (signal?.aborted) {
    throw new DOMException("Aborted", "AbortError");
  }

  const ws = new WebSocket(resolveChatWsUrl(token));
  let settled = false;
  let sawTerminal = false;

  const cleanup = () => {
    signal?.removeEventListener("abort", onAbort);
    if (
      ws.readyState === WebSocket.OPEN ||
      ws.readyState === WebSocket.CONNECTING
    ) {
      try {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ action: "cancel" }));
        }
      } catch {
        /* ignore */
      }
      ws.close();
    }
  };

  const onAbort = () => {
    cleanup();
  };
  signal?.addEventListener("abort", onAbort);

  await new Promise<void>((resolve, reject) => {
    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          action: "chat",
          slug: body.slug,
          session_id: body.session_id ?? null,
          message: body.message,
          selection: body.selection ?? null,
          agent_id: body.agent_id ?? null,
        }),
      );
    };

    ws.onmessage = (ev) => {
      let msg: { event?: string; data?: Record<string, unknown> };
      try {
        msg = JSON.parse(String(ev.data));
      } catch {
        return;
      }
      const event = msg.event || "message";
      const data = (msg.data || {}) as Record<string, unknown>;
      if (event === "delta") {
        handlers.onDelta?.(String(data.text || ""));
        return;
      }
      if (event === "reasoning") {
        handlers.onReasoning?.(String(data.text || ""));
        return;
      }
      if (event === "citation") {
        handlers.onCitation?.(data as ChatCitation);
        return;
      }
      if (event === "step") {
        handlers.onStep?.(data as unknown as AgentStep);
        return;
      }
      if (event === "usage") {
        handlers.onUsage?.(data as Record<string, number>);
        return;
      }
      if (event === "done") {
        sawTerminal = true;
        handlers.onDone?.(data as {
          session_id: string;
          request_id: string;
          run_id?: string;
          answer: string;
        });
        settled = true;
        cleanup();
        resolve();
        return;
      }
      if (event === "error") {
        sawTerminal = true;
        const code = String(data.code || "ERROR");
        const message = String(data.message || "对话失败");
        if (code === "CANCELLED") {
          settled = true;
          cleanup();
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }
        handlers.onError?.({ code, message });
        settled = true;
        cleanup();
        // 业务错误已交给 onError，不再抛到外层避免重复提示
        resolve();
      }
    };

    ws.onerror = () => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(new Error("WebSocket 连接失败"));
    };

    ws.onclose = () => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener("abort", onAbort);
      if (signal?.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      if (!sawTerminal) {
        reject(new Error("WebSocket 连接已关闭"));
        return;
      }
      resolve();
    };
  });
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
