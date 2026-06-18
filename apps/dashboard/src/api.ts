// Typed client for the Helix daemon API (the same endpoints the stdlib dashboard uses).

export type Memory = {
  id: string;
  type: string;
  content: string;
  scope: string;
  confidence: number;
  importance: number;
  origin?: string | null;
};

export type Hit = Memory & { score: number };

export type MemoryDetail = Memory & {
  provenance: { agent?: string; extractor?: string; origin?: string }[];
  created_at?: string;
};

export type HistoryEntry = { seq: number; ts: string; op: string; memory_id: string };

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  list: (scope?: string) =>
    getJSON<{ memories: Memory[] }>("/api/memories" + (scope ? `?scope=${encodeURIComponent(scope)}` : "")),
  search: (q: string, scope?: string) =>
    getJSON<{ results: Hit[] }>(
      `/api/search?q=${encodeURIComponent(q)}` + (scope ? `&scope=${encodeURIComponent(scope)}` : ""),
    ),
  remember: (content: string, scope: string) =>
    postJSON<{ results: { op: string; id: string }[] }>("/api/remember", { content, scope }),
  forget: (id: string) => postJSON<{ forgot: string[] }>("/api/forget", { id }),
  edit: (id: string, content: string, scope?: string) =>
    postJSON<MemoryDetail>("/api/edit", { id, content, scope }),
  detail: (id: string) => getJSON<MemoryDetail>(`/api/memory?id=${encodeURIComponent(id)}`),
  history: () => getJSON<{ history: HistoryEntry[] }>("/api/history?limit=80"),
  stats: () => getJSON<Record<string, unknown>>("/api/stats"),
};
