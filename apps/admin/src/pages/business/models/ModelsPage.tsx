/**
 * 业务 AI Key：按模型类目分栏（语言 / 声音 / 生图 / 生视频 / 检索）。
 * 目录来自框架 GET /models/catalog，列表用通用 ModelCategoryPanel。
 */
import { Spin, Tabs, Typography } from "antd";
import { useQuery } from "@tanstack/react-query";
import { fetchModelCatalog } from "../../../api/models";
import { useAuthStore } from "../../../stores/auth";
import { ModelCategoryPanel } from "./ModelCategoryPanel";

export function ModelsPage() {
  const canWrite = useAuthStore((s) => s.hasPermission("model:write"));
  const catalog = useQuery({
    queryKey: ["models-catalog"],
    queryFn: fetchModelCatalog,
  });

  if (catalog.isLoading) {
    return <Spin />;
  }

  if (catalog.isError || !catalog.data) {
    return (
      <Typography.Text type="danger">
        加载模型类目失败，请确认框架 API 已启动。
      </Typography.Text>
    );
  }

  return (
    <div>
      <Typography.Title level={3}>AI Key 配置</Typography.Title>
      <Typography.Paragraph type="secondary">
        按业务模型分类管理：语言模型、声音、生图、生视频、检索。每一类可配置多条，运行时取该类型下「默认且启用」的一条；密钥加密落库，不回显明文。
      </Typography.Paragraph>
      <Tabs
        items={catalog.data.categories.map((cat) => ({
          key: cat.category_id,
          label: cat.label,
          children: (
            <ModelCategoryPanel
              categoryLabel={cat.label}
              types={cat.types}
              canWrite={canWrite}
            />
          ),
        }))}
      />
    </div>
  );
}
