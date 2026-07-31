/**
 * 工作台顶栏：项目选择、命名新建、删除、上传剧本。
 */
import { Button, Form, Input, Modal, Select, Space, Upload, message } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createScriptProject,
  deleteScriptProject,
  listScriptProjects,
  uploadScriptFile,
} from "../../api/scriptBiz";
import type { WorkspaceMode } from "./types";

type Props = {
  projectId: string | null;
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  onProjectChange: (projectId: string | null) => void;
};

export function ProjectBar({
  projectId,
  mode,
  onModeChange,
  onProjectChange,
}: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [form] = Form.useForm<{ name: string }>();

  const projects = useQuery({
    queryKey: ["script-biz-projects"],
    queryFn: listScriptProjects,
  });

  const currentName = useMemo(
    () => (projects.data?.items || []).find((p) => p.id === projectId)?.name || "",
    [projectId, projects.data?.items],
  );

  const createMut = useMutation({
    mutationFn: (name: string) => createScriptProject({ name }),
    onSuccess: (p) => {
      void queryClient.invalidateQueries({ queryKey: ["script-biz-projects"] });
      onProjectChange(p.id);
      setCreateOpen(false);
      form.resetFields();
      message.success("已创建项目");
    },
    onError: (e) =>
      message.error(e instanceof Error ? e.message : "创建失败"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteScriptProject(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["script-biz-projects"] });
      void queryClient.invalidateQueries({ queryKey: ["script-workspace"] });
      onProjectChange(null);
      message.success("项目已删除");
    },
    onError: (e) =>
      message.error(e instanceof Error ? e.message : "删除失败"),
  });

  const uploadMut = useMutation({
    mutationFn: (file: File) => uploadScriptFile(projectId!, file),
    onSuccess: () => {
      message.success("剧本已上传");
      void queryClient.invalidateQueries({ queryKey: ["script-workspace"] });
    },
    onError: (e) =>
      message.error(e instanceof Error ? e.message : "上传失败"),
  });

  const submitCreate = async () => {
    const values = await form.validateFields();
    createMut.mutate(values.name.trim());
  };

  /** 二次确认后删除当前项目 */
  const askDelete = () => {
    if (!projectId) {
      message.warning("请先选择项目");
      return;
    }
    const name = currentName || projectId;
    Modal.confirm({
      title: "删除项目",
      content: `确定删除项目「${name}」吗？项目下的剧本、资产、分镜与视频数据都会被清除。`,
      okText: "继续",
      okType: "danger",
      cancelText: "取消",
      onOk: () =>
        new Promise<void>((resolve, reject) => {
          Modal.confirm({
            title: "再次确认",
            content: "此操作不可恢复。请再次确认删除该项目。",
            okText: "确认删除",
            okType: "danger",
            cancelText: "取消",
            onOk: async () => {
              try {
                await deleteMut.mutateAsync(projectId);
                resolve();
              } catch (e) {
                reject(e);
              }
            },
            onCancel: () => reject(),
          });
        }).catch(() => undefined),
    });
  };

  return (
    <div className="script-workspace__top">
      <Space wrap>
        <span className="script-workspace__brand">剧本工作台</span>
        <Select
          style={{ minWidth: 220 }}
          placeholder="选择项目"
          value={projectId}
          allowClear
          options={(projects.data?.items || []).map((p) => ({
            value: p.id,
            label: p.name,
          }))}
          onChange={(v) => onProjectChange(v || null)}
          loading={projects.isLoading}
        />
        <Space.Compact size="small">
          <Button
            type={mode === "workspace" ? "primary" : "default"}
            onClick={() => onModeChange("workspace")}
          >
            工作台
          </Button>
          <Button
            type={mode === "knowledge" ? "primary" : "default"}
            onClick={() => onModeChange("knowledge")}
          >
            知识库
          </Button>
        </Space.Compact>
        <Button
          size="small"
          onClick={() => {
            form.setFieldsValue({ name: "" });
            setCreateOpen(true);
          }}
        >
          新建项目
        </Button>
        <Button
          size="small"
          danger
          disabled={!projectId}
          loading={deleteMut.isPending}
          onClick={askDelete}
        >
          删除项目
        </Button>
        <Upload
          accept=".docx,.txt,.md,.fdx"
          showUploadList={false}
          disabled={!projectId || uploadMut.isPending}
          beforeUpload={(file) => {
            if (!projectId) {
              message.warning("请先选择项目");
              return Upload.LIST_IGNORE;
            }
            uploadMut.mutate(file);
            return false;
          }}
        >
          <Button
            size="small"
            icon={<InboxOutlined />}
            disabled={!projectId}
            loading={uploadMut.isPending}
          >
            上传剧本
          </Button>
        </Upload>
      </Space>
      <Button size="small" type="link" onClick={() => navigate("/apps")}>
        返回平台
      </Button>

      <Modal
        title="新建项目"
        open={createOpen}
        okText="创建"
        cancelText="取消"
        confirmLoading={createMut.isPending}
        onOk={() => void submitCreate()}
        onCancel={() => {
          setCreateOpen(false);
          form.resetFields();
        }}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={() => void submitCreate()}>
          <Form.Item
            name="name"
            label="项目名称"
            rules={[
              { required: true, message: "请输入项目名称" },
              { whitespace: true, message: "请输入项目名称" },
              { max: 64, message: "名称不超过 64 字" },
            ]}
          >
            <Input
              placeholder="例如：最危险的秘密"
              maxLength={64}
              autoFocus
              onPressEnter={() => void submitCreate()}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
