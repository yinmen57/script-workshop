/**
 * 知识库面板：与工作台分离。
 * 工作台 DB = 唯一事实；知识库 = 可重建检索副本 + 工艺规范命名空间。
 */
import { Alert, Button, Descriptions, Space, Tag, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getProjectKnowledgeStatus,
  indexProjectKnowledge,
} from "../../../api/business/scriptBiz";

type Props = {
  projectId: string | null;
};

const STATUS_LABEL: Record<string, { text: string; color: string }> = {
  empty: { text: "无可索引内容", color: "default" },
  not_indexed: { text: "未索引", color: "orange" },
  indexed: { text: "已索引", color: "green" },
};

export function KnowledgePane({ projectId }: Props) {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["script-workspace", "knowledge-status", projectId],
    queryFn: () => getProjectKnowledgeStatus(projectId!),
    enabled: !!projectId,
  });

  const indexMut = useMutation({
    mutationFn: () => indexProjectKnowledge(projectId!),
    onSuccess: () => {
      message.success("项目知识库已重建");
      void queryClient.invalidateQueries({
        queryKey: ["script-workspace", "knowledge-status", projectId],
      });
    },
    onError: (e) =>
      message.error(e instanceof Error ? e.message : "索引失败"),
  });

  if (!projectId) {
    return (
      <div className="script-workspace__knowledge">
        <div className="script-workspace__empty">请先选择项目</div>
      </div>
    );
  }

  const data = status.data;
  const badge = STATUS_LABEL[data?.status || ""] || {
    text: "加载中",
    color: "default",
  };

  return (
    <div className="script-workspace__knowledge">
      <div className="script-workspace__panel-title">项目知识库</div>
      <div className="script-workspace__scroll" style={{ padding: 16 }}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="职责分离"
          description="工作台数据库是人物、场景、确认状态与参考图的唯一事实来源。知识库只保存可重建的检索副本与工艺规范，生成时由 ConsistencyPack 组装，不得用旧副本覆盖已确认资产。"
        />

        <Space style={{ marginBottom: 16 }}>
          <Tag color={badge.color}>{badge.text}</Tag>
          <Button
            type="primary"
            loading={indexMut.isPending}
            disabled={data?.status === "empty"}
            onClick={() => indexMut.mutate()}
          >
            重建索引
          </Button>
          <Button
            loading={status.isFetching}
            onClick={() => void status.refetch()}
          >
            刷新状态
          </Button>
        </Space>

        {status.isLoading ? (
          <Typography.Text type="secondary">加载中…</Typography.Text>
        ) : data ? (
          <>
            <Descriptions
              size="small"
              column={1}
              bordered
              title="工作台事实（源）"
              style={{ marginBottom: 16 }}
            >
              <Descriptions.Item label="叙事空间">
                {data.workspace.narrative_space_count}
              </Descriptions.Item>
              <Descriptions.Item label="人物">
                {data.workspace.character_count}
              </Descriptions.Item>
              <Descriptions.Item label="场景">
                {data.workspace.scene_space_count}
              </Descriptions.Item>
              <Descriptions.Item label="预计文档数">
                {data.workspace.fact_document_estimate}
              </Descriptions.Item>
            </Descriptions>

            <Descriptions
              size="small"
              column={1}
              bordered
              title="向量索引（副本）"
              style={{ marginBottom: 16 }}
            >
              <Descriptions.Item label="命名空间">
                <Typography.Text code>{data.namespace}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="chunk 数">
                {data.index.chunk_count}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {data.index.updated_at || "—"}
              </Descriptions.Item>
              <Descriptions.Item label="角色">
                {data.role} / 事实源={data.source_of_truth}
              </Descriptions.Item>
            </Descriptions>

            <Typography.Title level={5}>工艺规范命名空间</Typography.Title>
            <Space wrap>
              {(data.craft_namespaces || []).map((ns) => (
                <Tag key={ns}>{ns}</Tag>
              ))}
            </Space>
            <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>
              工艺规范由 workspace 语料入库，全租户共享；项目索引只含本项目叙事/人物/场景副本。
            </Typography.Paragraph>
          </>
        ) : (
          <Typography.Text type="danger">无法加载知识库状态</Typography.Text>
        )}
      </div>
    </div>
  );
}
