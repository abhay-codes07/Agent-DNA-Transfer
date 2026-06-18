import { useEffect, useState } from "react";
import { api, type Hit, type HistoryEntry, type Memory, type MemoryDetail } from "./api";

type Tab = "memories" | "history" | "stats";

export function App() {
  const [tab, setTab] = useState<Tab>("memories");
  return (
    <div className="wrap">
      <header>
        <h1>🧬 Helix</h1>
        <span className="tag">your portable memory — local &amp; private</span>
      </header>
      <nav className="tabs">
        {(["memories", "history", "stats"] as Tab[]).map((t) => (
          <button key={t} className={t === tab ? "active" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      {tab === "memories" && <Memories />}
      {tab === "history" && <History />}
      {tab === "stats" && <Stats />}
    </div>
  );
}

function Memories() {
  const [items, setItems] = useState<(Memory | Hit)[]>([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState("");
  const [scope, setScope] = useState("global");

  const loadAll = () => api.list().then((d) => setItems(d.memories));
  useEffect(() => {
    loadAll();
  }, []);

  const search = () =>
    query ? api.search(query).then((d) => setItems(d.results)) : loadAll();
  const add = async () => {
    if (!draft.trim()) return;
    await api.remember(draft, scope);
    setDraft("");
    loadAll();
  };

  return (
    <section>
      <div className="row">
        <input placeholder="Search your memory…" value={query}
          onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
        <button className="go" onClick={search}>Search</button>
      </div>
      <div className="row">
        <input placeholder="Teach Helix a fact…" value={draft} onChange={(e) => setDraft(e.target.value)} />
        <input className="scope" value={scope} onChange={(e) => setScope(e.target.value)} />
        <button className="go" onClick={add}>Add</button>
      </div>
      {items.map((m) => (
        <Card key={m.id} mem={m} onChange={search} />
      ))}
      {items.length === 0 && <p className="muted">No memories yet — add one above.</p>}
    </section>
  );
}

function Card({ mem, onChange }: { mem: Memory | Hit; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [why, setWhy] = useState<MemoryDetail | null>(null);
  const [content, setContent] = useState(mem.content);
  const score = "score" in mem ? (mem as Hit).score : undefined;

  const save = async () => {
    await api.edit(mem.id, content, mem.scope);
    setEditing(false);
    onChange();
  };

  return (
    <div className="card">
      {editing ? (
        <>
          <textarea value={content} onChange={(e) => setContent(e.target.value)} />
          <div className="meta">
            <button className="go" onClick={save}>Save</button>
            <span className="x" onClick={() => setEditing(false)}>cancel</span>
          </div>
        </>
      ) : (
        <>
          <div>{mem.content}</div>
          <div className="meta">
            {score !== undefined && <span className="score">{score.toFixed(2)}</span>}
            <span className="pill">{mem.type}</span>
            <span className="pill">{mem.scope}</span>
            <span className="x" onClick={() => setEditing(true)}>edit</span>
            <span className="x" onClick={() => api.detail(mem.id).then(setWhy)}>why?</span>
            <span className="x" onClick={() => api.forget(mem.id).then(onChange)}>forget</span>
          </div>
          {why && (
            <div className="prov">
              {why.provenance.map((p, i) => (
                <div key={i}>source {p.agent ?? "?"} · extractor {p.extractor ?? "?"} · {p.origin}</div>
              ))}
              created {why.created_at?.slice(0, 19).replace("T", " ")} · confidence {why.confidence}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function History() {
  const [rows, setRows] = useState<HistoryEntry[]>([]);
  useEffect(() => {
    api.history().then((d) => setRows(d.history));
  }, []);
  return (
    <section>
      <h3>Timeline</h3>
      {rows.map((h) => (
        <div className="stat" key={h.seq}>
          <span className="muted">{h.ts?.slice(0, 19).replace("T", " ")}</span>
          <span className="pill">{h.op}</span>
          <span>{h.memory_id}</span>
        </div>
      ))}
      {rows.length === 0 && <p className="muted">No history yet.</p>}
    </section>
  );
}

function Stats() {
  const [stats, setStats] = useState<Record<string, unknown>>({});
  useEffect(() => {
    api.stats().then(setStats);
  }, []);
  return (
    <section>
      {Object.entries(stats).map(([k, v]) => (
        <div className="stat" key={k}>
          <span className="muted">{k}</span>
          <span>{String(v)}</span>
        </div>
      ))}
    </section>
  );
}
