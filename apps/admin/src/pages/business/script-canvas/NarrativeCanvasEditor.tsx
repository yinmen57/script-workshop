/**
 * 视频片段画布编辑器：ReactFlow 壳 + 自动保存 + 节点动作走 script-biz。
 * 画布单位 = ≤15s 视频片段。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Button, Space, Typography, message } from "antd";
import { useNavigate } from "react-router-dom";
import type { AgentStep } from "../../../api/chat";
import {
  confirmScriptAsset,
  confirmShot,
  generateMaterialPrompts,
  generateSegmentVideoPrompt,
  getCanvas,
  listMaterialPrompts,
  listVideoPrompts,
  planSpaceShots,
  type CanvasSnapshot,
} from "../../../api/business/scriptBiz";
import { CanvasChatPanel } from "./CanvasChatPanel";
import { CanvasEdge } from "./edges/canvas-edge";
import { useCanvasAutoSave } from "./hooks/useCanvasAutoSave";
import { narrativeNodeTypes, type NarrativeNodeData } from "./nodes";
import {
  applyAgentStepToNodes,
  CANVAS_STEP_CHANNEL,
  type CanvasStepMessage,
} from "./sync/applyAgentStep";
import { canvasTokens } from "./theme/tokens";
import "./theme/canvas.css";

const edgeTypes = { canvas: CanvasEdge };

type Props = {
  segmentId: string;
  /** 嵌入工作台时填满父容器，隐藏返回与侧挂对话 */
  embedded?: boolean;
};

function EditorInner({ segmentId, embedded = false }: Props) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState<CanvasSnapshot | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const viewportRef = useRef<Viewport>({ x: 0, y: 0, zoom: 1 });
  const projectIdRef = useRef<string>("");
  const spaceIdRef = useRef<string>("");
  const segmentIdRef = useRef(segmentId);
  segmentIdRef.current = segmentId;

  const { saving, lastSavedAt, version, flush } = useCanvasAutoSave(
    nodes,
    edges,
    viewportRef,
    { segmentId, enabled: !loading },
  );

  const patchNode = useCallback(
    (nodeId: string, patch: Partial<NarrativeNodeData>) => {
      setNodes((prev) =>
        prev.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...(n.data as object), ...patch } }
            : n,
        ),
      );
    },
    [setNodes],
  );

  const handleAction = useCallback(
    async (nodeId: string, action: string, data: NarrativeNodeData) => {
      const projectId = projectIdRef.current;
      if (!projectId) return;
      patchNode(nodeId, { status: "running", error: undefined });
      try {
        if (action === "confirm_asset" && data.entity_id) {
          await confirmScriptAsset(projectId, {
            target_type: data.kind === "prop" ? "prop" : "character",
            target_id: data.entity_id,
          });
          patchNode(nodeId, { status: "done", record_status: "confirmed" });
          message.success("已确认");
          return;
        }
        if (action === "gen_material") {
          const job = await generateMaterialPrompts(projectId);
          patchNode(nodeId, { status: "done" });
          message.success(
            `物料提示词作业完成（${(job.result as { total?: number })?.total ?? 0} 条）`,
          );
          return;
        }
        if (action === "plan_shots") {
          const spaceId = spaceIdRef.current;
          if (!spaceId) throw new Error("缺少所属叙事空间");
          const job = await planSpaceShots(spaceId);
          patchNode(nodeId, { status: "done" });
          message.success(
            `分镜规划完成（${(job.result as { total?: number })?.total ?? 0} 镜）`,
          );
          return;
        }
        if (action === "confirm_shot" && data.entity_id) {
          await confirmShot(data.entity_id);
          patchNode(nodeId, { status: "done", record_status: "confirmed" });
          message.success("分镜已确认");
          return;
        }
        if (action === "gen_video_prompt") {
          await generateSegmentVideoPrompt(segmentIdRef.current);
          const prompts = await listVideoPrompts(projectId, {
            videoSegmentId: segmentIdRef.current,
          });
          const latest = prompts.items[0];
          patchNode(nodeId, {
            status: "done",
            video_prompt_id: latest?.id,
            record_status: latest?.record_status,
          });
          message.success("成片提示词已生成");
          if (latest?.id) {
            navigate(
              `/script-biz/generate/video/${latest.id}?fromSegment=${segmentIdRef.current}`,
            );
          }
          return;
        }
        if (action === "open_video_confirm") {
          let promptId = data.video_prompt_id;
          if (!promptId) {
            const prompts = await listVideoPrompts(projectId, {
              videoSegmentId: segmentIdRef.current,
            });
            promptId = prompts.items[0]?.id;
          }
          if (!promptId) {
            patchNode(nodeId, { status: "idle" });
            message.warning("请先生成成片提示词");
            return;
          }
          patchNode(nodeId, {
            status: "idle",
            video_prompt_id: promptId,
          });
          navigate(
            `/script-biz/generate/video/${promptId}?fromSegment=${segmentIdRef.current}`,
          );
          return;
        }
        if (action === "open_material_confirm") {
          const targetType = data.kind === "prop" ? "prop" : "character";
          const targetId = data.entity_id;
          if (!targetId) throw new Error("缺少资产 id");
          const prompts = await listMaterialPrompts(projectId);
          const hit = prompts.items.find(
            (p) => p.target_type === targetType && p.target_id === targetId,
          );
          if (!hit) {
            patchNode(nodeId, { status: "idle" });
            message.warning("请先生成物料提示词");
            return;
          }
          patchNode(nodeId, { status: "idle" });
          navigate(
            `/script-biz/generate/image/${hit.id}?fromSegment=${segmentIdRef.current}`,
          );
          return;
        }
        patchNode(nodeId, { status: "idle" });
      } catch (e) {
        const err = e instanceof Error ? e.message : "操作失败";
        patchNode(nodeId, { status: "failed", error: err });
        message.error(err);
      }
    },
    [navigate, patchNode],
  );

  const actionRef = useRef(handleAction);
  actionRef.current = handleAction;

  const withActions = useCallback(
    (list: Node[]) =>
      list.map((n) => ({
        ...n,
        data: {
          ...(n.data as object),
          onAction: (action: string, data: NarrativeNodeData) =>
            void actionRef.current(n.id, action, data),
        },
      })),
    [],
  );

  const applyStep = useCallback(
    (step: AgentStep) => {
      setNodes((prev) =>
        withActions(
          applyAgentStepToNodes(prev, step, {
            segmentId: segmentIdRef.current,
            projectId: projectIdRef.current,
          }),
        ),
      );
    },
    [setNodes, withActions],
  );

  useEffect(() => {
    const bc = new BroadcastChannel(CANVAS_STEP_CHANNEL);
    bc.onmessage = (ev: MessageEvent<CanvasStepMessage>) => {
      const msg = ev.data;
      if (!msg?.step) return;
      if (msg.segmentId && msg.segmentId !== segmentIdRef.current) return;
      applyStep(msg.step);
    };
    return () => bc.close();
  }, [applyStep]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const snap = await getCanvas(segmentId);
        if (cancelled) return;
        setMeta(snap);
        projectIdRef.current = snap.project_id || "";
        spaceIdRef.current =
          snap.narrative_space_id || snap.segment?.narrative_space_id || "";
        setNodes(withActions((snap.nodes as Node[]) || []));
        setEdges(
          ((snap.edges as Edge[]) || []).map((e) => ({
            ...e,
            type: e.type || "canvas",
          })),
        );
        if (snap.viewport) {
          viewportRef.current = snap.viewport as Viewport;
        }
      } catch (e) {
        message.error(e instanceof Error ? e.message : "加载画布失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [segmentId, setNodes, setEdges, withActions]);

  const title =
    meta?.segment?.title ||
    (meta?.segment?.ordinal != null
      ? `片段 ${meta.segment.ordinal}`
      : "视频片段画布");
  const duration =
    meta?.segment?.duration_sec != null
      ? ` · ${meta.segment.duration_sec.toFixed(1)}s`
      : "";

  return (
    <div
      style={{
        height: embedded ? "100%" : "100vh",
        width: embedded ? "100%" : "100vw",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <ReactFlow
        className="script-canvas-flow"
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onMoveEnd={(_, vp) => {
          viewportRef.current = vp;
        }}
        nodeTypes={narrativeNodeTypes}
        edgeTypes={edgeTypes}
        defaultEdgeOptions={{ type: "canvas" }}
        fitView
        panOnScroll
        panOnDrag={[1, 2]}
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1.35}
          color={canvasTokens.dots}
        />
        <MiniMap
          pannable
          zoomable
          nodeColor={() => canvasTokens.brand}
          maskColor="rgba(15,23,42,0.06)"
        />
        <Controls />
        <Panel position="top-left">
          <Space
            style={{
              background: "#fff",
              padding: "8px 12px",
              borderRadius: 12,
              border: `1px solid ${canvasTokens.panelBorder}`,
              boxShadow: canvasTokens.panelShadow,
            }}
          >
            {embedded ? null : (
              <Button size="small" onClick={() => navigate("/script-workspace")}>
                返回工作台
              </Button>
            )}
            <Typography.Text>
              {title}
              {duration}
            </Typography.Text>
            <Typography.Text type="secondary">
              {saving
                ? "保存中…"
                : lastSavedAt
                  ? `已保存 v${version || meta?.version || 1}`
                  : `v${meta?.version || 1}`}
            </Typography.Text>
            <Button size="small" onClick={() => void flush()}>
              立即保存
            </Button>
          </Space>
        </Panel>
        {embedded ? null : (
          <Panel position="top-right">
            <CanvasChatPanel
              segmentId={segmentId}
              narrativeSpaceId={meta?.narrative_space_id}
              projectId={meta?.project_id}
              onStep={applyStep}
            />
          </Panel>
        )}
      </ReactFlow>
      {loading ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "grid",
            placeItems: "center",
            background: "rgba(255,255,255,0.6)",
            zIndex: 10,
          }}
        >
          加载画布…
        </div>
      ) : null}
    </div>
  );
}

export function NarrativeCanvasEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <EditorInner {...props} />
    </ReactFlowProvider>
  );
}
