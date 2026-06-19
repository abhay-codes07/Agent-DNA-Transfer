# Helix Dashboard — Design System

> Research-backed design spec for the local dashboard (the `helix dashboard` daemon).
> Authored 2026-06-20 from four parallel design-research sweeps (visual system, data-viz,
> frontend architecture, UX patterns). The dashboard is the human face of the v2 engine.

## Decisions (the binding ones)

1. **Self-contained, no-build, stdlib-served.** One HTML document served by the Python
   `http.server` daemon — no bundler, no `node_modules`, no CDN, no runtime network calls.
   This is the only architecture consistent with local-first / $0 / offline (ADR-033). The
   unused React/Vite scaffold is retired, not adopted. Reactivity is hand-rolled vanilla JS
   (component-as-function templates + event delegation + a hash router); a real component
   framework (Preact+htm) was evaluated and is a fine future option, but vanilla keeps the
   file truly self-contained with zero vendored bytes.
2. **Graph = hand-rolled canvas force layout.** No graph library. At our scale (tens–low
   thousands of nodes) a few hundred lines of canvas + a simple force sim looks great and adds
   zero dependencies. The graph is Helix's one decorative flourish — invest there, stay flat
   elsewhere.
3. **Charts = pure CSS/SVG.** GitHub-style heatmap in CSS grid; stat cards in CSS; the
   "$0 saved" counter is a ~10-line `requestAnimationFrame` count-up; sparklines are inline SVG.
   No charting library.
4. **Security:** `ThreadingHTTPServer` bound to `127.0.0.1` only, with **Host + Origin
   validation** (403 on mismatch) to defend against DNS-rebinding — a localhost server is not
   safe on loopback alone.

## Visual language (the premium-dev-tool rules)

- **Hairlines, not shadows.** Elevation comes from a 4-step surface ladder
  (`#0b0e14 → #141925 → #1b2230 → #222a3a`) + `rgba(255,255,255,.08)` borders. Real shadows are
  reserved for true overlays (modals, cmd-K).
- **One accent as punctuation.** The blue→violet helix gradient (`#5b8cff → #7b5bff`) appears
  only on the mark, primary actions, active nav, focus rings, and graph edges — never on
  surfaces.
- **Tabular numerals everywhere numeric** (`font-variant-numeric: tabular-nums`) so the $0
  meter, tables, and timeline don't jitter.
- **Type:** system sans stack; 14px body, 12px meta, 24–32px KPIs; weight capped at 600.
- **Spacing** on a 4/8 grid; **radius** 6–8px (12px modals, pills only for status chips).
- **Motion:** animate only `transform`/`opacity`, 150–200ms ease-out; honor
  `prefers-reduced-motion`. The onboarding "graph assembles itself" is the one moment of delight.

## Design tokens

See the `:root` block in `daemon.py`'s `DASHBOARD_HTML` — the canonical token set (surfaces,
hairlines, WCAG-AA text ramp, brand gradient, Primer semantic colors, 4/8 spacing, radius, type,
overlay shadow, motion). Text colors are all AA+ on `#0b0e14`; `#7a8490` is the darkest body-safe
value.

## Views

- **Memories** — search + add; provenance-bearing cards (type, scope, confidence band, stale /
  conflict / signed flags) with why? / edit / forget / **erase (type-to-confirm)**.
- **Copilot** — ask "what do I know about X?"; answers list **sourced** facts (provenance inline),
  suggested-prompt empty state.
- **Graph** — canvas force layout; node color by type, size by recall count; hover highlights a
  node's neighborhood; click opens its card.
- **Review** — keyboard-first queue of stale/conflict items (keep / dismiss); conflicts shown
  side-by-side (pick this / pick other / keep both), always undoable.
- **Insights** — hero stat cards + animated **$0-saved** meter, facts/day heatmap, by-type bars,
  top themes.
- **Timeline** — supersession transitions ("X → Y") + history events, most recent first.
- **Audit** — the hash-chained governance log with an "intact / TAMPERED" badge.
- **cmd-K** — fuzzy palette over actions + memories.

## Sources

Design: designsystems.one/vercel-geist, Linear/Supabase/Raycast/Warp design notes, Material dark
theme, Primer color, WCAG contrast, Lucide icon spec. Viz: vasturiano/force-graph (evaluated),
d3-force, GitHub-contribution-graph CSS, uPlot (evaluated). Architecture: Preact no-build guide,
Open Props, Pico.css, Python http.server, MCP transport security (Origin validation), CVE-2026-11624
(DNS rebinding). UX: Perplexity citations, cmdk, Superhuman/Linear/Anki triage, VS Code merge editor,
NN/g (preattentive viz, destructive actions, vanity metrics), Cloudscape delete-with-confirmation.
