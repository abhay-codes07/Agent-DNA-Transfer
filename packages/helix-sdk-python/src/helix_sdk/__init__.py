"""Helix Python SDK.

A small, ergonomic wrapper over helix_core.Engine for embedding portable memory in custom
agents and scripts — full parity with the CLI/MCP surface. $0/offline by default.

    from helix_sdk import Helix

    mem = Helix()
    mem.remember("We use RFC-7807 for API errors", scope="project:billing-svc")
    for hit in mem.recall("how do we format API errors?", scope="project:billing-svc"):
        print(hit.score, hit.memory.content)
"""

from __future__ import annotations

from typing import Any

from helix_core.config import Config
from helix_core.engine import Engine

__version__ = "0.1.1"


class Helix:
    """Thin, friendly facade over the engine. Same operations as `helix` and the MCP server."""

    def __init__(self, config: Config | None = None) -> None:
        self._engine = Engine(config)

    @property
    def engine(self) -> Engine:
        return self._engine

    # --- memory ---
    def remember(self, content: str, *, scope: str = "global", source: str = "sdk"):
        return self._engine.remember(content, scope=scope, source=source)

    def recall(self, query: str, *, scope: str | None = None, k: int = 8):
        return self._engine.recall(query, scope=scope, k=k)

    def context(
        self, *, scope: str | None = None, query: str | None = None, budget_tokens: int = 1500
    ) -> str:
        return self._engine.context(scope=scope, query=query, budget_tokens=budget_tokens)

    def list(self, *, scope: str | None = None, limit: int = 100):
        return self._engine.list_memories(scope=scope, limit=limit)

    def get(self, memory_id: str):
        return self._engine.get_memory(memory_id)

    def edit(self, memory_id: str, **fields):
        return self._engine.edit_memory(memory_id, **fields)

    def forget(self, id_or_query: str):
        return self._engine.forget(id_or_query)

    def relate(self, from_id: str, to_id: str, relation: str = "related_to") -> str:
        return self._engine.relate(from_id, to_id, relation)

    def maintain(self, **kw) -> dict:
        return self._engine.maintain(**kw)

    def purge(self, **kw) -> dict:
        return self._engine.purge(**kw)

    def history(self, limit: int = 50):
        return self._engine.history(limit)

    def stats(self) -> dict:
        return self._engine.stats()

    # --- v2: copilot, intelligence, observability ---
    def about(self, subject: str, *, k: int = 8) -> dict:
        return self._engine.about(subject, k=k)

    def proactive(self, hint: str, *, scope: str | None = None, k: int = 3):
        return self._engine.proactive(hint, scope=scope, k=k)

    def conflicts(self) -> Any:
        return self._engine.conflicts()

    def review_queue(self) -> Any:
        return self._engine.review_queue()

    def changes(self, *, scope: str | None = None):
        return self._engine.changes(scope=scope)

    def themes(self, *, scope: str | None = None, top: int = 8):
        return self._engine.themes(scope=scope, top=top)

    def analytics(self) -> dict:
        return self._engine.analytics()

    def savings(self) -> dict:
        return self._engine.savings()

    def as_of(self, when):
        return self._engine.as_of(when)

    def consolidate_sleep(self, **kw) -> dict:
        return self._engine.consolidate_sleep(**kw)

    def erase(self, id_or_query: str) -> dict:
        return self._engine.erase(id_or_query)

    # --- v2: procedural / skill memory ---
    def learn_procedure(self, trigger: str, steps: Any, **kw) -> str:
        return self._engine.learn_procedure(trigger, steps, **kw)

    def recall_procedures(self, situation: str, *, scope: str | None = None, k: int = 5):
        return self._engine.recall_procedures(situation, scope=scope, k=k)

    def record_procedure_outcome(self, proc_id: str, success: bool):
        return self._engine.record_procedure_outcome(proc_id, success)

    # --- v2: trust, sharing, governance ---
    def sign_facts(self) -> dict:
        return self._engine.sign_facts()

    def verify_facts(self) -> dict:
        return self._engine.verify_facts()

    def export_share(self, out_path: str, **kw) -> dict:
        return self._engine.export_share(out_path, **kw)

    def import_share(self, path_or_bundle, *, trust: bool = False) -> dict:
        return self._engine.import_share(path_or_bundle, trust=trust)

    def audit_log(self, limit: int = 100):
        return self._engine.audit_log(limit)

    def verify_audit(self) -> bool:
        return self._engine.verify_audit()

    # --- v2: connectors + the portable standard ---
    def ingest_repo(self, path: str, *, scope: str | None = None) -> dict:
        return self._engine.ingest_repo(path, scope=scope)

    def export_portable(self, path: str, *, sign: bool = False) -> dict:
        return self._engine.export_portable(path, sign=sign)

    def conform(self, path: str) -> dict:
        return self._engine.conform(path)

    # --- transfer (.dna) ---
    def export(self, path: str, *, passphrase: str | None = None, label: str = ""):
        return self._engine.export_strand(path, passphrase=passphrase, label=label)

    def verify(self, path: str) -> dict:
        return self._engine.verify_strand(path)

    def import_(
        self,
        path: str,
        *,
        passphrase: str | None = None,
        as_strand: str | None = None,
        replace: bool = False,
    ) -> dict:
        return self._engine.import_strand(
            path, passphrase=passphrase, as_strand=as_strand, replace=replace
        )

    def merge(self, path: str, *, passphrase: str | None = None) -> dict:
        return self._engine.merge_strand(path, passphrase=passphrase)

    def diff(self, path: str, *, passphrase: str | None = None) -> dict:
        return self._engine.diff_strand(path, passphrase=passphrase)

    # --- sync ---
    def push(
        self, location: str, *, passphrase: str | None = None, name: str | None = None
    ) -> dict:
        return self._engine.push(location, passphrase=passphrase, name=name)

    def pull(
        self,
        location: str,
        *,
        passphrase: str | None = None,
        name: str | None = None,
        merge: bool = True,
    ) -> dict:
        return self._engine.pull(location, passphrase=passphrase, name=name, merge=merge)

    def close(self) -> None:
        self._engine.close()

    def __enter__(self) -> "Helix":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


__all__ = ["Helix", "__version__"]
