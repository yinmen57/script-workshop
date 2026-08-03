import { canvasTokens } from "../theme/tokens";

function Chip({
  text,
  bg,
  color,
}: {
  text: string;
  bg: string;
  color: string;
}) {
  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 500,
        padding: "2px 6px",
        borderRadius: 6,
        background: bg,
        color,
        lineHeight: 1.4,
      }}
    >
      {text}
    </span>
  );
}

type Props = {
  recordStatus?: string;
  status?: string;
};

export function StatusBadges({ recordStatus, status }: Props) {
  return (
    <>
      {recordStatus === "confirmed" ? (
        <Chip text="已确认" bg="#ECFDF5" color="#059669" />
      ) : (
        <Chip text="AI" bg="#F7F8FA" color={canvasTokens.muted} />
      )}
      {status === "running" ? (
        <Chip text="执行中" bg="#EFF6FF" color="#2563EB" />
      ) : null}
      {status === "done" ? (
        <Chip text="完成" bg="#ECFDF5" color="#059669" />
      ) : null}
      {status === "failed" ? (
        <Chip text="失败" bg="#FEF2F2" color="#DC2626" />
      ) : null}
    </>
  );
}
