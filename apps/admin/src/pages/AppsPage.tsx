import { Button, Space, Table, Tag, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { listApps, type AppItem } from "../api/resources";

export function AppsPage() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["apps"],
    queryFn: () => listApps(),
  });

  const columns = [
    { title: "应用空间", dataIndex: "name" },
    { title: "目录", dataIndex: "slug" },
    { title: "协调 Agent", dataIndex: "coordinator_agent_id" },
    {
      title: "Agent 数",
      dataIndex: "agent_count",
      render: (value: number | undefined) => value ?? 0,
    },
    { title: "说明", dataIndex: "description", ellipsis: true },
    {
      title: "加载状态",
      dataIndex: "load_status",
      render: (value: string) => (
        <Tag color={value === "ready" ? "green" : "red"}>
          {value === "ready" ? "已加载" : "配置错误"}
        </Tag>
      ),
    },
    { title: "最后加载", dataIndex: "loaded_at" },
    {
      title: "操作",
      render: (_: unknown, row: AppItem) => (
        <Space>
          {row.load_status === "ready" ? (
            <Button
              type="primary"
              size="small"
              onClick={() => navigate(`/apps/${row.slug}/playground`)}
            >
              打开调试台
            </Button>
          ) : null}
          <Button size="small" onClick={() => navigate(`/apps/${row.slug}`)}>
            查看配置
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={3}>应用空间</Typography.Title>
      <Typography.Paragraph type="secondary">
        编辑 apps-space 下的文件即可定义应用；保存后刷新本页生效（按目录 mtime 热重载）。每个空间对应
        一个调试台。
      </Typography.Paragraph>
      <Table rowKey="slug" loading={isLoading} columns={columns} dataSource={data?.items || []} />
    </div>
  );
}
