import type { CSSProperties, ReactNode } from "react";
import { canvasTokens } from "../theme/tokens";

type Props = {
  width: number;
  height: number;
  hint: string;
  accent: string;
  previewUrl?: string;
  children?: ReactNode;
};

/** 媒体区：有预览图则展示，否则空态底（选中环由 NodeCardShell 负责）。 */
export function MediaPlaceholder({
  width,
  height,
  hint,
  accent,
  previewUrl,
  children,
}: Props) {
  const box: CSSProperties = {
    width,
    height,
    borderRadius: canvasTokens.mediaRadius,
    overflow: "hidden",
    background: canvasTokens.emptyBg,
    position: "relative",
  };

  return (
    <div style={box}>
      {previewUrl ? (
        <img
          src={previewUrl}
          alt=""
          draggable={false}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "grid",
            placeItems: "center",
            color: canvasTokens.muted,
            fontSize: 12,
            padding: 12,
            textAlign: "center",
            border: `1px dashed ${accent}33`,
            boxSizing: "border-box",
          }}
        >
          {hint}
        </div>
      )}
      {children}
    </div>
  );
}
