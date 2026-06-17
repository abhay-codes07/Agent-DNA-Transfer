# helix-sdk-python

Programmatic access to Helix memory for custom agents and scripts.

```python
from helix_sdk import Helix

mem = Helix()                       # local strand; $0, offline by default
mem.remember("We use RFC-7807 for API errors", scope="project:billing-svc")
hits = mem.recall("how do we format API errors?", scope="project:billing-svc")
```

Mirrors the MCP surface ([`docs/MCP_INTEGRATION.md`](../../docs/MCP_INTEGRATION.md)). Thin
wrapper over [`helix-core`](../helix-core).
