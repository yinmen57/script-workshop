import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { AdminLayout } from "./layouts/AdminLayout";
import { RequireAuth } from "./routes/RequireAuth";
import { LoginPage } from "./pages/framework/LoginPage";
import { AppsPage } from "./pages/framework/AppsPage";
import { AgentWorkspacePage } from "./pages/framework/AgentWorkspacePage";
import { PlaygroundPage } from "./pages/framework/PlaygroundPage";
import {
  businessFullscreenRoutes,
  businessLayoutRoutes,
} from "./business/routes";

const queryClient = new QueryClient();

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              {businessFullscreenRoutes}
              <Route element={<AdminLayout />}>
                <Route path="/" element={<Navigate to="/apps" replace />} />
                <Route path="/apps" element={<AppsPage />} />
                <Route path="/apps/:slug/playground" element={<PlaygroundPage />} />
                <Route path="/apps/:slug" element={<AgentWorkspacePage />} />
                {businessLayoutRoutes}
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/apps" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
