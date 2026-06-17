# helix-mcp

The Helix MCP server — the universal interface that lets *any* MCP-compatible agent (Claude
Code, Cursor, Copilot, Windsurf, ChatGPT desktop) read and write the same local memory.

Run it: `helix-mcp serve --stdio`. Tools/resources are documented in
[`docs/MCP_INTEGRATION.md`](../../docs/MCP_INTEGRATION.md). The surface is intentionally small
and versioned; growing it requires an ADR ([ADR-003](../../DECISIONS.md)). Thin front-end over
[`helix-core`](../helix-core).
