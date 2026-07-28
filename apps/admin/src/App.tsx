import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { AdminLayout } from "./layouts/AdminLayout";
import { RequireAuth } from "./routes/RequireAuth";
import { LoginPage } from "./pages/LoginPage";
import { AppsPage } from "./pages/AppsPage";
import { AgentWorkspacePage } from "./pages/AgentWorkspacePage";
import { PlaygroundPage } from "./pages/PlaygroundPage";
import { ScriptBizPage } from "./pages/ScriptBizPage";

const queryClient = new QueryClient();

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route element={<AdminLayout />}>
                <Route path="/" element={<Navigate to="/apps" replace />} />
                <Route path="/apps" element={<AppsPage />} />
                {/* 一个应用空间对应一个调试台：/apps/:slug/playground */}
                <Route path="/apps/:slug/playground" element={<PlaygroundPage />} />
                <Route path="/apps/:slug" element={<AgentWorkspacePage />} />
                <Route path="/script-biz" element={<ScriptBizPage />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/apps" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
