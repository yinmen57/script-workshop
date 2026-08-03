import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 前后端分离：开发态代理到框架 API / 业务 API；生产由网关反代
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:42867";
  const bizApiTarget =
    env.VITE_BIZ_API_PROXY_TARGET || "http://127.0.0.1:42868";

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        // 更具体的前缀放前面
        "/api/v1/script-biz": {
          target: bizApiTarget,
          changeOrigin: true,
        },
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
