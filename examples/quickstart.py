"""Quickstart: portable memory in ~10 lines, $0 and offline.

Target experience (Phase 1+). Run after `uv sync`:

    uv run python examples/quickstart.py
"""

from __future__ import annotations

from helix_sdk import Helix


def main() -> None:
    mem = Helix()  # opens your local strand; local embeddings, no key, no network

    # Teach it durable facts (scoped to a project).
    mem.remember("We use FastAPI + Postgres; events via NATS.", scope="project:billing-svc")
    mem.remember("All API errors use RFC-7807 problem+json.", scope="project:billing-svc")
    mem.remember("Chose Postgres over Mongo — needs ACID for money.", scope="project:billing-svc")

    # Later — in *any* connected agent — recall without re-explaining.
    for hit in mem.recall("how do we format API errors here?", scope="project:billing-svc"):
        print(f"[{hit.score:.2f}] {hit.memory.content}")


if __name__ == "__main__":
    main()
