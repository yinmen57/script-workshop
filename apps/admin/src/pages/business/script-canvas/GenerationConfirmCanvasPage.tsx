/**
 * 独立全屏确认画布：仅一个善舞风格生成确认节点。
 * 路由：/script-biz/generate/video|:image/:promptId
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button, Space, Spin, Typography, message } from "antd";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  confirmMaterialPrompt,
  confirmVideoPrompt,
  enqueueMaterialImage,
  enqueueVideoRender,
  getMaterialPrompt,
  getVideoPrompt,
  listMaterialImages,
  updateMaterialPrompt,
  updateVideoPrompt,
  type MaterialPrompt,
  type VideoPrompt,
} from "../../../api/business/scriptBiz";
import { CanvasChatPanel } from "./CanvasChatPanel";
import {
  GenerationConfirmNode,
  type GenerationConfirmData,
} from "./nodes/GenerationConfirmNode";
import { canvasTokens } from "./theme/tokens";
import "./theme/canvas.css";

const nodeTypes = { generation_confirm: GenerationConfirmNode };

type Kind = "video" | "image";

function Inner({ kind, promptId }: { kind: Kind; promptId: string }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fromSegment = searchParams.get("fromSegment") || "";
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [jobMessage, setJobMessage] = useState("");
  const [promptText, setPromptText] = useState("");
  const [video, setVideo] = useState<VideoPrompt | null>(null);
  const [material, setMaterial] = useState<MaterialPrompt | null>(null);
  const [refItems, setRefItems] = useState<
    Array<{ id: string; label: string; url?: string }>
  >([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (kind === "video") {
        const vp = await getVideoPrompt(promptId);
        setVideo(vp);
        setMaterial(null);
        setPromptText(vp.prompt_text || "");
        const refs = vp.ref_image_ids || [];
        if (refs.length && vp.project_id) {
          const imgs = await listMaterialImages(vp.project_id);
          const byId = new Map(imgs.items.map((i) => [i.id, i]));
          setRefItems(
            refs.map((id, idx) => {
              const img = byId.get(id);
              return {
                id,
                label: img?.label || `图片${idx + 1}`,
                url: img?.url,
              };
            }),
          );
        } else {
          setRefItems([]);
        }
      } else {
        const mp = await getMaterialPrompt(promptId);
        setMaterial(mp);
        setVideo(null);
        setPromptText(mp.prompt_text || "");
        if (mp.project_id) {
          const imgs = await listMaterialImages(mp.project_id, {
            source_kind: mp.target_type,
            source_id: mp.target_id,
          });
          setRefItems(
            imgs.items.slice(0, 6).map((img, idx) => ({
              id: img.id,
              label: img.label || `素材${idx + 1}`,
              url: img.url,
            })),
          );
        } else {
          setRefItems([]);
        }
      }
      setJobMessage("");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [kind, promptId]);

  useEffect(() => {
    void load();
  }, [load]);

  const recordStatus =
    kind === "video" ? video?.record_status : material?.record_status;
  const title =
    kind === "video"
      ? `成片提示词 · ${(video?.duration_sec ?? 0) || "?"}s`
      : `物料提示词 · ${material?.target_type || ""}`;
  const specLabel =
    kind === "video"
      ? `时长 ${video?.duration_sec ?? "-"}s · 版本 v${video?.version ?? "-"} · ${
          recordStatus === "confirmed" ? "已定版" : "草稿"
        }`
      : `版本 v${material?.version ?? "-"} · ${
          recordStatus === "confirmed" ? "已定版" : "草稿"
        }`;

  const onSave = async () => {
    if (recordStatus === "confirmed") return;
    setBusy(true);
    try {
      if (kind === "video") {
        const next = await updateVideoPrompt(promptId, {
          prompt_text: promptText,
        });
        setVideo(next);
      } else {
        const next = await updateMaterialPrompt(promptId, {
          prompt_text: promptText,
        });
        setMaterial(next);
      }
      message.success("已保存");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const onConfirmGenerate = async () => {
    setBusy(true);
    try {
      if (promptText.trim() && recordStatus !== "confirmed") {
        if (kind === "video") {
          await updateVideoPrompt(promptId, { prompt_text: promptText });
        } else {
          await updateMaterialPrompt(promptId, { prompt_text: promptText });
        }
      }
      if (recordStatus !== "confirmed") {
        if (kind === "video") {
          const next = await confirmVideoPrompt(promptId);
          setVideo(next);
        } else {
          const projectId = material?.project_id;
          if (!projectId) throw new Error("缺少 project_id");
          const next = await confirmMaterialPrompt(projectId, promptId);
          setMaterial(next);
        }
      }
      const job =
        kind === "video"
          ? await enqueueVideoRender(promptId)
          : await enqueueMaterialImage(promptId);
      setJobMessage(`已入队 ${job.id}（${job.status}），可到任务队列查看`);
      message.success("已确认并加入生成队列");
    } catch (e) {
      message.error(e instanceof Error ? e.message : "提交失败");
    } finally {
      setBusy(false);
    }
  };

  const nodes: Node[] = useMemo(() => {
    const data: GenerationConfirmData = {
      kind,
      title,
      promptText,
      negativePrompt:
        kind === "video" ? video?.negative_prompt : material?.negative_prompt,
      refItems,
      recordStatus,
      specLabel,
      busy,
      jobMessage,
      onPromptChange: setPromptText,
      onSave: () => void onSave(),
      onConfirmGenerate: () => void onConfirmGenerate(),
    };
    return [
      {
        id: "confirm-1",
        type: "generation_confirm",
        position: { x: 120, y: 80 },
        data,
        draggable: true,
        selectable: true,
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 回调随状态闭包更新
  }, [
    kind,
    title,
    promptText,
    video,
    material,
    refItems,
    recordStatus,
    specLabel,
    busy,
    jobMessage,
  ]);

  const goBack = () => {
    if (fromSegment) {
      navigate(`/script-biz/canvas/${fromSegment}`);
      return;
    }
    navigate("/script-workspace");
  };

  if (loading) {
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center" }}>
        <Spin tip="加载提示词…" />
      </div>
    );
  }

  const projectId =
    kind === "video" ? video?.project_id : material?.project_id;

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        background: canvasTokens.paneBg,
      }}
    >
      <div
        style={{
          height: 48,
          padding: "0 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: `1px solid ${canvasTokens.panelBorder}`,
          background: "#fff",
        }}
      >
        <Space>
          <Button onClick={goBack}>返回</Button>
          <Typography.Text strong>
            {kind === "video" ? "成片生成确认" : "物料生图确认"}
          </Typography.Text>
        </Space>
        <Space>
          <Button type="link" onClick={() => navigate("/jobs")}>
            任务队列
          </Button>
          <Button type="link" onClick={() => navigate("/script-workspace")}>
            回工作台讨论
          </Button>
        </Space>
      </div>
      <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
        <ReactFlow
          nodes={nodes}
          edges={[]}
          nodeTypes={nodeTypes}
          fitView
          nodesConnectable={false}
          edgesFocusable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={18}
            size={1}
            color={canvasTokens.dots}
          />
          <Controls />
          {projectId && kind === "video" && video ? (
            <Panel position="top-right">
              <CanvasChatPanel
                segmentId={video.video_segment_id}
                narrativeSpaceId={video.narrative_space_id}
                projectId={projectId}
                onStep={() => undefined}
              />
            </Panel>
          ) : null}
        </ReactFlow>
      </div>
    </div>
  );
}

export function GenerationConfirmCanvasPage() {
  const { kind, promptId } = useParams<{ kind: string; promptId: string }>();
  if (!promptId || (kind !== "video" && kind !== "image")) {
    return <Typography.Text type="danger">无效的确认页参数</Typography.Text>;
  }
  return (
    <ReactFlowProvider>
      <Inner kind={kind} promptId={promptId} />
    </ReactFlowProvider>
  );
}
