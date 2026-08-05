/**
 * 任务队列：查看项目 job_run（含生图/生视频长任务），支持筛选与取消。
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  cancelJob,
  listProjectJobs,
  listScriptProjects,
  type JobRun,
} from "../../../api/business/scriptBiz";

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "queued", label: "排队中" },
  { value: "running", label: "运行中" },
  { value: "done", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "cancelled", label: "已取消" },
];

const KIND_OPTIONS = [
  { value: "", label: "全部类型" },
  { value: "render_material_image", label: "生图" },
  { value: "render_video", label: "生视频" },
  { value: "parse", label: "解析" },
  { value: "material_prompts", label: "物料提示词" },
  { value: "plan_shots", label: "分镜" },
  { value: "video_segments", label: "视频片段" },
  { value: "video_prompts", label: "成片提示词" },
  { value: "narrative_segment", label: "语义切分" },
];

function statusColor(status: string) {
  if (status === "done") return "success";
  if (status === "failed") return "error";
  if (status === "cancelled") return "default";
  if (status === "running") return "processing";
  return "warning";
}

export function JobsPage() {
  const queryClient = useQueryClient();
  const [projectId, setProjectId] = useState<string | undefined>();
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");

  const projects = useQuery({
    queryKey: ["script-projects"],
    queryFn: listScriptProjects,
  });

  const jobs = useQuery({
    queryKey: ["script-jobs", projectId, status, kind],
    enabled: Boolean(projectId),
    queryFn: () =>
      listProjectJobs(projectId!, {
        status: status || undefined,
        kind: kind || undefined,
        limit: 100,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      const active = items.some(
        (j) => j.status === "queued" || j.status === "running",
      );
      return active ? 4000 : false;
    },
  });

  const cancelMut = useMutation({
    mutationFn: (jobId: string) => cancelJob(jobId),
    onSuccess: () => {
      message.success("已请求取消");
      void queryClient.invalidateQueries({ queryKey: ["script-jobs"] });
    },
    onError: (e: Error) => message.error(e.message || "取消失败"),
  });

  const activeCount = useMemo(
    () =>
      (jobs.data?.items || []).filter(
        (j) => j.status === "queued" || j.status === "running",
      ).length,
    [jobs.data],
  );

  const columns: ColumnsType<JobRun> = [
    {
      title: "标签",
      dataIndex: "label",
      width: 160,
      render: (v: string, row) => v || row.kind,
    },
    {
      title: "类型",
      dataIndex: "kind",
      width: 160,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (s: string) => <Tag color={statusColor(s)}>{s}</Tag>,
    },
    {
      title: "进度",
      dataIndex: "progress",
      width: 80,
      render: (p: number) => `${p ?? 0}%`,
    },
    {
      title: "错误",
      dataIndex: "error",
      ellipsis: true,
      render: (e: string | null) => e || "-",
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      width: 180,
      render: (t: string | null) => t || "-",
    },
    {
      title: "操作",
      key: "actions",
      width: 100,
      render: (_, row) =>
        row.status === "queued" || row.status === "running" ? (
          <Button
            size="small"
            danger
            loading={cancelMut.isPending}
            onClick={() => cancelMut.mutate(row.id)}
          >
            取消
          </Button>
        ) : null,
    },
  ];

  return (
    <div>
      <Typography.Title level={3} style={{ marginBottom: 8 }}>
        任务队列
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        生图 / 生视频等长任务入队后在此查看进度；进行中任务会自动刷新。
        {projectId ? ` 当前进行中 ${activeCount} 条。` : ""}
      </Typography.Paragraph>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            style={{ width: 240 }}
            placeholder="选择项目"
            loading={projects.isLoading}
            value={projectId}
            onChange={setProjectId}
            options={(projects.data?.items || []).map((p) => ({
              value: p.id,
              label: p.name,
            }))}
            allowClear
          />
          <Select
            style={{ width: 140 }}
            value={status}
            onChange={setStatus}
            options={STATUS_OPTIONS}
          />
          <Select
            style={{ width: 160 }}
            value={kind}
            onChange={setKind}
            options={KIND_OPTIONS}
          />
          <Button
            disabled={!projectId}
            loading={jobs.isFetching}
            onClick={() => void jobs.refetch()}
          >
            刷新
          </Button>
        </Space>
      </Card>
      <Table
        rowKey="id"
        size="middle"
        loading={jobs.isLoading}
        columns={columns}
        dataSource={jobs.data?.items || []}
        pagination={{ pageSize: 20 }}
        locale={{
          emptyText: projectId ? "暂无任务" : "请先选择项目",
        }}
      />
    </div>
  );
}
