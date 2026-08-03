/** 业务路由片段，由 App 挂载。 */
import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route } from "react-router-dom";
import { Spin } from "antd";

const ScriptCanvasPage = lazy(() =>
  import("../pages/business/ScriptCanvasPage").then((m) => ({
    default: m.ScriptCanvasPage,
  })),
);

const ScriptWorkspacePage = lazy(() =>
  import("../pages/business/script-workspace/ScriptWorkspacePage").then((m) => ({
    default: m.ScriptWorkspacePage,
  })),
);

const ModelsPage = lazy(() =>
  import("../pages/business/models/ModelsPage").then((m) => ({
    default: m.ModelsPage,
  })),
);

function FullscreenSuspense({ children }: { children: ReactNode }) {
  return (
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
      {children}
    </Suspense>
  );
}

/** 全屏业务页（不套 AdminLayout） */
export const businessFullscreenRoutes = (
  <>
    <Route
      path="/script-biz/canvas/:spaceId"
      element={
        <FullscreenSuspense>
          <ScriptCanvasPage />
        </FullscreenSuspense>
      }
    />
    <Route
      path="/script-workspace"
      element={
        <FullscreenSuspense>
          <ScriptWorkspacePage />
        </FullscreenSuspense>
      }
    />
  </>
);

/** 套在 AdminLayout 内的业务页 */
export const businessLayoutRoutes = (
  <>
    <Route
      path="/models"
      element={
        <Suspense fallback={<Spin />}>
          <ModelsPage />
        </Suspense>
      }
    />
    <Route path="/script-biz" element={<Navigate to="/script-workspace" replace />} />
  </>
);
