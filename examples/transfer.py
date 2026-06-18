"""Export your memory to a portable .dna, then import it 'on another machine' and recall.

Runnable:  uv run python examples/transfer.py   (needs PyNaCl for the .dna crypto)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from helix_core.config import Config
from helix_sdk import Helix

PASSPHRASE = "example-passphrase"


def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)

        # --- machine A: remember some facts, export a signed+encrypted .dna ---
        a = Helix(Config(home=root / "machine-a"))
        a.remember("We chose Postgres over Mongo for billing — needs ACID.", scope="project:billing")
        a.remember("All API errors use RFC-7807.", scope="project:billing")
        dna = root / "my-brain.dna"
        manifest = a.export(str(dna), passphrase=PASSPHRASE, label="laptop")
        print(f"exported {manifest.count_memories} memories -> {dna.name}")
        print(f"  signature valid: {a.verify(str(dna))['signature_valid']}")
        a.close()

        # --- machine B: import it and recall, with no re-explaining ---
        b = Helix(Config(home=root / "machine-b"))
        b.import_(str(dna), passphrase=PASSPHRASE, as_strand="work")
        b.close()

        c = Helix(Config(home=root / "machine-b", strand="work"))
        print("recall on machine B:")
        for hit in c.recall("which database did we pick for billing?", scope="project:billing"):
            print(f"  [{hit.score:.2f}] {hit.memory.content}")
        c.close()


if __name__ == "__main__":
    main()
