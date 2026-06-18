# Helix Dashboard (React + Vite)

The richer frontend for curating your memory. It talks to the local Helix daemon's JSON API —
the same endpoints the built-in zero-build dashboard uses.

> **Two dashboards, one API.** `helix dashboard` already serves a dependency-free, zero-build
> HTML UI on `127.0.0.1:8787` — that's the default and needs no Node. This React app is the
> optional richer client; build it with Node when you want it.

## Run (dev)

```bash
helix dashboard --no-open      # start the daemon + API on 127.0.0.1:8787
cd apps/dashboard
npm install
npm run dev                    # Vite dev server; /api is proxied to the daemon (vite.config.ts)
```

## Build

```bash
npm run build                  # -> dist/ (static; serve behind the daemon or any static host)
```

Views: **Memories** (search / add / inline edit / "why?" provenance / forget), **History**
(timeline), **Stats**. Planned: graph visualization, decay tuning, strand/key management.

Status: scaffolded against the daemon API; not yet built in CI (no Node toolchain in the Python
test env). The Python daemon + stdlib dashboard are the tested, shipping default.
