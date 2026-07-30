/**
 * 自 sd-2-c use-auto-save 思路改写：防抖 PUT canvas_snapshot，去掉 Worker / 多端冲突锁。
 */
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import type { Edge, Node, Viewport } from "@xyflow/react";
import { saveCanvas } from "../../../api/scriptBiz";

type Options = {
  spaceId: string;
  enabled?: boolean;
  debounceMs?: number;
};

function stripRuntime(nodes: Node[]): Node[] {
  return nodes.map((n) => {
    const data = { ...(n.data as Record<string, unknown>) };
    delete data.onAction;
    return { ...n, data };
  });
}

export function useCanvasAutoSave(
  nodes: Node[],
  edges: Edge[],
  viewportRef: MutableRefObject<Viewport>,
  options: Options,
) {
  const { spaceId, enabled = true, debounceMs = 1500 } = options;
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [version, setVersion] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  nodesRef.current = nodes;
  edgesRef.current = edges;

  const flush = useCallback(async () => {
    if (!enabled || !spaceId) return;
    setSaving(true);
    try {
      const saved = await saveCanvas(spaceId, {
        nodes: stripRuntime(nodesRef.current),
        edges: edgesRef.current,
        viewport: viewportRef.current,
      });
      setVersion(saved.version);
      setLastSavedAt(new Date());
    } finally {
      setSaving(false);
    }
  }, [enabled, spaceId, viewportRef]);

  useEffect(() => {
    if (!enabled) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      void flush().catch(() => undefined);
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [nodes, edges, enabled, debounceMs, flush]);

  return { saving, lastSavedAt, version, flush };
}
