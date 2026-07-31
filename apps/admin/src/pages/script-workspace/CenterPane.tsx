/**
 * 中栏：视频类嵌入叙事空间画布；素材类展示资产详情。
 */
import { Empty, Typography } from "antd";
import { NarrativeCanvasEditor } from "../script-canvas/NarrativeCanvasEditor";
import { MaterialPane } from "./MaterialPane";
import type { WorkspaceSelection, WorkspaceTab } from "./types";

type Props = {
  projectId: string | null;
  tab: WorkspaceTab;
  selection: WorkspaceSelection | null;
};

function resolveSpaceId(selection: WorkspaceSelection | null): string | null {
  if (!selection) return null;
  if (selection.type === "narrative_space") return selection.id;
  if (selection.narrative_space_id) return selection.narrative_space_id;
  return null;
}

export function CenterPane({ projectId, tab, selection }: Props) {
  if (!projectId) {
    return (
      <div className="script-workspace__center">
        <div className="script-workspace__empty">
          <Empty description="选择或新建一个项目开始" />
        </div>
      </div>
    );
  }

  if (tab === "material") {
    return (
      <div className="script-workspace__center">
        <MaterialPane projectId={projectId} selection={selection} />
      </div>
    );
  }

  const spaceId = resolveSpaceId(selection);
  if (!spaceId) {
    return (
      <div className="script-workspace__center">
        <div className="script-workspace__empty">
          <Empty
            description={
              <div>
                <Typography.Paragraph>
                  从左侧视频树选择一个叙事空间，中间打开画布。
                </Typography.Paragraph>
                <Typography.Text type="secondary">
                  选择片段或分镜时也会定位到所属叙事空间画布。
                </Typography.Text>
              </div>
            }
          />
        </div>
      </div>
    );
  }

  return (
    <div className="script-workspace__center">
      <NarrativeCanvasEditor key={spaceId} spaceId={spaceId} embedded />
    </div>
  );
}
