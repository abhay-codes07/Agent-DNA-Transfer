"""Framework adapters (v2 plan §5.3) — drop Helix in as the memory layer for popular agent
frameworks. Each adapter is import-safe without the framework installed, so importing this
package never fails; the framework is only needed to actually wire the adapter into a graph/agent.

    from helix_sdk.integrations.langgraph import HelixStore   # graph.compile(store=HelixStore())
    from helix_sdk.integrations.autogen import HelixMemory     # AssistantAgent(memory=[HelixMemory()])
"""

from __future__ import annotations

__all__ = ["langgraph", "autogen"]
