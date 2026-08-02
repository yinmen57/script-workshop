import {
  Button,
  Card,
  Collapse,
  Descriptions,
  Empty,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { getWorkspace } from "../api/resources";

export function AgentWorkspacePage() {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const workspace = useQuery({
    queryKey: ["workspace", slug],
    queryFn: () => getWorkspace(slug),
    enabled: Boolean(slug),
  });

  if (workspace.isLoading) return <Typography.Text>加载中…</Typography.Text>;
  if (!workspace.data) return <Empty description="应用空间不存在或加载失败" />;
  const data = workspace.data;

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate("/apps")}>返回应用空间</Button>
        {data.load_status === "ready" ? (
          <Button type="primary" onClick={() => navigate(`/apps/${data.slug}/playground`)}>
            打开调试台
          </Button>
        ) : null}
      </Space>
      <Typography.Title level={3}>{data.name}</Typography.Title>
      <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="目录">{data.workspace_path}</Descriptions.Item>
        <Descriptions.Item label="协作模式">
          <Tag color="blue">{data.collaboration_mode || "langgraph_multi_agent"}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="协调 Agent">{data.coordinator_agent_id}</Descriptions.Item>
        <Descriptions.Item label="加载状态">
          <Tag color={data.load_status === "ready" ? "green" : "red"}>{data.load_status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="主模型">{data.model.primary || "-"}</Descriptions.Item>
        <Descriptions.Item label="最大步数">{data.max_steps ?? "-"}</Descriptions.Item>
        <Descriptions.Item label="业务说明" span={2}>
          {data.description || "-"}
        </Descriptions.Item>
        {data.validation_error ? (
          <Descriptions.Item label="校验错误" span={2}>
            <Typography.Text type="danger">{data.validation_error}</Typography.Text>
          </Descriptions.Item>
        ) : null}
      </Descriptions>

      <Card title="知识库" style={{ marginBottom: 16 }}>
        {(data.knowledge || []).length ? (
          <Table
            rowKey="namespace"
            pagination={false}
            dataSource={data.knowledge}
            columns={[
              {
                title: "命名空间",
                dataIndex: "namespace",
                render: (v: string) => <Tag color="blue">{v}</Tag>,
              },
              {
                title: "语料目录",
                dataIndex: "dir",
                render: (v: string) => `knowledge/${v}`,
              },
              {
                title: "语料条目",
                dataIndex: "entry_count",
                width: 96,
              },
              {
                title: "索引状态",
                key: "indexed",
                width: 160,
                render: (_: unknown, row) =>
                  row.indexed ? (
                    <Space size={4} wrap>
                      <Tag color="green">已索引</Tag>
                      <Typography.Text type="secondary">
                        {row.chunk_count ?? 0} 片
                        {row.dimension ? ` · ${row.dimension}d` : ""}
                      </Typography.Text>
                    </Space>
                  ) : (
                    <Tag color="orange">未索引</Tag>
                  ),
              },
              {
                title: "引用 Agent",
                dataIndex: "used_by_agents",
                render: (agents: string[]) =>
                  agents?.length ? agents.map((id) => <Tag key={id}>{id}</Tag>) : "-",
              },
              {
                title: "说明",
                dataIndex: "description",
                ellipsis: true,
                render: (v: string) => v || "-",
              },
            ]}
          />
        ) : (
          <Empty description="本空间未声明 knowledge/manifest.yaml" />
        )}
      </Card>

      <Card title="协作 Agent" style={{ marginBottom: 16 }}>
        {data.agents?.length ? (
          <Collapse
            accordion
            items={(data.agents || []).map((agent) => ({
              key: agent.agent_id,
              label: (
                <Space wrap>
                  <span>
                    {agent.name} ({agent.agent_id})
                  </span>
                  <Tag color={agent.role === "coordinator" ? "gold" : "default"}>
                    {agent.role === "coordinator" ? "协调" : "专业"}
                  </Tag>
                  <Typography.Text type="secondary">
                    工具 {(agent.allowed_tools || []).length} · 提示词{" "}
                    {(agent.prompts || []).length}
                  </Typography.Text>
                </Space>
              ),
              children: (
                <div>
                  <Typography.Paragraph type="secondary">
                    {agent.description || "-"}
                  </Typography.Paragraph>
                  <Descriptions size="small" column={2} bordered style={{ marginBottom: 12 }}>
                    <Descriptions.Item label="系统提示词">
                      {agent.system_prompt_path}
                    </Descriptions.Item>
                    <Descriptions.Item label="步数上限">{agent.max_steps}</Descriptions.Item>
                    <Descriptions.Item label="可用工具" span={2}>
                      {(agent.allowed_tools || []).length
                        ? agent.allowed_tools.map((toolId) => <Tag key={toolId}>{toolId}</Tag>)
                        : "-"}
                    </Descriptions.Item>
                    <Descriptions.Item label="可检索命名空间" span={2}>
                      {(agent.namespaces || []).length
                        ? agent.namespaces.map((ns) => (
                            <Tag color="blue" key={ns}>
                              {ns}
                            </Tag>
                          ))
                        : "-"}
                    </Descriptions.Item>
                  </Descriptions>
                  <Collapse
                    size="small"
                    items={(agent.prompts || []).map((prompt) => ({
                      key: `${agent.agent_id}-${prompt.prompt_key}`,
                      label: `${prompt.prompt_key} · ${prompt.source_path}`,
                      children: (
                        <Typography.Paragraph
                          style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}
                        >
                          {prompt.content}
                        </Typography.Paragraph>
                      ),
                    }))}
                  />
                </div>
              ),
            }))}
          />
        ) : (
          <Empty description="未加载 Agent" />
        )}
      </Card>

      <Card title="共享工具库">
        <Table
          rowKey="id"
          pagination={false}
          dataSource={data.tools}
          columns={[
            { title: "工具", dataIndex: "name" },
            { title: "工具 ID", dataIndex: "id" },
            {
              title: "风险级别",
              dataIndex: "risk_level",
              render: (v: string) => <Tag>{v}</Tag>,
            },
            { title: "代码入口", dataIndex: "entrypoint" },
            { title: "定义位置", dataIndex: "source_path" },
          ]}
        />
      </Card>
    </div>
  );
}
