// Helix browser extension — popup (v2 plan §5.5).
const ENDPOINT = "http://127.0.0.1:8787";

chrome.runtime.sendMessage({ type: "ping" }, (res) => {
  const ok = res && res.ok;
  document.getElementById("dot").style.background = ok ? "#3fb950" : "#f85149";
  document.getElementById("status").textContent = ok
    ? "connected to your local memory"
    : "not connected";
});

document.getElementById("open").onclick = () => {
  chrome.tabs.create({ url: ENDPOINT });
};
