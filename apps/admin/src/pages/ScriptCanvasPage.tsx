import { useParams } from "react-router-dom";
import { Typography } from "antd";
import { NarrativeCanvasEditor } from "./script-canvas/NarrativeCanvasEditor";

/** 叙事空间画布：整页全屏，无管理端侧栏。 */
export function ScriptCanvasPage() {
  const { spaceId } = useParams<{ spaceId: string }>();
  if (!spaceId) {
    return (
      <div style={{ padding: 24 }}>
        <Typography.Text type="danger">缺少叙事空间 id</Typography.Text>
      </div>
    );
  }
  return <NarrativeCanvasEditor spaceId={spaceId} />;
}
