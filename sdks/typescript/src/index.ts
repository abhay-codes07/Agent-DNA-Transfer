/**
 * Helix TypeScript SDK.
 *
 * Talks to the local Helix daemon (the same HTTP API the dashboard uses) so JS/TS agents share
 * the user's portable memory. Start the daemon with `helix dashboard` (or `helix-mcp` for MCP).
 *
 *   import { Helix } from "@helix-memory/sdk";
 *   const mem = new Helix();
 *   await mem.remember("We use RFC-7807 for API errors", { scope: "project:billing" });
 *   const hits = await mem.recall("how do we format API errors?", { scope: "project:billing" });
 */

export type MemoryType =
  | "identity" | "preference" | "project" | "decision"
  | "entity" | "convention" | "snippet" | "episode" | "fact";

export interface Memory {
  id: string;
  type: MemoryType;
  content: string;
  scope: string;
  confidence: number;
  importance: number;
  origin?: string | null;
}

export interface Hit extends Memory {
  score: number;
  similarity: number;
  salience: number;
}

export interface RecallOptions {
  scope?: string;
  k?: number;
}

export class Helix {
  constructor(private readonly endpoint = "http://127.0.0.1:8787") {}

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(this.endpoint + path);
    if (!res.ok) throw new Error(`helix: GET ${path} -> ${res.status}`);
    return (await res.json()) as T;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(this.endpoint + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`helix: POST ${path} -> ${res.status}`);
    return (await res.json()) as T;
  }

  private qs(params: Record<string, string | number | undefined>): string {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
    const s = p.toString();
    return s ? "?" + s : "";
  }

  /** Teach Helix a durable fact. */
  async remember(content: string, opts: { scope?: string } = {}): Promise<{ op: string; id: string }[]> {
    const r = await this.post<{ results: { op: string; id: string }[] }>("/api/remember", {
      content,
      scope: opts.scope ?? "global",
    });
    return r.results;
  }

  /** Recall relevant memories (hybrid semantic + keyword + graph). */
  async recall(query: string, opts: RecallOptions = {}): Promise<Hit[]> {
    const r = await this.get<{ results: Hit[] }>("/api/search" + this.qs({ q: query, scope: opts.scope, k: opts.k }));
    return r.results;
  }

  /** A packed context block of what matters for this scope/query. */
  async context(opts: { scope?: string; query?: string } = {}): Promise<string> {
    const r = await this.get<{ context: string }>("/api/context" + this.qs({ scope: opts.scope, q: opts.query }));
    return r.context;
  }

  /** List stored memories. */
  async list(opts: { scope?: string; limit?: number } = {}): Promise<Memory[]> {
    const r = await this.get<{ memories: Memory[] }>("/api/memories" + this.qs({ scope: opts.scope, limit: opts.limit }));
    return r.memories;
  }

  /** Full detail incl. provenance ("why it believes this"). */
  async get_(id: string): Promise<Memory & { provenance: unknown[] }> {
    return this.get("/api/memory" + this.qs({ id }));
  }

  /** Edit a memory in place (re-embeds if content changes). */
  async edit(id: string, fields: { content?: string; scope?: string; type?: MemoryType; importance?: number }): Promise<Memory> {
    return this.post("/api/edit", { id, ...fields });
  }

  /** Soft-delete a memory by id or top query match. */
  async forget(idOrQuery: string): Promise<string[]> {
    const r = await this.post<{ forgot: string[] }>("/api/forget", { id: idOrQuery });
    return r.forgot;
  }

  /** Link two memories with a typed relation. */
  async relate(fromId: string, toId: string, relation = "related_to"): Promise<string> {
    const r = await this.post<{ edge: string }>("/api/relate", { from: fromId, to: toId, relation });
    return r.edge;
  }

  /** Engine diagnostics. */
  async stats(): Promise<Record<string, unknown>> {
    return this.get("/api/stats");
  }
}
