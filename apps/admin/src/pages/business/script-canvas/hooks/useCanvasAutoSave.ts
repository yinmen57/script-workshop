/**
 * 自 sd-2-c use-auto-save 思路改写：防抖 PUT canvas_snapshot，去掉 Worker / 多端冲突锁。
 */
import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import type { Edge, Node, Viewport } from "@xyflow/react";
import { message } from "antd";
import { saveCanvas } from "../../../../api/business/scriptBiz";

type Options = {
  segmentId: string;
  enabled?: boolean;
  debounceMs?: number;
};

export function useCanvasAutoSave(
  nodes: Node[],
  edges: Edge[],
  viewportRef: MutableRefObject<Viewport>,
  options: Options,
) {
  const { segmentId, enabled = true, debounceMs = 1500 } = options;
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipFirst = useRef(true);

  const persist = useCallback(async () => {
    if (!enabled || !segmentId) return;
    setSaving(true);
    try {
      const saved = await saveCanvas(segmentId, {
        nodes,
        edges,
        viewport: viewportRef.current,
      });
      setVersion(saved.version);
      setLastSavedAt(Date.now());
    } catch (e) {
      message.error(e instanceof Error ? e.message : "画布保存失败");
    } finally {
      setSaving(false);
    }
  }, [enabled, segmentId, nodes, edges, viewportRef]);

  const flush = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    await persist();
  }, [persist]);

  useEffect(() => {
    if (!enabled) return;
    // 首次加载完成前不自动保存，避免空图覆盖
    if (skipFirst.current) {
      skipFirst.current = false;
      return;
    }
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      void persist();
    }, debounceMs);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [nodes, edges, enabled, debounceMs, persist]);

  useEffect(() => {
    skipFirst.current = true;
  }, [segmentId]);

  return { saving, lastSavedAt, version, flush };
}
