// Helix browser extension — content script (v2 plan §5.5).
// Adds a floating "Save to Helix" button on ChatGPT/Claude/Gemini. Select text in the
// conversation, click, and it's distilled into your local memory (Helix extracts the durable
// facts — we only send what you selected, never the whole page).

(function () {
  if (window.__helixInjected) return;
  window.__helixInjected = true;

  const btn = document.createElement("button");
  btn.textContent = "🧬 Save to Helix";
  btn.style.cssText =
    "position:fixed;bottom:18px;right:18px;z-index:2147483647;background:linear-gradient(120deg,#5b8cff,#7b5bff);" +
    "color:#fff;border:none;border-radius:10px;padding:10px 14px;font:13px system-ui,sans-serif;cursor:pointer;" +
    "box-shadow:0 6px 20px rgba(0,0,0,.35)";
  btn.onclick = () => {
    const sel = String(window.getSelection() || "").trim();
    if (!sel) return toast("Select some text in the chat to save first.");
    const scope = "project:" + location.hostname.split(".")[0];
    chrome.runtime.sendMessage({ type: "remember", content: sel, scope }, (res) => {
      toast(res && res.ok ? "🧬 Saved to Helix" : "Helix not reachable — run `helix dashboard`");
    });
  };
  document.documentElement.appendChild(btn);

  function toast(text) {
    const t = document.createElement("div");
    t.textContent = text;
    t.style.cssText =
      "position:fixed;bottom:64px;right:18px;z-index:2147483647;background:#222a3a;color:#e6e9ef;" +
      "border:1px solid rgba(255,255,255,.14);border-radius:8px;padding:9px 13px;font:13px system-ui;" +
      "box-shadow:0 6px 20px rgba(0,0,0,.35);opacity:0;transition:opacity .2s";
    document.documentElement.appendChild(t);
    requestAnimationFrame(() => (t.style.opacity = "1"));
    setTimeout(() => {
      t.style.opacity = "0";
      setTimeout(() => t.remove(), 250);
    }, 2400);
  }
})();
