import { api } from "./client";
import type { PageResult } from "./resources";

export type ModelType = "chat" | "embedding" | "rerank" | "image" | "video";

export type ModelItem = {
  id: string;
  tenant_id: string;
  name: string;
  provider: string;
  model_type: ModelType;
  model_name: string;
  base_url: string | null;
  dimension: number | null;
  extra: Record<string, unknown>;
  is_default: boolean;
  status: string;
  has_api_key: boolean;
  created_at: string | null;
  updated_at: string | null;
};

export type ModelListParams = {
  model_type?: string;
  status?: string;
  keyword?: string;
  page?: number;
  page_size?: number;
};

export type ModelUpsertBody = {
  name: string;
  provider?: string;
  model_type: ModelType;
  model_name: string;
  base_url?: string | null;
  api_key?: string;
  dimension?: number | null;
  status?: string;
  is_default?: boolean;
  extra?: Record<string, unknown>;
};

export type ModelTestResult = {
  ok: boolean;
  model_id: string;
  model_type: string;
  latency_ms: number;
  detail: Record<string, unknown>;
};

export async function listModels(params: ModelListParams = {}) {
  const { data } = await api.get<PageResult<ModelItem>>("/models", { params });
  return data;
}

export async function getModel(modelId: string) {
  const { data } = await api.get<ModelItem>(`/models/${modelId}`);
  return data;
}

export async function createModel(body: ModelUpsertBody) {
  const { data } = await api.post<ModelItem>("/models", body);
  return data;
}

export async function updateModel(modelId: string, body: Partial<ModelUpsertBody>) {
  const { data } = await api.patch<ModelItem>(`/models/${modelId}`, body);
  return data;
}

export async function deleteModel(modelId: string) {
  const { data } = await api.delete<{ ok: boolean }>(`/models/${modelId}`);
  return data;
}

export async function testModel(modelId: string) {
  const { data } = await api.post<ModelTestResult>(`/models/${modelId}/test`);
  return data;
}
