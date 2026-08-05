/**
 * 调试台命名测试夹具：按应用 slug 存 localStorage。
 */
import type { ChatSelection } from "../../api/chat";

export type PlaygroundFixture = {
  id: string;
  name: string;
  agent_id?: string | null;
  sample_message?: string;
  selection: ChatSelection;
  updated_at: string;
};

function storageKey(slug: string) {
  return `playground:fixtures:${slug}`;
}

function newId(): string {
  return `fx_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function listFixtures(slug: string): PlaygroundFixture[] {
  if (!slug) return [];
  try {
    const raw = localStorage.getItem(storageKey(slug));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (x): x is PlaygroundFixture =>
        Boolean(x && typeof x === "object" && typeof x.id === "string" && typeof x.name === "string"),
    );
  } catch {
    return [];
  }
}

function writeAll(slug: string, items: PlaygroundFixture[]) {
  localStorage.setItem(storageKey(slug), JSON.stringify(items));
}

export function upsertFixture(
  slug: string,
  input: {
    id?: string;
    name: string;
    agent_id?: string | null;
    sample_message?: string;
    selection: ChatSelection;
  },
): PlaygroundFixture {
  const items = listFixtures(slug);
  const now = new Date().toISOString();
  const existingIdx = input.id
    ? items.findIndex((x) => x.id === input.id)
    : -1;
  const fixture: PlaygroundFixture = {
    id: input.id && existingIdx >= 0 ? input.id : newId(),
    name: input.name.trim(),
    agent_id: input.agent_id ?? null,
    sample_message: (input.sample_message || "").trim() || undefined,
    selection: input.selection,
    updated_at: now,
  };
  if (existingIdx >= 0) {
    items[existingIdx] = fixture;
  } else {
    items.unshift(fixture);
  }
  writeAll(slug, items);
  return fixture;
}

export function removeFixture(slug: string, id: string): void {
  writeAll(
    slug,
    listFixtures(slug).filter((x) => x.id !== id),
  );
}

export function getFixture(slug: string, id: string): PlaygroundFixture | null {
  return listFixtures(slug).find((x) => x.id === id) || null;
}
