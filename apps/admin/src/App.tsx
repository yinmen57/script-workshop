import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, Spin } from "antd";
import zhCN from "antd/locale/zh_CN";
import { AdminLayout } from "./layouts/AdminLayout";
import { RequireAuth } from "./routes/RequireAuth";
import { LoginPage } from "./pages/LoginPage";
import { AppsPage } from "./pages/AppsPage";
import { AgentWorkspacePage } from "./pages/AgentWorkspacePage";
import { PlaygroundPage } from "./pages/PlaygroundPage";
import { ModelsPage } from "./pages/ModelsPage";
// 画布依赖 React Flow，懒加载避免拖垮整站首屏
const ScriptCanvasPage = lazy(() =>
  import("./pages/ScriptCanvasPage").then((m) => ({
    default: m.ScriptCanvasPage,
  })),
);

const ScriptWorkspacePage = lazy(() =>
  import("./pages/script-workspace/ScriptWorkspacePage").then((m) => ({
    default: m.ScriptWorkspacePage,
  })),
);

const queryClient = new QueryClient();

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              {/* 画布全屏：不套侧栏/顶栏 */}
              <Route
                path="/script-biz/canvas/:spaceId"
                element={
                  <Suspense
                    fallback={
                      <div
                        style={{
                          height: "100vh",
                          display: "grid",
                          placeItems: "center",
                        }}
                      >
                        <Spin />
                      </div>
                    }
                  >
                    <ScriptCanvasPage />
                  </Suspense>
                }
              />
              <Route
                path="/script-workspace"
                element={
                  <Suspense
                    fallback={
                      <div
                        style={{
                          height: "100vh",
                          display: "grid",
                          placeItems: "center",
                        }}
                      >
                        <Spin />
                      </div>
                    }
                  >
                    <ScriptWorkspacePage />
                  </Suspense>
                }
              />
              <Route element={<AdminLayout />}>
                <Route path="/" element={<Navigate to="/apps" replace />} />
                <Route path="/apps" element={<AppsPage />} />
                {/* 一个应用空间对应一个调试台：/apps/:slug/playground */}
                <Route path="/apps/:slug/playground" element={<PlaygroundPage />} />
                <Route path="/apps/:slug" element={<AgentWorkspacePage />} />
                <Route path="/models" element={<ModelsPage />} />
                {/* 旧工坊入口重定向到新工作台 */}
                <Route
                  path="/script-biz"
                  element={<Navigate to="/script-workspace" replace />}
                />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/apps" replace />} />
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
