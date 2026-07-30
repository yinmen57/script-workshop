import {
  Button,
  Card,
  Collapse,
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
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  confirmMaterialPrompt,
  confirmNarrativeSpace,
  confirmScriptAsset,
  confirmShot,
  confirmVideoPrompt,
  createScriptProject,
  deleteNarrativeSpace,
  generateMaterialPrompts,
  generateProjectVideoPrompts,
  generateSpaceVideoPrompt,
  getScriptAssets,
  getScriptStructure,
  indexProjectKnowledge,
  listMaterialPrompts,
  listRevisions,
  listSceneSpaces,
  listScriptDocuments,
  listScriptProjects,
  listShots,
  listVideoJobs,
  listVideoPrompts,
  parseScriptProject,
  parseScriptStructure,
  planProjectShots,
  planSpaceShots,
  registerMaterialImage,
  renderMaterialImage,
  renderVideoPrompt,
  revertRevision,
  segmentScriptStructure,
  updateNarrativeSpace,
  uploadScriptFile,
  type CharacterAsset,
  type Episode,
  type MaterialPrompt,
  type NarrativeSpace,
  type PropAsset,
  type RecordRevision,
  type ScriptProject,
  type ShotPlan,
  type VideoPrompt,
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
  const [editNs, setEditNs] = useState<NarrativeSpace | null>(null);
  const [revisionTarget, setRevisionTarget] = useState<{
    type: string;
    id: string;
    label: string;
  } | null>(null);
  const [imageOpen, setImageOpen] = useState(false);
  const [active, setActive] = useState<ScriptProject | null>(null);
  const [form] = Form.useForm();
  const [parseForm] = Form.useForm();
  const [editNsForm] = Form.useForm();
  const [imageForm] = Form.useForm();

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

  const videoPrompts = useQuery({
    queryKey: ["script-biz-video-prompts", active?.id],
    queryFn: () => listVideoPrompts(active!.id),
    enabled: Boolean(active?.id),
  });

  const videoJobs = useQuery({
    queryKey: ["script-biz-video-jobs", active?.id],
    queryFn: () => listVideoJobs(active!.id),
    enabled: Boolean(active?.id),
  });

  const sceneSpaces = useQuery({
    queryKey: ["script-biz-scene-spaces", active?.id],
    queryFn: () => listSceneSpaces(active!.id),
    enabled: Boolean(active?.id),
  });

  const revisions = useQuery({
    queryKey: [
      "script-biz-revisions",
      revisionTarget?.type,
      revisionTarget?.id,
    ],
    queryFn: () => listRevisions(revisionTarget!.type, revisionTarget!.id),
    enabled: Boolean(revisionTarget?.type && revisionTarget?.id),
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
    onSuccess: (job) => {
      const result = (job.result || {}) as {
        total?: number;
        skipped_confirmed?: number;
      };
      const skipped = result.skipped_confirmed ?? 0;
      message.success(
        skipped
          ? `已生成 ${result.total ?? 0} 条，跳过 ${skipped} 条已确认`
          : `已生成 ${result.total ?? 0} 条物料提示词`,
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

  const structureSegmentMut = useMutation({
    mutationFn: () => segmentScriptStructure(active!.id),
    onSuccess: (job) => {
      const parsed = (job.result || {}) as {
        episode_count?: number;
        narrative_space_count?: number;
      };
      message.success(
        `语义切分完成：${parsed.episode_count ?? 0} 集 / ${parsed.narrative_space_count ?? 0} 个叙事空间`,
      );
      queryClient.invalidateQueries({ queryKey: ["script-biz-structure", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const indexKnowledgeMut = useMutation({
    mutationFn: () => indexProjectKnowledge(active!.id),
    onSuccess: (job) => {
      const result = (job.result || {}) as {
        narrative_space_count?: number;
        indexed?: number;
      };
      message.success(
        `已按叙事空间入库：${result.narrative_space_count ?? 0} 个空间 / ${result.indexed ?? 0} 块`,
      );
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const planShotsMut = useMutation({
    mutationFn: () => planProjectShots(active!.id),
    onSuccess: (job) => {
      const result = (job.result || {}) as {
        space_count?: number;
        total?: number;
      };
      message.success(
        `已规划 ${result.space_count ?? 0} 个叙事空间，共 ${result.total ?? 0} 个分镜`,
      );
      queryClient.invalidateQueries({ queryKey: ["script-biz-shots", active?.id] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const planSpaceShotsMut = useMutation({
    mutationFn: (spaceId: string) => planSpaceShots(spaceId),
    onSuccess: (job) => {
      const result = (job.result || {}) as { total?: number };
      message.success(`该空间已规划 ${result.total ?? 0} 个分镜`);
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

  const genVideoMut = useMutation({
    mutationFn: () => generateProjectVideoPrompts(active!.id),
    onSuccess: (job) => {
      const result = (job.result || {}) as { space_count?: number };
      message.success(
        `已生成 ${result.space_count ?? 0} 个叙事空间的成片提示词`,
      );
      queryClient.invalidateQueries({
        queryKey: ["script-biz-video-prompts", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const genSpaceVideoMut = useMutation({
    mutationFn: (spaceId: string) => generateSpaceVideoPrompt(spaceId),
    onSuccess: () => {
      message.success("该空间成片提示词已生成");
      queryClient.invalidateQueries({
        queryKey: ["script-biz-video-prompts", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const confirmVideoMut = useMutation({
    mutationFn: (promptId: string) => confirmVideoPrompt(promptId),
    onSuccess: () => {
      message.success("成片提示词已定版");
      queryClient.invalidateQueries({
        queryKey: ["script-biz-video-prompts", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const updateNsMut = useMutation({
    mutationFn: (values: {
      title?: string;
      summary?: string;
      time_place?: string;
      ordinal?: number | string;
    }) =>
      updateNarrativeSpace(editNs!.id, {
        ...values,
        ordinal:
          values.ordinal === undefined || values.ordinal === ""
            ? undefined
            : Number(values.ordinal),
      }),
    onSuccess: () => {
      message.success("叙事空间已更新");
      setEditNs(null);
      queryClient.invalidateQueries({
        queryKey: ["script-biz-structure", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const deleteNsMut = useMutation({
    mutationFn: (spaceId: string) => deleteNarrativeSpace(spaceId),
    onSuccess: () => {
      message.success("已删除");
      queryClient.invalidateQueries({
        queryKey: ["script-biz-structure", active?.id],
      });
      queryClient.invalidateQueries({ queryKey: ["script-biz-shots", active?.id] });
      queryClient.invalidateQueries({
        queryKey: ["script-biz-video-prompts", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const revertMut = useMutation({
    mutationFn: (revisionId: string) => revertRevision(revisionId),
    onSuccess: (data) => {
      message.success("已反悔写回");
      queryClient.invalidateQueries({
        queryKey: ["script-biz-revisions", data.target_type, data.target_id],
      });
      queryClient.invalidateQueries({
        queryKey: ["script-biz-structure", active?.id],
      });
      queryClient.invalidateQueries({ queryKey: ["script-biz-shots", active?.id] });
      queryClient.invalidateQueries({
        queryKey: ["script-biz-video-prompts", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const registerImageMut = useMutation({
    mutationFn: (values: {
      url: string;
      label?: string;
      source_kind?: string;
      source_id?: string;
    }) =>
      registerMaterialImage(active!.id, {
        url: values.url,
        label: values.label,
        origin: "uploaded",
        source_kind: values.source_kind,
        source_id: values.source_id,
      }),
    onSuccess: () => {
      message.success("图片已登记到目录");
      setImageOpen(false);
      imageForm.resetFields();
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const renderImageMut = useMutation({
    mutationFn: (promptId: string) => renderMaterialImage(promptId),
    onSuccess: (job) => {
      const result = (job.result || {}) as { url?: string };
      message.success(result.url ? `物料图已生成` : "生图作业完成");
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const renderVideoMut = useMutation({
    mutationFn: (promptId: string) => renderVideoPrompt(promptId),
    onSuccess: () => {
      message.success("成片视频已生成");
      queryClient.invalidateQueries({
        queryKey: ["script-biz-video-jobs", active?.id],
      });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadScriptFile(active!.id, file),
    onSuccess: (data) => {
      message.success(`已转 Markdown 并入库（${data.markdown_chars} 字）`);
      setUploadOpen(false);
      queryClient.invalidateQueries({ queryKey: ["script-biz-docs", active?.id] });
      queryClient.invalidateQueries({ queryKey: ["script-biz-projects"] });
    },
    onError: (e: unknown) => message.error(errMsg(e)),
  });

  // 集按 ordinal 升序；集内叙事空间也按 ordinal 升序（手风琴维度）
  const episodesSorted: Episode[] = useMemo(() => {
    const items = [...(structure.data?.items || [])];
    items.sort((a, b) => a.ordinal - b.ordinal);
    return items.map((ep) => ({
      ...ep,
      narrative_spaces: [...(ep.narrative_spaces || [])].sort(
        (a, b) => a.ordinal - b.ordinal,
      ),
    }));
  }, [structure.data?.items]);

  const structureRows =
    episodesSorted.flatMap((ep) =>
      ep.narrative_spaces.map((ns) => ({
        ...ns,
        episode_title: ep.title,
        episode_ordinal: ep.ordinal,
      })),
    ) || [];

  const nsTitleById = new Map(
    structureRows.map((ns) => [
      ns.id,
      `${ns.episode_title || `第 ${ns.episode_ordinal} 集`} · ${ns.title}`,
    ]),
  );

  const nsActionColumns = [
    { title: "序号", dataIndex: "ordinal", width: 64 },
    { title: "叙事空间", dataIndex: "title", width: 160 },
    { title: "时空", dataIndex: "time_place", ellipsis: true },
    {
      title: "估时",
      dataIndex: "estimated_duration_sec",
      width: 72,
      render: (v: number | null | undefined) => (v == null ? "-" : `${v}s`),
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
      width: 320,
      render: (_: unknown, row: NarrativeSpace) => (
        <Space size={4} wrap>
          <Button
            size="small"
            type="primary"
            onClick={() => navigate(`/script-biz/canvas/${row.id}`)}
          >
            画布
          </Button>
          <Button
            size="small"
            loading={planSpaceShotsMut.isPending}
            onClick={() => planSpaceShotsMut.mutate(row.id)}
          >
            规划分镜
          </Button>
          <Button
            size="small"
            loading={genSpaceVideoMut.isPending}
            onClick={() => genSpaceVideoMut.mutate(row.id)}
          >
            成片提示词
          </Button>
          <Button
            size="small"
            onClick={() => {
              setEditNs(row);
              editNsForm.setFieldsValue({
                title: row.title,
                summary: row.summary,
                time_place: row.time_place,
                ordinal: row.ordinal,
              });
            }}
          >
            编辑
          </Button>
          <Button
            size="small"
            onClick={() =>
              setRevisionTarget({
                type: "narrative_space",
                id: row.id,
                label: row.title,
              })
            }
          >
            历史
          </Button>
          {row.record_status === "confirmed" ? null : (
            <>
              <Button
                size="small"
                loading={confirmNsMut.isPending}
                onClick={() => confirmNsMut.mutate(row.id)}
              >
                确认
              </Button>
              <Button
                size="small"
                danger
                loading={deleteNsMut.isPending}
                onClick={() => deleteNsMut.mutate(row.id)}
              >
                删除
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

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
              <Space>
                <Button
                  size="small"
                  loading={structureParseMut.isPending}
                  onClick={() => structureParseMut.mutate()}
                  disabled={!documents.data?.items?.length}
                >
                  规则粗切
                </Button>
                <Button
                  size="small"
                  type="primary"
                  loading={structureSegmentMut.isPending}
                  onClick={() => structureSegmentMut.mutate()}
                  disabled={!documents.data?.items?.length}
                >
                  语义切分
                </Button>
                <Button
                  size="small"
                  loading={indexKnowledgeMut.isPending}
                  onClick={() => indexKnowledgeMut.mutate()}
                  disabled={!episodesSorted.length}
                >
                  入知识库
                </Button>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              手风琴按「集」展开；集与叙事空间均按序号升序。规则粗切只看集标记与地点 /
              转场；语义切分再交 LLM 判定一场戏的边界，长度不设限，成片按视频片段分段。
            </Typography.Paragraph>
            {structure.isLoading ? (
              <Typography.Text type="secondary">加载目录…</Typography.Text>
            ) : !episodesSorted.length ? (
              <Typography.Text type="secondary">
                上传剧本后点「仅解析结构」或完整「解析」
              </Typography.Text>
            ) : (
              <Collapse
                accordion
                defaultActiveKey={episodesSorted[0]?.id}
                items={episodesSorted.map((ep) => ({
                  key: ep.id,
                  label: (
                    <Space>
                      <Typography.Text strong>
                        {ep.title || `第 ${ep.ordinal} 集`}
                      </Typography.Text>
                      <Tag>{ep.narrative_spaces.length} 个叙事空间</Tag>
                      {recordTag(ep.record_status)}
                    </Space>
                  ),
                  children: (
                    <Table
                      rowKey="id"
                      size="small"
                      pagination={false}
                      dataSource={ep.narrative_spaces}
                      columns={nsActionColumns}
                    />
                  ),
                }))}
              />
            )}
          </Card>

          <Card
            title="地点身份 · scene_space"
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              跨集视觉一致性锚点；结构解析时按地点名自动回填并挂到叙事空间。
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              loading={sceneSpaces.isLoading}
              pagination={false}
              dataSource={sceneSpaces.data?.items || []}
              locale={{ emptyText: "解析结构后自动生成" }}
              columns={[
                { title: "名称", dataIndex: "name", width: 140 },
                { title: "key", dataIndex: "canonical_key", ellipsis: true },
                { title: "锚点", dataIndex: "anchor", ellipsis: true },
                {
                  title: "参考图",
                  dataIndex: "reference_image_url",
                  ellipsis: true,
                  render: (v: string | null | undefined) => v || "-",
                },
                {
                  title: "记录态",
                  dataIndex: "record_status",
                  width: 96,
                  render: recordTag,
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
                  width: 160,
                  render: (_: unknown, row: ShotPlan) => (
                    <Space size={4}>
                      <Button
                        size="small"
                        onClick={() =>
                          setRevisionTarget({
                            type: "shot_plan",
                            id: row.id,
                            label: `镜 ${row.ordinal}`,
                          })
                        }
                      >
                        历史
                      </Button>
                      {row.record_status === "confirmed" ? null : (
                        <Button
                          size="small"
                          loading={confirmShotMut.isPending}
                          onClick={() => confirmShotMut.mutate(row.id)}
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
            title="成片视频提示词 · 挂叙事空间"
            extra={
              <Space>
                <Button size="small" onClick={() => setImageOpen(true)}>
                  登记图片
                </Button>
                <Button
                  size="small"
                  loading={genVideoMut.isPending}
                  onClick={() => genVideoMut.mutate()}
                  disabled={!shots.data?.items?.length}
                >
                  批量生成
                </Button>
              </Space>
            }
            style={{ marginBottom: 16 }}
          >
            <Typography.Paragraph type="secondary">
              D1：一空间一段成片提示词，聚合该空间全部分镜；时长 ≤15s。
            </Typography.Paragraph>
            <Table
              rowKey="id"
              size="small"
              loading={videoPrompts.isLoading}
              pagination={false}
              dataSource={videoPrompts.data?.items || []}
              locale={{ emptyText: "先规划分镜，再生成成片提示词" }}
              columns={[
                {
                  title: "叙事空间",
                  dataIndex: "narrative_space_id",
                  width: 180,
                  ellipsis: true,
                  render: (id: string) => nsTitleById.get(id) || id,
                },
                { title: "版本", dataIndex: "version", width: 64 },
                { title: "提示词", dataIndex: "prompt_text", ellipsis: true },
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
                  width: 220,
                  render: (_: unknown, row: VideoPrompt) => (
                    <Space size={4}>
                      <Button
                        size="small"
                        onClick={() =>
                          setRevisionTarget({
                            type: "video_prompt",
                            id: row.id,
                            label: `v${row.version}`,
                          })
                        }
                      >
                        历史
                      </Button>
                      {row.record_status === "confirmed" ? (
                        <Button
                          size="small"
                          type="primary"
                          loading={renderVideoMut.isPending}
                          onClick={() => renderVideoMut.mutate(row.id)}
                        >
                          生视频
                        </Button>
                      ) : (
                        <Button
                          size="small"
                          loading={confirmVideoMut.isPending}
                          onClick={() => confirmVideoMut.mutate(row.id)}
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

          <Card title="成片视频任务" style={{ marginBottom: 16 }}>
            <Table
              rowKey="id"
              size="small"
              loading={videoJobs.isLoading}
              pagination={false}
              dataSource={videoJobs.data?.items || []}
              locale={{ emptyText: "确认成片提示词后点「生视频」" }}
              columns={[
                {
                  title: "叙事空间",
                  dataIndex: "narrative_space_id",
                  width: 180,
                  ellipsis: true,
                  render: (id: string) => nsTitleById.get(id) || id,
                },
                {
                  title: "状态",
                  dataIndex: "status",
                  width: 100,
                  render: (v: string) => <Tag>{v}</Tag>,
                },
                {
                  title: "成片",
                  dataIndex: "oss_uri",
                  ellipsis: true,
                  render: (v: string | null | undefined) =>
                    v ? (
                      <a href={v} target="_blank" rel="noreferrer">
                        打开
                      </a>
                    ) : (
                      "-"
                    ),
                },
                { title: "错误", dataIndex: "error", ellipsis: true },
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
                  width: 180,
                  render: (_: unknown, row: MaterialPrompt) => (
                    <Space size={4}>
                      {row.record_status === "confirmed" ? (
                        <Button
                          size="small"
                          type="primary"
                          loading={renderImageMut.isPending}
                          onClick={() => renderImageMut.mutate(row.id)}
                        >
                          生图
                        </Button>
                      ) : (
                        <Button
                          size="small"
                          loading={confirmPromptMut.isPending}
                          onClick={() => confirmPromptMut.mutate(row.id)}
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

      <Modal
        title={`编辑叙事空间 · ${editNs?.title || ""}`}
        open={Boolean(editNs)}
        onCancel={() => setEditNs(null)}
        onOk={() => editNsForm.submit()}
        confirmLoading={updateNsMut.isPending}
        destroyOnHidden
      >
        <Form
          form={editNsForm}
          layout="vertical"
          onFinish={(values) => updateNsMut.mutate(values)}
        >
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="ordinal" label="序号">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="time_place" label="时空">
            <Input />
          </Form.Item>
          <Form.Item name="summary" label="摘要">
            <Input.TextArea rows={4} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`废稿历史 · ${revisionTarget?.label || ""}`}
        open={Boolean(revisionTarget)}
        onCancel={() => setRevisionTarget(null)}
        footer={null}
        width={720}
        destroyOnHidden
      >
        <Table
          rowKey="id"
          size="small"
          loading={revisions.isLoading}
          pagination={false}
          dataSource={revisions.data?.items || []}
          locale={{ emptyText: "尚无历史快照（确认或编辑后产生）" }}
          columns={[
            { title: "版本", dataIndex: "revision_no", width: 72 },
            { title: "原因", dataIndex: "change_reason", width: 100 },
            { title: "时间", dataIndex: "created_at", width: 180 },
            {
              title: "快照摘要",
              dataIndex: "snapshot",
              ellipsis: true,
              render: (snap: RecordRevision["snapshot"]) =>
                JSON.stringify(snap).slice(0, 120),
            },
            {
              title: "操作",
              width: 100,
              render: (_: unknown, row: RecordRevision) => (
                <Button
                  size="small"
                  loading={revertMut.isPending}
                  onClick={() => revertMut.mutate(row.id)}
                >
                  反悔写回
                </Button>
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title="登记图片到目录"
        open={imageOpen}
        onCancel={() => setImageOpen(false)}
        onOk={() => imageForm.submit()}
        confirmLoading={registerImageMut.isPending}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary">
          第四段生图前可先手工登记 URL；可挂到地点身份（source_kind=scene_space）。
        </Typography.Paragraph>
        <Form
          form={imageForm}
          layout="vertical"
          onFinish={(values) => registerImageMut.mutate(values)}
        >
          <Form.Item name="url" label="图片 URL" rules={[{ required: true }]}>
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="label" label="标签">
            <Input />
          </Form.Item>
          <Form.Item name="source_kind" label="来源类型">
            <Input placeholder="scene_space / costume_change（可选）" />
          </Form.Item>
          <Form.Item name="source_id" label="来源 ID">
            <Input placeholder="对应主记录 id（可选）" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
