/**
 * 画布视觉令牌（理解自赏舞画布亮色壳，按本项目重写）。
 * 人物/道具偏 brand，成片偏 violet，分镜偏 rose。
 */
export const canvasTokens = {
  brand: "#6962FF",
  brandHover: "#7C75F0",
  connection: "#2F80ED",
  connectionStrong: "#0F6FDF",
  paneBg: "#FCFCFC",
  dots: "#DADDE2",
  cardRadius: 12,
  mediaRadius: 8,
  headerIconBg: "#F1F1F1",
  headerIcon: "#303030",
  label: "#5C6370",
  title: "#2B2F36",
  muted: "#8A9099",
  emptyBg: "#F0F2F5",
  panelBorder: "#E6E8EC",
  panelShadow: "0 8px 24px rgba(15, 23, 42, 0.10)",
  selectedRing: "0 0 0 2px rgba(148, 163, 184, 0.58), 0 8px 22px rgba(15, 23, 42, 0.10)",
  accent: {
    character: "#6962FF",
    prop: "#10B981",
    shot: "#F43F5E",
    video_out: "#8B5CF6",
  } as const,
  media: {
    character: { width: 200, height: 260 },
    prop: { width: 200, height: 200 },
    shot: { width: 280, height: 120 },
    video_out: { width: 280, height: 158 },
  } as const,
} as const;

export type NodeAccentKind = keyof typeof canvasTokens.accent;
