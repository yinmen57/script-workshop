/**
 * 通用模型类目管理：一类模型（可多条）的列表 + 新增/编辑。
 * 规格来自后端 ModelCatalog，不写死业务字段。
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
  type ModelTypeSpec,
  type ModelUpsertBody,
} from "../../../api/models";

const ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";

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

function providerLabel(spec: ModelTypeSpec, provider: string) {
  return spec.provider_labels?.[provider] || provider;
}

type Props = {
  categoryLabel: string;
  types: ModelTypeSpec[];
  canWrite: boolean;
};

export function ModelCategoryPanel({ categoryLabel, types, canWrite }: Props) {
  const queryClient = useQueryClient();
  const [activeType, setActiveType] = useState<ModelType>(types[0].type_id);
  const [status, setStatus] = useState<string | undefined>();
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ModelItem | null>(null);
  const [form] = Form.useForm<FormValues>();
  const watchType = Form.useWatch("model_type", form) as ModelType | undefined;
  const watchProvider = Form.useWatch("provider", form);

  const activeSpec =
    types.find((t) => t.type_id === (watchType || activeType)) || types[0];

  const queryKey = useMemo(
    () => ["models", activeType, { keyword, status, page, pageSize }],
    [activeType, keyword, status, page, pageSize],
  );

  const list = useQuery({
    queryKey,
    queryFn: () =>
      listModels({
        model_type: activeType,
        keyword: keyword || undefined,
        status,
        page,
        page_size: pageSize,
      }),
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["models"] });
  };

  const saveMut = useMutation({
    mutationFn: async (values: FormValues) => {
      const spec = types.find((t) => t.type_id === values.model_type) || activeSpec;
      const body: ModelUpsertBody = {
        name: values.name.trim(),
        provider: values.provider,
        model_type: values.model_type,
        model_name: values.model_name.trim(),
        base_url: values.base_url?.trim() || null,
        status: values.status,
        is_default: values.is_default,
        dimension: spec.requires_dimension ? values.dimension ?? null : null,
      };
      const key = values.api_key?.trim();
      if (key) body.api_key = key;
      if (editing) return updateModel(editing.id, body);
      return createModel(body);
    },
    onSuccess: () => {
      invalidate();
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
      invalidate();
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
      model_type: activeType,
      provider: activeSpec.default_provider,
      status: "enabled",
      is_default: true,
      base_url:
        activeSpec.default_provider === "volcengine_ark" ? ARK_BASE_URL : undefined,
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
      title: `删除${categoryLabel}配置`,
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
      title: "Provider",
      dataIndex: "provider",
      width: 130,
      ellipsis: true,
      render: (v: string, row: ModelItem) => {
        const spec = types.find((t) => t.type_id === row.model_type) || activeSpec;
        return providerLabel(spec, v);
      },
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
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {activeSpec.description ||
          `${categoryLabel}：同类可配置多条，运行时使用设为默认且启用的一条。`}
      </Typography.Paragraph>

      <Space style={{ marginBottom: 16 }} wrap>
        {types.length > 1 ? (
          <Select
            style={{ width: 160 }}
            value={activeType}
            onChange={(v) => {
              setActiveType(v);
              setPage(1);
            }}
            options={types.map((t) => ({ value: t.type_id, label: t.label }))}
          />
        ) : null}
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
            添加{activeSpec.label}
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
        title={editing ? `编辑${activeSpec.label}` : `添加${activeSpec.label}`}
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
              const next = types.find((t) => t.type_id === changed.model_type);
              if (!next) return;
              form.setFieldValue("provider", next.default_provider);
              if (next.default_provider === "volcengine_ark") {
                form.setFieldValue("base_url", ARK_BASE_URL);
              }
            }
            if (changed.provider === "volcengine_ark" && !editing) {
              const current = form.getFieldValue("base_url");
              if (!current) form.setFieldValue("base_url", ARK_BASE_URL);
            }
          }}
        >
          <Form.Item
            name="name"
            label="显示名称"
            rules={[{ required: true, message: "请填写名称" }]}
          >
            <Input placeholder={`例如：${activeSpec.label} 生产 / 备用`} />
          </Form.Item>
          {types.length > 1 ? (
            <Form.Item
              name="model_type"
              label="子类型"
              rules={[{ required: true, message: "请选择类型" }]}
            >
              <Select
                options={types.map((t) => ({
                  value: t.type_id,
                  label: t.label,
                }))}
                disabled={Boolean(editing)}
              />
            </Form.Item>
          ) : (
            <Form.Item name="model_type" hidden initialValue={activeType}>
              <Input />
            </Form.Item>
          )}
          <Form.Item
            name="provider"
            label="Provider"
            rules={[{ required: true, message: "请选择 Provider" }]}
          >
            {activeSpec.providers?.length ? (
              <Select
                options={activeSpec.providers.map((p) => ({
                  value: p,
                  label: providerLabel(activeSpec, p),
                }))}
              />
            ) : (
              <Input placeholder={activeSpec.default_provider} />
            )}
          </Form.Item>
          <Form.Item
            name="model_name"
            label="模型名"
            rules={[{ required: true, message: "请填写模型名" }]}
          >
            <Input placeholder={activeSpec.model_name_placeholder} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="Base URL"
            extra="必须包含协议，例如 https://ark.cn-beijing.volces.com/api/v3"
            rules={[
              { required: true, message: "请填写 Base URL" },
              {
                validator: async (_, value: string) => {
                  const v = (value || "").trim();
                  if (!v) return;
                  if (!/^https?:\/\//i.test(v)) {
                    throw new Error("必须以 http:// 或 https:// 开头");
                  }
                },
              },
            ]}
          >
            <Input
              placeholder={
                watchProvider === "shangwu"
                  ? "例如：http://115.191.32.99:8080"
                  : activeSpec.base_url_placeholder
              }
            />
          </Form.Item>
          <Form.Item
            name="api_key"
            label="API Key"
            extra={
              editing?.has_api_key
                ? "已配置密钥；留空表示不修改，填写则覆盖"
                : activeSpec.requires_api_key_on_create
                  ? "必填"
                  : "本地服务可留空"
            }
            rules={
              editing || !activeSpec.requires_api_key_on_create
                ? undefined
                : [{ required: true, message: "请填写 API Key" }]
            }
          >
            <Input.Password
              placeholder={editing ? "留空则不修改" : "粘贴 API Key"}
            />
          </Form.Item>
          {activeSpec.requires_dimension ? (
            <Form.Item
              name="dimension"
              label="向量维度"
              rules={[{ required: true, message: "必须填写维度" }]}
            >
              <InputNumber min={1} style={{ width: "100%" }} placeholder="例如：1024" />
            </Form.Item>
          ) : null}
          <Form.Item
            name="is_default"
            label="设为运行时默认"
            valuePropName="checked"
            extra={`同「${activeSpec.label}」仅一条生效；同类可存多条备用`}
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
