// Helix browser extension — background service worker (v2 plan §5.5).
// All loopback traffic goes through here so content scripts on https pages don't hit
// mixed-content rules. It only ever talks to 127.0.0.1 — local-first, $0.

const ENDPOINT = "http://127.0.0.1:8787";

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.type === "remember") {
    fetch(ENDPOINT + "/api/remember", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: msg.content, scope: msg.scope || "global" }),
    })
      .then((r) => r.json())
      .then((d) => reply({ ok: true, op: d.results && d.results[0] && d.results[0].op }))
      .catch((e) => reply({ ok: false, error: String(e) }));
    return true; // async response
  }
  if (msg.type === "ping") {
    fetch(ENDPOINT + "/api/health")
      .then((r) => reply({ ok: r.ok }))
      .catch(() => reply({ ok: false }));
    return true;
  }
  return false;
});
