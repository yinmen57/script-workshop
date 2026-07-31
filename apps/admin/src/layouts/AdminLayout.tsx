import {
  AppstoreOutlined,
  LogoutOutlined,
  PartitionOutlined,
} from "@ant-design/icons";
import { Layout, Menu, Typography, Button, Space } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: "/apps", icon: <AppstoreOutlined />, label: "应用空间" },
  { key: "/script-workspace", icon: <PartitionOutlined />, label: "剧本工作台" },
];

export function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const displayName = useAuthStore((s) => s.displayName);
  const tenantId = useAuthStore((s) => s.tenantId);
  const logout = useAuthStore((s) => s.logout);

  const selectedKey = location.pathname.startsWith("/apps")
    ? "/apps"
    : location.pathname.startsWith("/script-workspace")
      ? "/script-workspace"
      : location.pathname;

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={220}>
        <div style={{ padding: 16 }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            AI Platform
          </Typography.Title>
          <Typography.Text type="secondary">Agent 开发框架</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            paddingInline: 24,
          }}
        >
          <Space>
            <Typography.Text>
              {displayName} / {tenantId}
            </Typography.Text>
            <Button
              icon={<LogoutOutlined />}
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              退出
            </Button>
          </Space>
        </Header>
        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
