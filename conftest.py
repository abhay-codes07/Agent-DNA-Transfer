"""Pytest bootstrap: make the workspace packages importable without an install.

Lets `pytest` run the $0/offline core on a bare Python (no `uv sync` needed) by putting each
package's `src/` on sys.path. Production installs use the uv workspace instead.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).parent
_SRC = [
    "packages/helix-core/src",
    "packages/helix-cli/src",
    "packages/helix-mcp/src",
    "packages/helix-sdk-python/src",
]
for rel in _SRC:
    p = str((_ROOT / rel).resolve())
    if p not in sys.path:
        sys.path.insert(0, p)
