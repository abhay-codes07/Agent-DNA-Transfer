"""Helix MCP server.

Exposes the small, stable memory surface (docs/MCP_INTEGRATION.md) to any MCP-compatible
agent. Thin front-end over helix_core.Engine — no business logic here. Growing this surface
requires an ADR (ADR-003).

Pre-alpha: tool contracts are declared; handlers delegate to the engine in Phase 2.
"""

from __future__ import annotations

# The real server registers these via the `mcp` SDK in Phase 2. Declared here as the
# authoritative contract so adapters and tests can rely on the names/shapes.
TOOLS = [
    "memory.search",  # query, scope?, k?, types?, budget_tokens? -> ranked memories
    "memory.context",  # scope?, budget_tokens? -> packed context block
    "memory.write",  # content, type?, scope?, source -> created/updated ids
    "memory.note",  # text, scope? -> ack + id
    "memory.forget",  # id|query -> removed ids
    "memory.list",  # scope?, type?, limit? -> memories
    "memory.relate",  # from_id, to_id, relation -> edge id
]

RESOURCES = [
    "helix://graph",  # read-only memory graph
    "helix://strand/manifest",  # current strand metadata
]


def main() -> None:
    """Entry point: `helix-mcp serve --stdio`. Implemented in Phase 2."""
    raise SystemExit(
        "helix-mcp is pre-alpha. Phase 2 wires these tools to helix_core.Engine over MCP:\n"
        + "\n".join(f"  - {t}" for t in TOOLS)
    )


if __name__ == "__main__":
    main()
