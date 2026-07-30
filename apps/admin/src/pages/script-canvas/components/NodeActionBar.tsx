import { canvasTokens } from "../theme/tokens";
import type { NodeAction, NarrativeNodeData } from "../nodes/types";

type Props = {
  actions: NodeAction[];
  data: NarrativeNodeData;
  running?: boolean;
};

/** 节点底部动作：次要灰底 / 主按钮 brand 渐变。 */
export function NodeActionBar({ actions, data, running }: Props) {
  if (!actions.length) return null;
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 6,
        padding: "0 12px 12px",
      }}
    >
      {actions.map((a) => {
        const primary = Boolean(a.primary);
        return (
          <button
            key={a.key}
            type="button"
            disabled={running}
            className="nodrag nopan"
            onClick={() => data.onAction?.(a.key, data)}
            style={{
              border: primary ? "none" : `1px solid ${canvasTokens.panelBorder}`,
              borderRadius: 8,
              padding: "4px 10px",
              fontSize: 11,
              cursor: running ? "not-allowed" : "pointer",
              opacity: running ? 0.55 : 1,
              color: primary ? "#fff" : canvasTokens.label,
              background: primary
                ? `linear-gradient(135deg, ${canvasTokens.brand}, ${canvasTokens.brandHover})`
                : "#fff",
            }}
          >
            {a.label}
          </button>
        );
      })}
    </div>
  );
}
