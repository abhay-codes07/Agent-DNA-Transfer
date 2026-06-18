"""Encrypted team sync: teammate A pushes, teammate B pulls + merges (no secret leakage).

Runnable:  uv run python examples/team_sync.py   (needs PyNaCl)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from helix_core.config import Config
from helix_sdk import Helix

PASSPHRASE = "team-shared-passphrase"


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        shared = root / "shared-folder"  # e.g. a Dropbox/Drive-synced directory

        a = Helix(Config(home=root / "alice"))
        a.remember("Team convention: all API errors use RFC-7807.", scope="project:billing")
        a.remember("We chose Postgres over Mongo for billing.", scope="project:billing")
        a.push(str(shared), passphrase=PASSPHRASE, name="team.dna")
        print("Alice pushed an encrypted team.dna")
        a.close()

        b = Helix(Config(home=root / "bob"))
        b.remember("We chose Postgres over Mongo for billing.", scope="project:billing")  # dup
        res = b.pull(str(shared), passphrase=PASSPHRASE, name="team.dna")
        print(f"Bob pulled + merged: {res['merged']}")
        print("Bob now recalls the shared convention he never typed:")
        for hit in b.recall("how should API errors be formatted", scope="project:billing"):
            print(f"  [{hit.score:.2f}] {hit.memory.content}")
        b.close()


if __name__ == "__main__":
    main()
