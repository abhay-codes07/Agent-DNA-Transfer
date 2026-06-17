/**
 * Helix TypeScript SDK.
 *
 * Talks to a local Helix daemon / MCP server so JS/TS agents can use the same portable
 * memory as everything else. Mirrors the MCP surface (docs/MCP_INTEGRATION.md).
 *
 * Pre-alpha: types are the contract; the transport lands in Phase 6 (see ROADMAP.md).
 */

export type MemoryType =
  | "identity"
  | "preference"
  | "project"
  | "decision"
  | "entity"
  | "convention"
  | "snippet"
  | "fact";

export interface Memory {
  id: string;
  type: MemoryType;
  content: string;
  scope: string; // "global" | `project:${string}`
  confidence: number; // 0..1
  source?: { agent?: string; ingestedAt?: string };
}

export interface RecallOptions {
  scope?: string;
  k?: number;
  budgetTokens?: number;
}

export class Helix {
  constructor(private readonly endpoint = "http://127.0.0.1:8787") {}

  /** Teach Helix a fact. Redaction + gate + extract run server-side. */
  async remember(_content: string, _opts?: { scope?: string }): Promise<string[]> {
    throw new Error("Phase 6: POST /remember to the local daemon");
  }

  /** Recall relevant memories for a query (hybrid vector + graph, ranked). */
  async recall(_query: string, _opts?: RecallOptions): Promise<Memory[]> {
    throw new Error("Phase 6: GET /recall from the local daemon");
  }

  /** Soft-delete a memory (recoverable via history). */
  async forget(_idOrQuery: string): Promise<string[]> {
    throw new Error("Phase 6: POST /forget to the local daemon");
  }
}
