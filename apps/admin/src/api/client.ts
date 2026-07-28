import axios from "axios";
import { useAuthStore } from "../stores/auth";

// 前后端分离：默认走同源代理 /api/v1，生产可改为网关地址
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export const api = axios.create({
  baseURL,
  timeout: 30000,
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout();
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export type LoginResult = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
};

export type MeResult = {
  user_id: string | null;
  display_name: string;
  tenant_id: string;
  permissions: string[];
};

export async function loginApi(account: string, password: string) {
  const { data } = await api.post<LoginResult>("/auth/login", { account, password });
  return data;
}

export async function meApi() {
  const { data } = await api.get<MeResult>("/auth/me");
  return data;
}

export async function readyApi() {
  const { data } = await api.get<{ ready: boolean; dependencies: Record<string, string> }>(
    "/ready",
  );
  return data;
}
