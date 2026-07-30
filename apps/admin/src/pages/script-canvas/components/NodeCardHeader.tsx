import type { ReactNode } from "react";
import { canvasTokens } from "../theme/tokens";

type Props = {
  kindLabel: string;
  title: string;
  accent: string;
  icon: ReactNode;
  badges?: ReactNode;
};

/** 节点标题行：图标徽标 + 类型名 + 标题 + 右侧状态。 */
export function NodeCardHeader({
  kindLabel,
  title,
  accent,
  icon,
  badges,
}: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "12px 14px 8px",
      }}
    >
      <span
        style={{
          width: 20,
          height: 20,
          borderRadius: "50%",
          background: canvasTokens.headerIconBg,
          color: accent || canvasTokens.headerIcon,
          display: "grid",
          placeItems: "center",
          fontSize: 11,
          flexShrink: 0,
        }}
      >
        {icon}
      </span>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            fontSize: 10,
            color: canvasTokens.muted,
            letterSpacing: 0.4,
            lineHeight: 1.2,
          }}
        >
          {kindLabel}
        </div>
        <div
          style={{
            fontSize: 12,
            fontWeight: 600,
            color: canvasTokens.title,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={title}
        >
          {title}
        </div>
      </div>
      {badges ? (
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>{badges}</div>
      ) : null}
    </div>
  );
}
