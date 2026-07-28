import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { loginApi, meApi } from "../api/client";
import { useAuthStore } from "../stores/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setProfile = useAuthStore((s) => s.setProfile);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onFinish = async (values: { account: string }) => {
    setLoading(true);
    setError(null);
    try {
      // 本地 APP_ENV=dev 后端不校验密码
      const tokens = await loginApi(values.account, "");
      setTokens(tokens.access_token, tokens.refresh_token);
      const me = await meApi();
      setProfile({
        userId: me.user_id,
        displayName: me.display_name,
        tenantId: me.tenant_id,
        permissions: me.permissions,
      });
      navigate("/apps");
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { message?: string } } })?.response?.data?.message ||
        "登录失败";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "linear-gradient(160deg, #f5f7fa 0%, #e8eef5 100%)",
      }}
    >
      <Card style={{ width: 380 }}>
        <Typography.Title level={3}>AI Platform</Typography.Title>
        <Typography.Paragraph type="secondary">本地开发登录（无需密码）</Typography.Paragraph>
        {error ? <Alert type="error" message={error} style={{ marginBottom: 16 }} /> : null}
        <Form layout="vertical" onFinish={onFinish} initialValues={{ account: "admin" }}>
          <Form.Item name="account" label="账号" rules={[{ required: true }]}>
            <Input autoComplete="username" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
