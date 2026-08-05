import { Navigate, useParams } from "react-router-dom";
import { NarrativeCanvasEditor } from "./script-canvas/NarrativeCanvasEditor";

/** 全屏画布入口：键为视频片段 id。 */
export function ScriptCanvasPage() {
  const { segmentId } = useParams<{ segmentId: string }>();
  if (!segmentId) {
    return <Navigate to="/script-workspace" replace />;
  }
  return <NarrativeCanvasEditor segmentId={segmentId} />;
}
