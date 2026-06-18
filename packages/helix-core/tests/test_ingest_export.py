"""Tests for `ingest` (seed memory from notes) and Markdown export. Offline."""

from __future__ import annotations

from helix_core.config import Config
from helix_core.engine import Engine

NOTES = """# Project notes

## Architecture

- We use Postgres for the billing service.
- All API errors use RFC-7807.

ok thanks

```
this line is inside a code fence and should be ignored
```

The team deploys on Fridays only.
"""


def _engine(home) -> Engine:
    return Engine(Config(home=home))


def test_ingest_seeds_memory_and_skips_noise(tmp_path):
    eng = _engine(tmp_path)
    res = eng.ingest(NOTES, scope="project:billing")
    assert res["slices"] == 3  # 3 substantive lines; headers / short / fenced are dropped

    contents = " ".join(m.content.lower() for m in eng.list_memories())
    assert "postgres" in contents
    assert "rfc-7807" in contents
    assert "fridays" in contents
    assert "code fence" not in contents  # fenced code is not remembered
    eng.close()


def test_ingest_file(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text(NOTES, encoding="utf-8")
    eng = _engine(tmp_path)
    res = eng.ingest_file(str(f), scope="global")
    assert res["slices"] == 3
    eng.close()


def test_export_markdown_is_readable(tmp_path):
    eng = _engine(tmp_path)
    eng.remember("We use Postgres for billing.", scope="project:billing")
    eng.remember("I prefer pytest.", scope="global")
    out = tmp_path / "mem.md"
    n = eng.export_markdown(str(out))
    assert n >= 2

    text = out.read_text(encoding="utf-8")
    assert "# Helix memory" in text
    assert "## project:billing" in text
    assert "Postgres" in text
    eng.close()
