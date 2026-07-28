import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 前后端分离：开发态通过代理转发 API，生产态由网关/Nginx 反代
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:42867";

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  };
});
