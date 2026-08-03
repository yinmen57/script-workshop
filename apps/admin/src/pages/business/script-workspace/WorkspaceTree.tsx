/**
 * 左栏文件系统树：视频类（集→空间→片段→分镜）与素材类（类型→资产）。
 */
import { Spin, Tabs, Tag, Tree, Typography, message } from "antd";
import type { DataNode, EventDataNode } from "antd/es/tree";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import {
  getScriptAssets,
  getScriptStructure,
  listMaterialImages,
  listMaterialPrompts,
  listSceneSpaces,
  listShots,
  listVideoSegments,
  type Episode,
  type MaterialImage,
  type ShotPlan,
  type VideoSegment,
} from "../../../api/business/scriptBiz";
import type { WorkspaceSelection, WorkspaceTab } from "./types";

type Props = {
  projectId: string;
  tab: WorkspaceTab;
  onTabChange: (tab: WorkspaceTab) => void;
  selection: WorkspaceSelection | null;
  onSelect: (sel: WorkspaceSelection) => void;
};

type LazyKey = string;

function statusDot(recordStatus?: string) {
  return recordStatus === "confirmed" ? (
    <Tag color="green" style={{ marginInlineStart: 4, fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
      定
    </Tag>
  ) : (
    <Tag style={{ marginInlineStart: 4, fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
      AI
    </Tag>
  );
}

function titleOf(label: string, recordStatus?: string) {
  return (
    <span>
      {label}
      {statusDot(recordStatus)}
    </span>
  );
}

export function WorkspaceTree({
  projectId,
  tab,
  onTabChange,
  selection,
  onSelect,
}: Props) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const [spaceChildren, setSpaceChildren] = useState<
    Record<string, DataNode[]>
  >({});
  /** 片段 / 分镜 → 所属叙事空间，供选中时回填 */
  const [ownerSpace, setOwnerSpace] = useState<Record<string, string>>({});
  const [ownerEpisode, setOwnerEpisode] = useState<Record<string, string>>({});
  const [loadingKeys, setLoadingKeys] = useState<Set<LazyKey>>(new Set());

  const structure = useQuery({
    queryKey: ["script-workspace", "structure", projectId],
    queryFn: () => getScriptStructure(projectId),
  });

  const assets = useQuery({
    queryKey: ["script-workspace", "assets", projectId],
    queryFn: () => getScriptAssets(projectId),
    enabled: tab === "material",
  });

  const scenes = useQuery({
    queryKey: ["script-workspace", "scenes", projectId],
    queryFn: () => listSceneSpaces(projectId),
    enabled: tab === "material",
  });

  const prompts = useQuery({
    queryKey: ["script-workspace", "prompts", projectId],
    queryFn: () => listMaterialPrompts(projectId),
    enabled: tab === "material",
  });

  const images = useQuery({
    queryKey: ["script-workspace", "images", projectId],
    queryFn: () => listMaterialImages(projectId),
    enabled: tab === "material",
  });

  const loadSpaceChildren = useCallback(
    async (spaceId: string, episodeId: string) => {
      if (spaceChildren[spaceId] || loadingKeys.has(spaceId)) return;
      setLoadingKeys((prev) => new Set(prev).add(spaceId));
      try {
        const [segBundle, shotBundle] = await Promise.all([
          listVideoSegments(projectId, spaceId),
          listShots(projectId, spaceId),
        ]);
        const shotsById = new Map(
          (shotBundle.items || []).map((s: ShotPlan) => [s.id, s]),
        );
        const nodes: DataNode[] = (segBundle.items || []).map(
          (seg: VideoSegment) => {
            const childShots = (seg.shot_ids || [])
              .map((id) => shotsById.get(id))
              .filter(Boolean) as ShotPlan[];
            // 未编入任何片段的分镜挂在「未分组」下
            return {
              key: `segment:${seg.id}`,
              title: titleOf(
                seg.title || `片段 ${seg.ordinal}`,
                seg.record_status,
              ),
              isLeaf: childShots.length === 0,
              children: childShots.map((shot) => ({
                key: `shot:${shot.id}`,
                title: titleOf(
                  `镜 ${shot.ordinal}${shot.beat ? ` · ${shot.beat.slice(0, 16)}` : ""}`,
                  shot.record_status,
                ),
                isLeaf: true,
              })),
            };
          },
        );

        const groupedIds = new Set(
          (segBundle.items || []).flatMap((s) => s.shot_ids || []),
        );
        const ungrouped = (shotBundle.items || []).filter(
          (s) => !groupedIds.has(s.id),
        );
        if (ungrouped.length) {
          nodes.push({
            key: `ungrouped:${spaceId}`,
            title: `未编组分镜（${ungrouped.length}）`,
            children: ungrouped.map((shot) => ({
              key: `shot:${shot.id}`,
              title: titleOf(
                `镜 ${shot.ordinal}${shot.beat ? ` · ${shot.beat.slice(0, 16)}` : ""}`,
                shot.record_status,
              ),
              isLeaf: true,
            })),
          });
        }
        if (!nodes.length) {
          nodes.push({
            key: `empty-space:${spaceId}`,
            title: "暂无片段 / 分镜",
            isLeaf: true,
            disabled: true,
          });
        }
        setSpaceChildren((prev) => ({ ...prev, [spaceId]: nodes }));
        const nextOwner: Record<string, string> = {};
        const nextEp: Record<string, string> = {};
        for (const seg of segBundle.items || []) {
          nextOwner[`segment:${seg.id}`] = spaceId;
          nextEp[`segment:${seg.id}`] = episodeId;
          for (const sid of seg.shot_ids || []) {
            nextOwner[`shot:${sid}`] = spaceId;
            nextEp[`shot:${sid}`] = episodeId;
          }
        }
        for (const shot of shotBundle.items || []) {
          nextOwner[`shot:${shot.id}`] = spaceId;
          nextEp[`shot:${shot.id}`] = episodeId;
        }
        setOwnerSpace((prev) => ({ ...prev, ...nextOwner }));
        setOwnerEpisode((prev) => ({ ...prev, ...nextEp }));
      } catch (e) {
        message.error(e instanceof Error ? e.message : "加载片段失败");
      } finally {
        setLoadingKeys((prev) => {
          const next = new Set(prev);
          next.delete(spaceId);
          return next;
        });
      }
    },
    [loadingKeys, projectId, spaceChildren],
  );

  const videoTree: DataNode[] = useMemo(() => {
    const episodes: Episode[] = structure.data?.items || [];
    return episodes.map((ep) => ({
      key: `episode:${ep.id}`,
      title: titleOf(`第 ${ep.ordinal} 集 ${ep.title || ""}`.trim(), ep.record_status),
      children: (ep.narrative_spaces || []).map((ns) => ({
        key: `space:${ns.id}`,
        title: titleOf(
          `${ns.ordinal}. ${ns.title || "叙事空间"}`,
          ns.record_status,
        ),
        children: spaceChildren[ns.id],
      })),
    }));
  }, [spaceChildren, structure.data?.items]);

  const materialTree: DataNode[] = useMemo(() => {
    const chars = assets.data?.characters || [];
    const props = assets.data?.props || [];
    const owned = props.filter((p) => p.scope !== "scene");
    const sceneProps = props.filter((p) => p.scope === "scene");
    const promptByTarget = new Map(
      (prompts.data?.items || []).map((p) => [`${p.target_type}:${p.target_id}`, p]),
    );
    const imagesBySource = new Map<string, MaterialImage[]>();
    for (const img of images.data?.items || []) {
      const key = `${img.source_kind || ""}:${img.source_id || ""}`;
      const list = imagesBySource.get(key) || [];
      list.push(img);
      imagesBySource.set(key, list);
    }

    const assetChildren = (
      kind: "character" | "prop",
      id: string,
      label: string,
      recordStatus?: string,
    ): DataNode => {
      const prompt = promptByTarget.get(`${kind}:${id}`);
      const imgs = imagesBySource.get(`${kind}:${id}`) || [];
      const children: DataNode[] = [];
      if (prompt) {
        children.push({
          key: `material_prompt:${prompt.id}`,
          title: titleOf(`提示词 v${prompt.version}`, prompt.record_status),
          isLeaf: true,
        });
      }
      for (const img of imgs) {
        children.push({
          key: `material_image:${img.id}`,
          title: img.label || "物料图",
          isLeaf: true,
        });
      }
      return {
        key: `${kind}:${id}`,
        title: titleOf(label, recordStatus),
        isLeaf: children.length === 0,
        children: children.length ? children : undefined,
      };
    };

    return [
      {
        key: "group:characters",
        title: `人物（${chars.length}）`,
        children: chars.map((c) =>
          assetChildren("character", c.id, c.name, c.record_status),
        ),
      },
      {
        key: "group:owned-props",
        title: `归属道具（${owned.length}）`,
        children: owned.map((p) =>
          assetChildren(
            "prop",
            p.id,
            `${p.prop_name}${p.owner_name ? ` · ${p.owner_name}` : ""}`,
            p.record_status,
          ),
        ),
      },
      {
        key: "group:scene-props",
        title: `场景公物（${sceneProps.length}）`,
        children: sceneProps.map((p) =>
          assetChildren("prop", p.id, p.prop_name, p.record_status),
        ),
      },
      {
        key: "group:scenes",
        title: `地点（${scenes.data?.items?.length || 0}）`,
        children: (scenes.data?.items || []).map((s) => ({
          key: `scene_space:${s.id}`,
          title: titleOf(s.name, s.record_status),
          isLeaf: true,
        })),
      },
    ];
  }, [assets.data, images.data?.items, prompts.data?.items, scenes.data?.items]);

  const onLoadData = async (node: EventDataNode<DataNode>) => {
    const key = String(node.key);
    if (!key.startsWith("space:")) return;
    const spaceId = key.slice("space:".length);
    // 从 structure 找回 episode_id
    let episodeId = "";
    for (const ep of structure.data?.items || []) {
      if ((ep.narrative_spaces || []).some((ns) => ns.id === spaceId)) {
        episodeId = ep.id;
        break;
      }
    }
    await loadSpaceChildren(spaceId, episodeId);
  };

  const resolveSelection = (key: string): WorkspaceSelection | null => {
    if (key.startsWith("episode:")) {
      const id = key.slice("episode:".length);
      const ep = (structure.data?.items || []).find((e) => e.id === id);
      return {
        type: "episode",
        id,
        project_id: projectId,
        episode_id: id,
        title: ep ? `第 ${ep.ordinal} 集` : id,
      };
    }
    if (key.startsWith("space:")) {
      const id = key.slice("space:".length);
      for (const ep of structure.data?.items || []) {
        const ns = (ep.narrative_spaces || []).find((n) => n.id === id);
        if (ns) {
          return {
            type: "narrative_space",
            id,
            project_id: projectId,
            episode_id: ep.id,
            narrative_space_id: id,
            title: ns.title,
          };
        }
      }
    }
    if (key.startsWith("segment:")) {
      const id = key.slice("segment:".length);
      return {
        type: "video_segment",
        id,
        project_id: projectId,
        episode_id: ownerEpisode[key],
        narrative_space_id: ownerSpace[key],
        video_segment_id: id,
        title: `片段 ${id.slice(-6)}`,
      };
    }
    if (key.startsWith("shot:")) {
      const id = key.slice("shot:".length);
      return {
        type: "shot",
        id,
        project_id: projectId,
        episode_id: ownerEpisode[key],
        narrative_space_id: ownerSpace[key],
        shot_id: id,
        title: `分镜 ${id.slice(-6)}`,
      };
    }
    if (key.startsWith("character:")) {
      const id = key.slice("character:".length);
      const c = (assets.data?.characters || []).find((x) => x.id === id);
      return {
        type: "character",
        id,
        project_id: projectId,
        title: c?.name || id,
      };
    }
    if (key.startsWith("prop:")) {
      const id = key.slice("prop:".length);
      const p = (assets.data?.props || []).find((x) => x.id === id);
      return {
        type: "prop",
        id,
        project_id: projectId,
        title: p?.prop_name || id,
      };
    }
    if (key.startsWith("scene_space:")) {
      const id = key.slice("scene_space:".length);
      const s = (scenes.data?.items || []).find((x) => x.id === id);
      return {
        type: "scene_space",
        id,
        project_id: projectId,
        title: s?.name || id,
      };
    }
    if (key.startsWith("material_prompt:")) {
      const id = key.slice("material_prompt:".length);
      return {
        type: "material_prompt",
        id,
        project_id: projectId,
        title: "物料提示词",
      };
    }
    if (key.startsWith("material_image:")) {
      const id = key.slice("material_image:".length);
      return {
        type: "material_image",
        id,
        project_id: projectId,
        title: "物料图",
      };
    }
    return null;
  };

  const selectedKeys = selection
    ? [
        selection.type === "narrative_space"
          ? `space:${selection.id}`
          : selection.type === "video_segment"
            ? `segment:${selection.id}`
            : selection.type === "shot"
              ? `shot:${selection.id}`
              : selection.type === "episode"
                ? `episode:${selection.id}`
                : `${selection.type}:${selection.id}`,
      ]
    : [];

  return (
    <div className="script-workspace__left">
      <Tabs
        size="small"
        activeKey={tab}
        onChange={(k) => onTabChange(k as WorkspaceTab)}
        items={[
          { key: "video", label: "视频类" },
          { key: "material", label: "素材类" },
        ]}
        style={{ paddingInline: 8, marginBottom: 0 }}
      />
      <div className="script-workspace__scroll script-workspace__tree">
        {tab === "video" ? (
          structure.isLoading ? (
            <div className="script-workspace__empty">
              <Spin />
            </div>
          ) : (structure.data?.items || []).length === 0 ? (
            <div className="script-workspace__empty">
              <Typography.Text type="secondary">
                暂无结构。请先上传剧本并在旧工坊或对话中做规则粗切 / 语义切分。
              </Typography.Text>
            </div>
          ) : (
            <Tree
              showLine
              treeData={videoTree}
              loadData={onLoadData}
              expandedKeys={expanded}
              onExpand={(keys) => setExpanded(keys.map(String))}
              selectedKeys={selectedKeys}
              onSelect={(_, info) => {
                const sel = resolveSelection(String(info.node.key));
                if (sel) onSelect(sel);
              }}
            />
          )
        ) : assets.isLoading ? (
          <div className="script-workspace__empty">
            <Spin />
          </div>
        ) : (
          <Tree
            showLine
            treeData={materialTree}
            selectedKeys={selectedKeys}
            onSelect={(_, info) => {
              const sel = resolveSelection(String(info.node.key));
              if (sel) onSelect(sel);
            }}
          />
        )}
      </div>
    </div>
  );
}
