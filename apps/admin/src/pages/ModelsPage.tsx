/**
 * AI Key 配置：对接 /models。
 * Chat / Embedding / Rerank / 生图 / 生视频密钥加密落库，页面不回显明文。
 */
import { useMemo, useState } from "react";
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  createModel,
  deleteModel,
  listModels,
  testModel,
  updateModel,
  type ModelItem,
  type ModelType,
  type ModelUpsertBody,
} from "../api/models";
import { useAuthStore } from "../stores/auth";

type FormValues = {
  name: string;
  provider: string;
  model_type: ModelType;
  model_name: string;
  base_url?: string;
  api_key?: string;
  dimension?: number | null;
  status: string;
  is_default: boolean;
};

function apiErrorMessage(e: unknown, fallback: string) {
  if (axios.isAxiosError(e)) {
    const msg = e.response?.data?.message;
    if (typeof msg === "string" && msg) return msg;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

const MODEL_TYPE_LABEL: Record<ModelType, string> = {
  chat: "Chat",
  embedding: "Embedding",
  rerank: "Rerank",
  image: "生图",
  video: "生视频",
};

const MODEL_TYPE_OPTIONS = [
  { value: "chat", label: "Chat（对话）" },
  { value: "embedding", label: "Embedding（向量）" },
  { value: "rerank", label: "Rerank（精排）" },
  { value: "image", label: "生图" },
  { value: "video", label: "生视频" },
];

const DEFAULT_PROVIDER: Record<ModelType, string> = {
  chat: "openai_compatible",
  embedding: "openai_compatible",
  rerank: "xinference",
  image: "shangwu",
  video: "shangwu",
};

const MEDIA_PROVIDER_OPTIONS = [
  { value: "shangwu", label: "赏舞" },
  { value: "volcengine_ark", label: "火山方舟" },
];

const ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";

const isMediaType = (t?: ModelType) => t === "image" || t === "video";

export function ModelsPage() {
  const queryClient = useQueryClient();
  const canWrite = useAuthStore((s) => s.hasPermission("model:write"));

  const [keyword, setKeyword] = useState("");
  const [modelType, setModelType] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModelItem | null>(null);
  const [form] = Form.useForm<FormValues>();
  const watchType = Form.useWatch("model_type", form);
  const watchProvider = Form.useWatch("provider", form);

  const queryKey = useMemo(
    () => ["models", { keyword, modelType, status, page, pageSize }],
    [keyword, modelType, status, page, pageSize],
  );

  const list = useQuery({
    queryKey,
    queryFn: () =>
      listModels({
        keyword: keyword || undefined,
        model_type: modelType,
        status,
        page,
        page_size: pageSize,
      }),
  });

  const saveMut = useMutation({
    mutationFn: async (values: FormValues) => {
      const body: ModelUpsertBody = {
        name: values.name.trim(),
        provider: values.provider,
        model_type: values.model_type,
        model_name: values.model_name.trim(),
        base_url: values.base_url?.trim() || null,
        status: values.status,
        is_default: values.is_default,
        dimension:
          values.model_type === "embedding" ? values.dimension ?? null : null,
      };
      const key = values.api_key?.trim();
      if (key) body.api_key = key;

      if (editing) {
        return updateModel(editing.id, body);
      }
      return createModel(body);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      setModalOpen(false);
      setEditing(null);
      form.resetFields();
      message.success(editing ? "已更新" : "已添加");
    },
    onError: (e) => message.error(apiErrorMessage(e, "保存失败")),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteModel(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["models"] });
      message.success("已删除");
    },
    onError: (e) => message.error(apiErrorMessage(e, "删除失败")),
  });

  const testMut = useMutation({
    mutationFn: (id: string) => testModel(id),
    onSuccess: (result) => {
      if (result.ok) {
        message.success(`连通正常（${result.latency_ms} ms）`);
      } else {
        const err = result.detail?.error;
        message.error(
          typeof err === "string" ? err : `连通失败（${result.latency_ms} ms）`,
        );
      }
    },
    onError: (e) => message.error(apiErrorMessage(e, "测试失败")),
  });

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      provider: "openai_compatible",
      model_type: "chat",
      status: "enabled",
      is_default: true,
    });
    setModalOpen(true);
  };

  const openEdit = (row: ModelItem) => {
    setEditing(row);
    form.setFieldsValue({
      name: row.name,
      provider: row.provider,
      model_type: row.model_type,
      model_name: row.model_name,
      base_url: row.base_url || undefined,
      api_key: undefined,
      dimension: row.dimension,
      status: row.status,
      is_default: row.is_default,
    });
    setModalOpen(true);
  };

  const askDelete = (row: ModelItem) => {
    Modal.confirm({
      title: "删除模型配置",
      content: `确定删除「${row.name}」吗？密钥将一并清除。`,
      okText: "删除",
      okType: "danger",
      cancelText: "取消",
      onOk: () => deleteMut.mutateAsync(row.id),
    });
  };

  const columns = [
    { title: "名称", dataIndex: "name", ellipsis: true },
    {
      title: "类型",
      dataIndex: "model_type",
      width: 90,
      render: (v: ModelType) => MODEL_TYPE_LABEL[v] || v,
    },
    {
      title: "Provider",
      dataIndex: "provider",
      width: 130,
      ellipsis: true,
      render: (v: string) =>
        v === "volcengine_ark" ? "火山方舟" : v === "shangwu" ? "赏舞" : v,
    },
    { title: "模型名", dataIndex: "model_name", ellipsis: true },
    {
      title: "Base URL",
      dataIndex: "base_url",
      ellipsis: true,
      render: (v: string | null) => v || "-",
    },
    {
      title: "API Key",
      dataIndex: "has_api_key",
      width: 100,
      render: (v: boolean) => (
        <Tag color={v ? "green" : "default"}>{v ? "已配置" : "未配置"}</Tag>
      ),
    },
    {
      title: "默认",
      dataIndex: "is_default",
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="gold">运行时</Tag> : <Tag>否</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 90,
      render: (v: string) => (
        <Tag color={v === "enabled" ? "blue" : "default"}>
          {v === "enabled" ? "启用" : "停用"}
        </Tag>
      ),
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 180,
      render: (v: string | null) => v || "-",
    },
    {
      title: "操作",
      width: 220,
      render: (_: unknown, row: ModelItem) => (
        <Space>
          <Button
            size="small"
            loading={testMut.isPending && testMut.variables === row.id}
            onClick={() => testMut.mutate(row.id)}
          >
            测试
          </Button>
          {canWrite ? (
            <>
              <Button size="small" onClick={() => openEdit(row)}>
                编辑
              </Button>
              <Button size="small" danger onClick={() => askDelete(row)}>
                删除
              </Button>
            </>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={3}>AI Key 配置</Typography.Title>
      <Typography.Paragraph type="secondary">
        Chat / Embedding / Rerank / 生图 / 生视频各自独立配置。生图与生视频可选赏舞或火山方舟。密钥加密落库，运行时只读同类型「默认」且启用的一条；密钥不回显明文。
      </Typography.Paragraph>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          allowClear
          placeholder="按名称搜索"
          style={{ width: 220 }}
          onSearch={(v) => {
            setKeyword(v.trim());
            setPage(1);
          }}
        />
        <Select
          allowClear
          placeholder="类型"
          style={{ width: 180 }}
          value={modelType}
          onChange={(v) => {
            setModelType(v);
            setPage(1);
          }}
          options={MODEL_TYPE_OPTIONS}
        />
        <Select
          allowClear
          placeholder="状态"
          style={{ width: 120 }}
          value={status}
          onChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
          options={[
            { value: "enabled", label: "启用" },
            { value: "disabled", label: "停用" },
          ]}
        />
        {canWrite ? (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            添加配置
          </Button>
        ) : null}
      </Space>

      <Table
        rowKey="id"
        loading={list.isLoading}
        columns={columns}
        dataSource={list.data?.items || []}
        pagination={{
          current: page,
          pageSize,
          total: list.data?.total || 0,
          showSizeChanger: true,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
      />

      <Modal
        title={editing ? "编辑 AI Key" : "添加 AI Key"}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditing(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        confirmLoading={saveMut.isPending}
        destroyOnClose
        width={560}
        okText="保存"
        cancelText="取消"
      >
        <Form<FormValues>
          form={form}
          layout="vertical"
          onFinish={(values) => saveMut.mutate(values)}
          onValuesChange={(changed) => {
            if (changed.model_type && !editing) {
              const nextType = changed.model_type as ModelType;
              const nextProvider = DEFAULT_PROVIDER[nextType];
              form.setFieldValue("provider", nextProvider);
              if (nextProvider === "volcengine_ark") {
                form.setFieldValue("base_url", ARK_BASE_URL);
              }
            }
            if (changed.provider === "volcengine_ark" && !editing) {
              const current = form.getFieldValue("base_url");
              if (!current) {
                form.setFieldValue("base_url", ARK_BASE_URL);
              }
            }
          }}
        >
          <Form.Item
            name="name"
            label="显示名称"
            rules={[{ required: true, message: "请填写名称" }]}
          >
            <Input placeholder="例如：火山方舟 DeepSeek / 赏舞" />
          </Form.Item>
          <Form.Item
            name="model_type"
            label="类型"
            rules={[{ required: true, message: "请选择类型" }]}
          >
            <Select options={MODEL_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="provider"
            label="Provider"
            rules={[{ required: true, message: "请选择 Provider" }]}
          >
            {isMediaType(watchType) ? (
              <Select options={MEDIA_PROVIDER_OPTIONS} />
            ) : (
              <Input placeholder="openai_compatible / xinference" />
            )}
          </Form.Item>
          <Form.Item
            name="model_name"
            label="模型名"
            rules={[{ required: true, message: "请填写模型名" }]}
          >
            <Input
              placeholder={
                watchType === "image"
                  ? watchProvider === "volcengine_ark"
                    ? "例如：doubao-seedream-5-0-260128"
                    : "赏舞 image_model 名称"
                  : watchType === "video"
                    ? watchProvider === "volcengine_ark"
                      ? "例如：doubao-seedance-2-0-260128"
                      : "赏舞视频模型名"
                    : "例如：deepseek-v4-flash-260425 或 bge-m3"
              }
            />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            rules={[{ required: true, message: "请填写 Base URL" }]}
          >
            <Input
              placeholder={
                isMediaType(watchType) && watchProvider === "shangwu"
                  ? "例如：http://115.191.32.99:8080"
                  : "例如：https://ark.cn-beijing.volces.com/api/v3"
              }
            />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={
              editing?.has_api_key
                ? "已配置密钥；留空表示不修改，填写则覆盖"
                : watchType === "embedding" || watchType === "rerank"
                  ? "本地 Xinference 可留空"
                  : "必填"
            }
            rules={
              editing || watchType === "embedding" || watchType === "rerank"
                ? undefined
                : [{ required: true, message: "请填写 API Key" }]
            }
          >
            <Input.Password placeholder={editing ? "留空则不修改" : "粘贴 API Key"} />
          </Form.Item>
          {watchType === "embedding" ? (
            <Form.Item
              name="dimension"
              label="向量维度"
              rules={[{ required: true, message: "Embedding 必须填写维度" }]}
            >
              <InputNumber min={1} style={{ width: "100%" }} placeholder="例如：1024" />
            </Form.Item>
          ) : null}
          <Form.Item
            name="is_default"
            label="设为运行时默认"
            valuePropName="checked"
            extra="同类型仅一条生效；Agent / 剧本作业 / 检索会读默认配置"
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="status"
            label="状态"
            rules={[{ required: true, message: "请选择状态" }]}
          >
            <Select
              options={[
                { value: "enabled", label: "启用" },
                { value: "disabled", label: "停用" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
