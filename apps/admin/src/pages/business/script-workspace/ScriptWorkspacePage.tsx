/**
 * 剧本工作台：顶栏项目操作 + 左树（视频/素材）+ 中栏（画布/素材展示）+ 右栏对话。
 * 知识库为独立模式，不与工作台事实编辑混在同一栏。
 */
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CenterPane } from "./CenterPane";
import { KnowledgePane } from "./KnowledgePane";
import { ProjectBar } from "./ProjectBar";
import { WorkspaceChat } from "./WorkspaceChat";
import { WorkspaceTree } from "./WorkspaceTree";
import type { WorkspaceMode, WorkspaceSelection, WorkspaceTab } from "./types";
import "./workspace.css";

const PROJECT_KEY = "script-workshop:project-id";

export function ScriptWorkspacePage() {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string | null>(() =>
    localStorage.getItem(PROJECT_KEY),
  );
  const [mode, setMode] = useState<WorkspaceMode>("workspace");
  const [tab, setTab] = useState<WorkspaceTab>("video");
  const [selection, setSelection] = useState<WorkspaceSelection | null>(null);

  useEffect(() => {
    setSelection(null);
    if (projectId) localStorage.setItem(PROJECT_KEY, projectId);
    else localStorage.removeItem(PROJECT_KEY);
  }, [projectId]);

  return (
    <div className="script-workspace">
      <ProjectBar
        projectId={projectId}
        mode={mode}
        onModeChange={setMode}
        onProjectChange={setProjectId}
      />
      {mode === "knowledge" ? (
        <div className="script-workspace__body script-workspace__body--knowledge">
          <KnowledgePane projectId={projectId} />
        </div>
      ) : (
        <div className="script-workspace__body">
          {projectId ? (
            <WorkspaceTree
              projectId={projectId}
              tab={tab}
              onTabChange={(next) => {
                setTab(next);
              }}
              selection={selection}
              onSelect={setSelection}
            />
          ) : (
            <div className="script-workspace__left">
              <div className="script-workspace__empty">请选择项目</div>
            </div>
          )}
          <CenterPane
            projectId={projectId}
            tab={tab}
            selection={selection}
          />
          <WorkspaceChat
            projectId={projectId}
            selection={selection}
            onStep={() => {
              // Agent 工具跑完后刷新左树与素材
              void queryClient.invalidateQueries({
                queryKey: ["script-workspace"],
              });
            }}
          />
        </div>
      )}
    </div>
  );
}
