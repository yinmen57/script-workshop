/**
 * 叙事空间画布编辑器：ReactFlow 壳 + 自动保存 + 节点动作走 script-biz。
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
import type { AgentStep } from "../../api/chat";
import {
  confirmScriptAsset,
  confirmShot,
  confirmVideoPrompt,
  generateMaterialPrompts,
  generateSpaceVideoPrompt,
  getCanvas,
  listVideoPrompts,
  planSpaceShots,
  renderVideoPrompt,
  type CanvasSnapshot,
} from "../../api/scriptBiz";
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
  spaceId: string;
};

function EditorInner({ spaceId }: Props) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [meta, setMeta] = useState<CanvasSnapshot | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const viewportRef = useRef<Viewport>({ x: 0, y: 0, zoom: 1 });
  const projectIdRef = useRef<string>("");
  const spaceIdRef = useRef(spaceId);
  spaceIdRef.current = spaceId;

  const { saving, lastSavedAt, version, flush } = useCanvasAutoSave(
    nodes,
    edges,
    viewportRef,
    { spaceId, enabled: !loading },
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
          const job = await planSpaceShots(spaceIdRef.current);
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
          await generateSpaceVideoPrompt(spaceIdRef.current);
          const prompts = await listVideoPrompts(projectId, spaceIdRef.current);
          const latest = prompts.items[0];
          patchNode(nodeId, {
            status: "done",
            video_prompt_id: latest?.id,
            record_status: latest?.record_status,
          });
          message.success("成片提示词已生成");
          return;
        }
        if (action === "confirm_video_prompt") {
          let promptId = data.video_prompt_id;
          if (!promptId) {
            const prompts = await listVideoPrompts(projectId, spaceIdRef.current);
            promptId = prompts.items[0]?.id;
          }
          if (!promptId) throw new Error("尚无成片提示词");
          await confirmVideoPrompt(promptId);
          patchNode(nodeId, {
            status: "done",
            record_status: "confirmed",
            video_prompt_id: promptId,
          });
          message.success("成片提示词已确认");
          return;
        }
        if (action === "render_video") {
          let promptId = data.video_prompt_id;
          if (!promptId) {
            const prompts = await listVideoPrompts(projectId, spaceIdRef.current);
            promptId = prompts.items.find((p) => p.record_status === "confirmed")
              ?.id;
          }
          if (!promptId) throw new Error("请先生成并确认成片提示词");
          await renderVideoPrompt(promptId);
          patchNode(nodeId, { status: "done" });
          message.success("成片视频已生成");
          return;
        }
        patchNode(nodeId, { status: "idle" });
      } catch (e) {
        const err = e instanceof Error ? e.message : "操作失败";
        patchNode(nodeId, { status: "failed", error: err });
        message.error(err);
      }
    },
    [patchNode],
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
            spaceId: spaceIdRef.current,
            projectId: projectIdRef.current,
          }),
        ),
      );
    },
    [setNodes, withActions],
  );

  // 调试台同浏览器页发出的 step 也可同步到本画布
  useEffect(() => {
    const bc = new BroadcastChannel(CANVAS_STEP_CHANNEL);
    bc.onmessage = (ev: MessageEvent<CanvasStepMessage>) => {
      const msg = ev.data;
      if (!msg?.step) return;
      if (msg.spaceId && msg.spaceId !== spaceIdRef.current) return;
      applyStep(msg.step);
    };
    return () => bc.close();
  }, [applyStep]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const snap = await getCanvas(spaceId);
        if (cancelled) return;
        setMeta(snap);
        projectIdRef.current = snap.project_id || "";
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
  }, [spaceId, setNodes, setEdges, withActions]);

  return (
    <div style={{ height: "100vh", width: "100vw", position: "relative", overflow: "hidden" }}>
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
            <Button size="small" onClick={() => navigate("/script-biz")}>
              返回工坊
            </Button>
            <Typography.Text>
              {meta?.space?.title || "叙事空间画布"}
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
        <Panel position="top-right">
          <CanvasChatPanel
            spaceId={spaceId}
            projectId={meta?.project_id}
            onStep={applyStep}
          />
        </Panel>
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
