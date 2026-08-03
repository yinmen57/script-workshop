/**
 * 中栏素材展示：选中人物/道具/提示词/图片时展示详情。
 */
import { Button, Empty, Image, Space, Tag, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmMaterialPrompt,
  confirmScriptAsset,
  getScriptAssets,
  listMaterialImages,
  listMaterialPrompts,
} from "../../../api/business/scriptBiz";
import type { WorkspaceSelection } from "./types";

type Props = {
  projectId: string;
  selection: WorkspaceSelection | null;
};

export function MaterialPane({ projectId, selection }: Props) {
  const queryClient = useQueryClient();
  const assets = useQuery({
    queryKey: ["script-workspace", "assets", projectId],
    queryFn: () => getScriptAssets(projectId),
  });
  const prompts = useQuery({
    queryKey: ["script-workspace", "prompts", projectId],
    queryFn: () => listMaterialPrompts(projectId),
  });
  const images = useQuery({
    queryKey: ["script-workspace", "images", projectId],
    queryFn: () => listMaterialImages(projectId),
  });

  const confirmAssetMut = useMutation({
    mutationFn: (body: { target_type: "character" | "prop"; target_id: string }) =>
      confirmScriptAsset(projectId, body),
    onSuccess: () => {
      message.success("已定版");
      void queryClient.invalidateQueries({ queryKey: ["script-workspace"] });
    },
    onError: (e) =>
      message.error(e instanceof Error ? e.message : "定版失败"),
  });

  const confirmPromptMut = useMutation({
    mutationFn: (promptId: string) => confirmMaterialPrompt(projectId, promptId),
    onSuccess: () => {
      message.success("提示词已定版");
      void queryClient.invalidateQueries({ queryKey: ["script-workspace"] });
    },
    onError: (e) =>
      message.error(e instanceof Error ? e.message : "定版失败"),
  });

  if (!selection) {
    return (
      <div className="script-workspace__empty">
        <Empty description="从左侧素材树选择人物、道具或地点" />
      </div>
    );
  }

  if (selection.type === "character" || selection.type === "prop") {
    const character = (assets.data?.characters || []).find(
      (c) => c.id === selection.id,
    );
    const prop = (assets.data?.props || []).find((p) => p.id === selection.id);
    const prompt = (prompts.data?.items || []).find(
      (p) =>
        p.target_type === selection.type && p.target_id === selection.id,
    );
    const imgs = (images.data?.items || []).filter(
      (img) =>
        img.source_kind === selection.type && img.source_id === selection.id,
    );
    const title =
      selection.type === "character"
        ? character?.name || selection.title
        : prop?.prop_name || selection.title;
    const anchor =
      selection.type === "character"
        ? character?.appearance_anchor
        : prop?.visual_anchor;

    return (
      <div className="script-workspace__material">
        <Space style={{ marginBottom: 8 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            {title}
          </Typography.Title>
          <Tag>{selection.type === "character" ? "人物" : "道具"}</Tag>
          <Tag color={selection.type === "character" ? (character?.record_status === "confirmed" ? "green" : undefined) : prop?.record_status === "confirmed" ? "green" : undefined}>
            {(selection.type === "character"
              ? character?.record_status
              : prop?.record_status) === "confirmed"
              ? "已确认"
              : "AI"}
          </Tag>
        </Space>
        <Typography.Paragraph type="secondary">{anchor || "暂无锚点描述"}</Typography.Paragraph>
        <Space style={{ marginBottom: 16 }}>
          <Button
            size="small"
            type="primary"
            loading={confirmAssetMut.isPending}
            onClick={() =>
              confirmAssetMut.mutate({
                target_type: selection.type as "character" | "prop",
                target_id: selection.id,
              })
            }
          >
            定版资产
          </Button>
          {prompt ? (
            <Button
              size="small"
              loading={confirmPromptMut.isPending}
              onClick={() => confirmPromptMut.mutate(prompt.id)}
            >
              定版提示词
            </Button>
          ) : null}
        </Space>
        {prompt ? (
          <>
            <Typography.Text strong>物料提示词 v{prompt.version}</Typography.Text>
            <div className="script-workspace__prompt" style={{ marginTop: 8 }}>
              {prompt.prompt_text}
            </div>
          </>
        ) : (
          <Typography.Text type="secondary">尚无物料提示词</Typography.Text>
        )}
        <div style={{ marginTop: 20 }}>
          <Typography.Text strong>物料图（{imgs.length}）</Typography.Text>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 }}>
            {imgs.map((img) => (
              <Image
                key={img.id}
                src={img.url}
                width={140}
                height={140}
                style={{ objectFit: "cover", borderRadius: 8 }}
              />
            ))}
            {!imgs.length ? (
              <Typography.Text type="secondary">暂无图片</Typography.Text>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (selection.type === "material_prompt") {
    const prompt = (prompts.data?.items || []).find((p) => p.id === selection.id);
    if (!prompt) {
      return (
        <div className="script-workspace__empty">
          <Empty description="提示词不存在" />
        </div>
      );
    }
    return (
      <div className="script-workspace__material">
        <Space style={{ marginBottom: 8 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            物料提示词
          </Typography.Title>
          <Tag>
            {prompt.target_type}:{prompt.target_id.slice(-6)}
          </Tag>
          <Tag color={prompt.record_status === "confirmed" ? "green" : undefined}>
            {prompt.record_status === "confirmed" ? "已确认" : "AI"}
          </Tag>
        </Space>
        <Button
          size="small"
          type="primary"
          style={{ marginBottom: 12 }}
          loading={confirmPromptMut.isPending}
          onClick={() => confirmPromptMut.mutate(prompt.id)}
        >
          定版
        </Button>
        <div className="script-workspace__prompt">{prompt.prompt_text}</div>
      </div>
    );
  }

  if (selection.type === "material_image") {
    const img = (images.data?.items || []).find((i) => i.id === selection.id);
    if (!img) {
      return (
        <div className="script-workspace__empty">
          <Empty description="图片不存在" />
        </div>
      );
    }
    return (
      <div className="script-workspace__material">
        <Typography.Title level={4}>{img.label || "物料图"}</Typography.Title>
        <Image src={img.url} style={{ maxWidth: 420, borderRadius: 10 }} />
      </div>
    );
  }

  if (selection.type === "scene_space") {
    return (
      <div className="script-workspace__material">
        <Typography.Title level={4}>{selection.title || "地点"}</Typography.Title>
        <Typography.Paragraph type="secondary">
          地点锚点详情可在对话中进一步生成或编辑。
        </Typography.Paragraph>
      </div>
    );
  }

  return (
    <div className="script-workspace__empty">
      <Empty description="当前选中不是素材对象" />
    </div>
  );
}
