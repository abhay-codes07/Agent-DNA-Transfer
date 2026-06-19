# Helix browser extension

Capture ChatGPT / Claude / Gemini conversations into your local Helix memory — a surface MCP
can't reach. Local-first: it only ever talks to `http://127.0.0.1:8787` (your own machine).

## Use

1. Start the local server: `helix dashboard`.
2. Load the extension unpacked: open `chrome://extensions`, enable **Developer mode**, click
   **Load unpacked**, and select this folder.
3. On ChatGPT / Claude / Gemini, **select text** in the conversation and click the floating
   **🧬 Save to Helix** button. Helix distills the durable facts (it only receives your selection,
   never the whole page).

The toolbar popup shows whether Helix is reachable and links to the dashboard.

## Privacy

No analytics, no remote calls. Captured text goes only to your loopback Helix daemon, which stores
distilled facts locally (redacted for secrets/PII on the way in).
