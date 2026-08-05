/** 业务侧菜单项；框架布局拼装时引入。 */
import {
  KeyOutlined,
  OrderedListOutlined,
  PartitionOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";

export type AdminMenuItem = {
  key: string;
  icon?: ReactNode;
  label: string;
};

export const businessMenuItems: AdminMenuItem[] = [
  { key: "/script-workspace", icon: <PartitionOutlined />, label: "剧本工作台" },
  { key: "/jobs", icon: <OrderedListOutlined />, label: "任务队列" },
];

/** 需要权限的业务菜单（由 Layout 按权限拼装） */
export function businessMenuItemsFor(hasPermission: (p: string) => boolean): AdminMenuItem[] {
  const items = [...businessMenuItems];
  if (hasPermission("model:read")) {
    items.push({ key: "/models", icon: <KeyOutlined />, label: "AI Key 配置" });
  }
  return items;
}

export function resolveBusinessSelectedKey(pathname: string): string | null {
  if (pathname.startsWith("/script-workspace") || pathname.startsWith("/script-biz")) {
    return "/script-workspace";
  }
  if (pathname.startsWith("/jobs")) {
    return "/jobs";
  }
  if (pathname.startsWith("/models")) {
    return "/models";
  }
  return null;
}
