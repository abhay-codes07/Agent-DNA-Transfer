"""Adapter tests — Helix as the memory layer for LangGraph + AutoGen. Offline / $0.

The adapters are duck-typed (they don't import the frameworks), so these exercise the
engine-backed behavior directly without LangGraph/AutoGen installed.
"""

from __future__ import annotations

import asyncio

from helix_core.config import Config
from helix_core.engine import Engine
from helix_sdk.integrations.autogen import HelixMemory
from helix_sdk.integrations.langgraph import HelixStore


def test_langgraph_store_put_and_search(tmp_path):
    eng = Engine(Config(home=tmp_path))
    store = HelixStore(engine=eng)
    ns = ("billing",)
    store.put(ns, "k1", {"content": "We use Postgres for the billing service"})
    store.put(ns, "k2", {"content": "All API errors use RFC-7807"})
    res = store.search(ns, query="which database for billing", limit=5)
    assert res and any("Postgres" in i.value["content"] for i in res)
    assert res[0].score >= 0.0
    store.close()


def test_langgraph_store_async_mirror(tmp_path):
    eng = Engine(Config(home=tmp_path))
    store = HelixStore(engine=eng)
    ns = ("proj",)
    asyncio.run(store.aput(ns, "k", "We deploy on Fly.io"))
    res = asyncio.run(store.asearch(ns, query="where do we deploy"))
    assert any("Fly.io" in i.value["content"] for i in res)
    store.close()


def test_autogen_memory_add_query_update(tmp_path):
    eng = Engine(Config(home=tmp_path))
    mem = HelixMemory(engine=eng, scope="project:x", k=5)
    asyncio.run(mem.add("Events flow through NATS not Kafka"))
    res = asyncio.run(mem.query("what message bus do we use"))
    assert res and any("NATS" in r["content"] for r in res)
    block = asyncio.run(mem.update_context(None))
    assert isinstance(block, str) and "NATS" in block
    asyncio.run(mem.close())
