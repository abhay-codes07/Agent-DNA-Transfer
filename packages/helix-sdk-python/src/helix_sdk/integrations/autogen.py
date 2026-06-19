"""AutoGen / AG2 adapter — a Memory backed by Helix (v2 plan §5.3).

`HelixMemory` implements AutoGen's `Memory` protocol (`add` / `query` / `update_context` /
`clear` / `close`) over a local, portable `.dna` strand, so an agent's durable knowledge lives
in Helix instead of a transcript buffer:

    from helix_sdk.integrations.autogen import HelixMemory
    agent = AssistantAgent("dev", model_client=..., memory=[HelixMemory(scope="project:billing")])

`update_context` injects the most relevant facts (token-budgeted) as a system message before the
model runs. The adapter is duck-typed — it does not require AutoGen to import — so it stays $0.
"""

from __future__ import annotations

from typing import Any

from helix_core.config import Config
from helix_core.engine import Engine


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return getattr(content, "content", None) or str(content)


class HelixMemory:
    """AutoGen-compatible Memory backed by a local Helix strand."""

    def __init__(
        self,
        engine: Engine | None = None,
        config: Config | None = None,
        *,
        scope: str = "global",
        k: int = 5,
    ) -> None:
        self._engine = engine or Engine(config)
        self.scope = scope
        self.k = k

    async def add(self, content: Any, cancellation_token: Any = None) -> None:
        self._engine.remember(_text(content), scope=self.scope, source="autogen")

    async def query(self, query: Any, cancellation_token: Any = None, **_: Any) -> list[dict]:
        hits = self._engine.recall(_text(query), scope=self.scope, k=self.k)
        return [{"content": h.memory.content, "score": h.score} for h in hits]

    async def update_context(self, model_context: Any = None) -> str:
        """Inject relevant memory as a system message; also return the packed block."""
        block = self._engine.context(scope=self.scope)
        if block and model_context is not None and hasattr(model_context, "add_message"):
            try:  # SystemMessage shape varies by AutoGen version; degrade gracefully
                from autogen_core.models import SystemMessage  # type: ignore

                await model_context.add_message(SystemMessage(content=block))
            except Exception:
                pass
        return block

    async def clear(self) -> None:
        # Helix never bulk-wipes memory (the user owns it); clearing is a no-op by design.
        return None

    async def close(self) -> None:
        self._engine.close()
