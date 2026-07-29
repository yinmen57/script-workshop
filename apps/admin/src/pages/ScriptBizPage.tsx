import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  confirmMaterialPrompt,
  confirmNarrativeSpace,
  confirmScriptAsset,
  confirmShot,
  createScriptProject,
  generateMaterialPrompts,
  getScriptAssets,
  getScriptStructure,
  listMaterialPrompts,
  listScriptDocuments,
  listScriptProjects,
  listShots,
  parseScriptProject,
  parseScriptStructure,
  planProjectShots,
  planSpaceShots,
  uploadScriptFile,
  type CharacterAsset,
  type MaterialPrompt,
  type NarrativeSpace,
  type PropAsset,
  type ScriptProject,
  type ShotPlan,
} from "../api/scriptBiz";
import axios from "axios";

function errMsg(e: unknown) {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.message || e.response?.data?.detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return e instanceof Error ? e.message : "请求失败";
}

function recordTag(v?: string) {
  if (v === "confirmed") return <Tag color="green">已确认</Tag>;
  return <Tag>AI</Tag>;
}

export function ScriptBizPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [parseOpen, setParseOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [active, setActive] = useState<ScriptProject | null>(null);
  const [form] = Form.useForm();
  const [parseForm] = Form.useForm();

  const projects = useQuery({
    queryKey: ["script-biz-projects"],
    queryFn: listScriptProjects,
  });

  const assets = useQuery({
    queryKey: ["script-biz-assets", active?.id],
    queryFn: () => getScriptAssets(active!.id),
    enabled: Boolean(active?.id),
  });

  const prompts = useQuery({
    queryKey: ["script-biz-prompts", active?.id],
    queryFn: () => listMaterialPrompts(active!.id),
    enabled: Boolean(active?.id),
  });

  const documents = useQuery({
    queryKey: ["script-biz-docs", active?.id],
    queryFn: () => listScriptDocuments(active!.id),
    enabled: Boolean(active?.id),
  });

  const structure = useQuery({
    queryKey: ["script-biz-structure", active?.id],
    queryFn: () => getScriptStructure(active!.id),
    enabled: Boolean(active?.id),
  });

  const shots = useQuery({
    queryKey: ["script-biz-shots", active?.id],
    queryFn: () => listShots(active!.id),
    enabled: Boolean(active?.id),
  });

  const createMut = useMutation({
    mutationFn: createScriptProject,
    onSuccess: () => {
      message.success("项目已创建");
      setCreateOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["script-biz-projects"] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const parseMut = useMutation({
    mutationFn: (values: { script_text?: string; title?: string }) =>
      parseScriptProject(active!.id, {
        script_text: values.script_text || "",
        title: values.title,
      }),
    onSuccess: () => {
      message.success("解析完成（已确认资产不会被覆盖）");
      setParseOpen(false);
      parseForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["script-biz-projects"] });
      queryClient.invalidateQueries({ queryKey: ["script-biz-assets", active?.id] });
      queryClient.invalidateQueries({ queryKey: ["script-biz-docs", active?.id] });
      queryClient.invalidateQueries({ queryKey: ["script-biz-structure", active?.id] });
      queryClient.invalidateQueries({ queryKey: ["script-biz-prompts", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const materialMut = useMutation({
    mutationFn: () => generateMaterialPrompts(active!.id),
    onSuccess: (data) => {
      const skipped = data.skipped_confirmed ?? 0;
      message.success(
        skipped
          ? `已生成 ${data.total} 条，跳过 ${skipped} 条已确认`
          : `已生成 ${data.total} 条物料提示词`,
      );
      queryClient.invalidateQueries({ queryKey: ["script-biz-prompts", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const confirmAssetMut = useMutation({
    mutationFn: (body: { target_type: "character" | "prop"; target_id: string }) =>
      confirmScriptAsset(active!.id, body),
    onSuccess: () => {
      message.success("已确认，重解析不会覆盖");
      queryClient.invalidateQueries({ queryKey: ["script-biz-assets", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const confirmPromptMut = useMutation({
    mutationFn: (promptId: string) => confirmMaterialPrompt(active!.id, promptId),
    onSuccess: () => {
      message.success("提示词已确认");
      queryClient.invalidateQueries({ queryKey: ["script-biz-prompts", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const confirmNsMut = useMutation({
    mutationFn: (spaceId: string) => confirmNarrativeSpace(spaceId),
    onSuccess: () => {
      message.success("叙事空间已确认");
      queryClient.invalidateQueries({ queryKey: ["script-biz-structure", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const structureParseMut = useMutation({
    mutationFn: () => parseScriptStructure(active!.id),
    onSuccess: (data) => {
      message.success(
        `结构已解析：${data.parsed.episode_count} 集 / ${data.parsed.narrative_space_count} 个叙事空间`,
      );
      queryClient.invalidateQueries({ queryKey: ["script-biz-structure", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const planShotsMut = useMutation({
    mutationFn: () => planProjectShots(active!.id),
    onSuccess: (data) => {
      message.success(
        `已规划 ${data.space_count} 个叙事空间，共 ${data.total} 个分镜`,
      );
      queryClient.invalidateQueries({ queryKey: ["script-biz-shots", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const planSpaceShotsMut = useMutation({
    mutationFn: (spaceId: string) => planSpaceShots(spaceId),
    onSuccess: (data) => {
      message.success(`该空间已规划 ${data.total} 个分镜`);
      queryClient.invalidateQueries({ queryKey: ["script-biz-shots", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const confirmShotMut = useMutation({
    mutationFn: (shotId: string) => confirmShot(shotId),
    onSuccess: () => {
      message.success("分镜已定版");
      queryClient.invalidateQueries({ queryKey: ["script-biz-shots", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadScriptFile(active!.id, file),
    onSuccess: (data) => {
      const indexed = data.knowledge?.indexed ?? 0;
      message.success(
        `已转 Markdown 并入库（${data.markdown_chars} 字），知识库写入 ${indexed} 片`,
      );
      setUploadOpen(false);
      queryClient.invalidateQueries({ queryKey: ["script-biz-docs", active?.id] });
      queryClient.invalidateQueries({ queryKey: ["script-biz-projects"] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const structureRows =
    structure.data?.items.flatMap((ep) =>
      ep.narrative_spaces.map((ns) => ({
        ...ns,
        episode_title: ep.title,
        episode_ordinal: ep.ordinal,
      })),
    ) || [];

  const nsTitleById = new Map(
    structureRows.map((ns) => [ns.id, `${ns.episode_title || `第 ${ns.episode_ordinal} 集`} · ${ns.title}`]),
  );

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <div>
          <Typography.Title level={3} style={{ margin: 0 }}>
            剧本工坊
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            四级结构：剧本 → 集 → 叙事空间 → 分镜。AI 产物可确认后不被重解析覆盖。
          </Typography.Paragraph>
        </div>
        <Space>
          <Button onClick={() => navigate("/apps/script-workshop/playground")}>
            打开调试台
          </Button>
          <Button type="primary" onClick={() => setCreateOpen(true)}>
            新建项目
          </Button>
        </Space>
      </Space>

      <Card title="项目列表" style={{ marginBottom: 16 }}>
        <Table
          rowKey="id"
          loading={projects.isLoading}
          dataSource={projects.data?.items || []}
          pagination={false}
          columns={[
            { title: "名称", dataIndex: "name" },
            {
              title: "状态",
              dataIndex: "status",
              render: (v: string) => <Tag>{v}</Tag>,
            },
            { title: "更新时间", dataIndex: "updated_at" },
            {
              title: "操作",
              render: (_: unknown, row: ScriptProject) => (
                <Space>
                  <Button
                    size="small"
                    type={active?.id === row.id ? "primary" : "default"}
                    onClick={() => setActive(row)}
                  >
                    查看
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setActive(row);
                      setUploadOpen(true);
                    }}
                  >
                    上传剧本
                  </Button>
                  <Button
                    size="small"
                    onClick={() => {
                      setActive(row);
                      setParseOpen(true);
                    }}
                  >
                    解析
                  </Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      {active ? (
        <>
          <Card
            title={`剧本版本 · ${active.name}`}
            extra={
              <Space>
                <Button size="small" onClick={() => setUploadOpen(true)}>
                  上传文件
                </Button>
                <Button size="small" onClick={() => setParseOpen(true)}>
                  解析
                </Button>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              知识库命名空间：script/project/{active.id}
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              loading={documents.isLoading}
              pagination={false}
              dataSource={documents.data?.items || []}
              columns={[
                { title: "版本", dataIndex: "version", width: 72 },
                { title: "标题", dataIndex: "title" },
                {
                  title: "来源文件",
                  dataIndex: "source_filename",
                  render: (v: string | null) => v || "粘贴文本",
                },
                {
                  title: "格式",
                  dataIndex: "source_format",
                  render: (v: string | null) => v || "-",
                },
                {
                  title: "解析状态",
                  dataIndex: "parse_status",
                  render: (v: string) => <Tag>{v}</Tag>,
                },
                { title: "摘要", dataIndex: "raw_text", ellipsis: true },
              ]}
            />
          </Card>

          <Card
            title="目录结构 · 集 / 叙事空间"
            extra={
              <Button
                size="small"
                loading={structureParseMut.isPending}
                onClick={() => structureParseMut.mutate()}
                disabled={!documents.data?.items?.length}
              >
                仅解析结构
              </Button>
            }
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              规则切分：集标记 + 场景变化 / 转场 / 单空间约 ≤15s；不用 Hook/Escalation/Cliffhanger
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              loading={structure.isLoading}
              pagination={false}
              dataSource={structureRows}
              locale={{ emptyText: "上传剧本后点「仅解析结构」或完整「解析」" }}
              columns={[
                {
                  title: "集",
                  dataIndex: "episode_title",
                  width: 100,
                  render: (v: string, row: NarrativeSpace & { episode_ordinal: number }) =>
                    v || `第 ${row.episode_ordinal} 集`,
                },
                { title: "序号", dataIndex: "ordinal", width: 64 },
                { title: "叙事空间", dataIndex: "title", width: 160 },
                { title: "时空", dataIndex: "time_place", ellipsis: true },
                {
                  title: "估时",
                  dataIndex: "estimated_duration_sec",
                  width: 72,
                  render: (v: number | null | undefined) =>
                    v == null ? "-" : `${v}s`,
                },
                { title: "摘要", dataIndex: "summary", ellipsis: true },
                {
                  title: "记录态",
                  dataIndex: "record_status",
                  width: 96,
                  render: recordTag,
                },
                {
                  title: "操作",
                  width: 200,
                  render: (_: unknown, row: NarrativeSpace) => (
                    <Space size={4}>
                      <Button
                        size="small"
                        loading={planSpaceShotsMut.isPending}
                        onClick={() => planSpaceShotsMut.mutate(row.id)}
                      >
                        规划分镜
                      </Button>
                      {row.record_status === "confirmed" ? null : (
                        <Button
                          size="small"
                          loading={confirmNsMut.isPending}
                          onClick={() => confirmNsMut.mutate(row.id)}
                        >
                          确认
                        </Button>
                      )}
                    </Space>
                  ),
                },
              ]}
            />
          </Card>

          <Card
            title="分镜 · 挂叙事空间"
            extra={
              <Button
                size="small"
                loading={planShotsMut.isPending}
                onClick={() => planShotsMut.mutate()}
                disabled={!structureRows.length}
              >
                批量规划分镜
              </Button>
            }
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              一空间多镜头；已确认分镜重规划会跳过该空间。确认即定版并写入废稿历史。
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              loading={shots.isLoading}
              pagination={false}
              dataSource={shots.data?.items || []}
              locale={{ emptyText: "先解析结构，再点「规划分镜」" }}
              columns={[
                {
                  title: "叙事空间",
                  dataIndex: "narrative_space_id",
                  width: 180,
                  ellipsis: true,
                  render: (id: string) => nsTitleById.get(id) || id,
                },
                { title: "镜号", dataIndex: "ordinal", width: 64 },
                { title: "节拍", dataIndex: "beat", ellipsis: true },
                {
                  title: "镜头",
                  dataIndex: "camera",
                  ellipsis: true,
                  render: (v: ShotPlan["camera"]) => {
                    if (!v) return "-";
                    const desc =
                      (v.description as string) ||
                      (v.shot_type as string) ||
                      JSON.stringify(v);
                    return desc;
                  },
                },
                {
                  title: "时长",
                  dataIndex: "duration_sec",
                  width: 72,
                  render: (v: number | null | undefined) =>
                    v == null ? "-" : `${v}s`,
                },
                {
                  title: "记录态",
                  dataIndex: "record_status",
                  width: 96,
                  render: recordTag,
                },
                {
                  title: "操作",
                  width: 100,
                  render: (_: unknown, row: ShotPlan) =>
                    row.record_status === "confirmed" ? null : (
                      <Button
                        size="small"
                        loading={confirmShotMut.isPending}
                        onClick={() => confirmShotMut.mutate(row.id)}
                      >
                        确认
                      </Button>
                    ),
                },
              ]}
            />
          </Card>

          <Card
            title={`资产 · ${active.name}`}
            extra={
              <Button
                loading={materialMut.isPending}
                onClick={() => materialMut.mutate()}
                disabled={
                  assets.data?.characters?.length === 0 && assets.data?.props?.length === 0
                }
              >
                生成物料提示词
              </Button>
            }
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              已确认资产重解析不会被覆盖
            </Typography.Paragraph>
            <Typography.Title level={5}>人物</Typography.Title>
            <Table
              rowKey="id"
              size="small"
              loading={assets.isLoading}
              pagination={false}
              dataSource={assets.data?.characters || []}
              columns={[
                { title: "名称", dataIndex: "name" },
                { title: "key", dataIndex: "character_key" },
                { title: "外貌锚点", dataIndex: "appearance_anchor", ellipsis: true },
                { title: "状态", dataIndex: "status", width: 100 },
                {
                  title: "记录态",
                  dataIndex: "record_status",
                  width: 96,
                  render: recordTag,
                },
                {
                  title: "操作",
                  width: 100,
                  render: (_: unknown, row: CharacterAsset) =>
                    row.record_status === "confirmed" ? null : (
                      <Button
                        size="small"
                        loading={confirmAssetMut.isPending}
                        onClick={() =>
                          confirmAssetMut.mutate({
                            target_type: "character",
                            target_id: row.id,
                          })
                        }
                      >
                        确认
                      </Button>
                    ),
                },
              ]}
              style={{ marginBottom: 16 }}
            />
            <Typography.Title level={5}>道具</Typography.Title>
            <Table
              rowKey="id"
              size="small"
              loading={assets.isLoading}
              pagination={false}
              dataSource={assets.data?.props || []}
              columns={[
                { title: "名称", dataIndex: "prop_name" },
                { title: "归属", dataIndex: "owner_name", render: (v) => v || "场景" },
                { title: "key", dataIndex: "prop_key", ellipsis: true },
                { title: "外观锚点", dataIndex: "visual_anchor", ellipsis: true },
                { title: "状态", dataIndex: "status", width: 100 },
                {
                  title: "记录态",
                  dataIndex: "record_status",
                  width: 96,
                  render: recordTag,
                },
                {
                  title: "操作",
                  width: 100,
                  render: (_: unknown, row: PropAsset) =>
                    row.record_status === "confirmed" ? null : (
                      <Button
                        size="small"
                        loading={confirmAssetMut.isPending}
                        onClick={() =>
                          confirmAssetMut.mutate({
                            target_type: "prop",
                            target_id: row.id,
                          })
                        }
                      >
                        确认
                      </Button>
                    ),
                },
              ]}
            />
          </Card>

          <Card title="物料提示词">
            <Table
              rowKey="id"
              size="small"
              loading={prompts.isLoading}
              pagination={false}
              dataSource={prompts.data?.items || []}
              columns={[
                { title: "类型", dataIndex: "target_type", width: 96 },
                { title: "目标 ID", dataIndex: "target_id", ellipsis: true },
                { title: "版本", dataIndex: "version", width: 72 },
                { title: "提示词", dataIndex: "prompt_text", ellipsis: true },
                {
                  title: "记录态",
                  dataIndex: "record_status",
                  width: 96,
                  render: recordTag,
                },
                {
                  title: "操作",
                  width: 100,
                  render: (_: unknown, row: MaterialPrompt) =>
                    row.record_status === "confirmed" ? null : (
                      <Button
                        size="small"
                        loading={confirmPromptMut.isPending}
                        onClick={() => confirmPromptMut.mutate(row.id)}
                      >
                        确认
                      </Button>
                    ),
                },
              ]}
            />
          </Card>
        </>
      ) : null}

      <Modal
        title="新建剧本项目"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMut.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(values) => createMut.mutate(values)}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
            <Input placeholder="例如：狐狸面具第 1 集" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`上传剧本 · ${active?.name || ""}`}
        open={uploadOpen}
        onCancel={() => setUploadOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <Upload.Dragger
          multiple={false}
          maxCount={1}
          accept=".md,.markdown,.txt,.docx,.pdf,.html,.htm,.pptx,.xlsx,.csv"
          disabled={uploadMut.isPending}
          showUploadList={false}
          customRequest={async ({ file, onSuccess, onError }) => {
            try {
              await uploadMut.mutateAsync(file as File);
              onSuccess?.(null);
            } catch (err) {
              onError?.(err as Error);
            }
          }}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此处上传</p>
          <p className="ant-upload-hint">
            支持 md / txt / docx / pdf / html / pptx 等；将自动转为 Markdown 并写入知识库
          </p>
        </Upload.Dragger>
      </Modal>

      <Modal
        title={`解析剧本 · ${active?.name || ""}`}
        open={parseOpen}
        onCancel={() => setParseOpen(false)}
        onOk={() => parseForm.submit()}
        confirmLoading={parseMut.isPending}
        width={720}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          若已上传文件，可留空剧本文本，将解析最新版本；也可粘贴文本覆盖新建版本后解析。
          已确认的人物/道具/叙事空间不会被覆盖。
        </Typography.Paragraph>
        <Form
          form={parseForm}
          layout="vertical"
          onFinish={(values) => parseMut.mutate(values)}
        >
          <Form.Item name="title" label="标题">
            <Input placeholder="可选；上传解析时可留空" />
          </Form.Item>
          <Form.Item name="script_text" label="剧本文本（可选）">
            <Input.TextArea rows={12} placeholder="留空则使用已上传的最新剧本" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
