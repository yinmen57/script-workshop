/**
 * 中栏：视频类嵌入「视频片段」画布；素材类展示资产详情。
 * 画布单位 = ≤15s 视频片段；叙事空间本身不开画布。
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

function resolveSegmentId(selection: WorkspaceSelection | null): string | null {
  if (!selection) return null;
  if (selection.type === "video_segment") return selection.id;
  if (selection.video_segment_id) return selection.video_segment_id;
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

  const segmentId = resolveSegmentId(selection);
  if (!segmentId) {
    return (
      <div className="script-workspace__center">
        <div className="script-workspace__empty">
          <Empty
            description={
              <div>
                <Typography.Paragraph>
                  从左侧视频树选择一个视频片段（≤15s），中间打开画布。
                </Typography.Paragraph>
                <Typography.Text type="secondary">
                  叙事空间是语义切分单位；选中分镜时会打开所属片段画布。
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
      <NarrativeCanvasEditor key={segmentId} segmentId={segmentId} embedded />
    </div>
  );
}
