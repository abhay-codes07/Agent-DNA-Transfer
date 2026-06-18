# Examples

Runnable recipes showing how Helix is used. From a clone with the packages on the path
(`uv sync`, or `pip install pynacl mcp typer rich`), run any of them:

```bash
uv run python examples/quickstart.py    # remember + recall locally ($0, offline)
uv run python examples/transfer.py      # export a .dna, import it "on another machine", recall
uv run python examples/team_sync.py     # encrypted push/pull + merge between two teammates
uv run python examples/eval.py          # the built-in recall-quality benchmark
```

| Recipe | Shows |
|---|---|
| [`quickstart.py`](quickstart.py) | Remember + recall via the Python SDK (local, free, offline) |
| [`transfer.py`](transfer.py) | The portable `.dna`: export → verify → import → recall elsewhere |
| [`team_sync.py`](team_sync.py) | Encrypted team sync: push, then pull + merge (backend sees only ciphertext) |
| [`eval.py`](eval.py) | Recall precision/recall@k, MRR, and latency on the built-in coding benchmark |

Wire Helix into your agents with `helix connect <agent>` (see
[`docs/MCP_INTEGRATION.md`](../docs/MCP_INTEGRATION.md)). Status: [`ROADMAP.md`](../ROADMAP.md).
