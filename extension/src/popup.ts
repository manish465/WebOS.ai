import { PageSnapshot } from "./types.js";

document.addEventListener("DOMContentLoaded", async () => {
  const btnInspect = document.getElementById("btn-inspect") as HTMLButtonElement;
  const btnFill = document.getElementById("btn-fill") as HTMLButtonElement;
  const statControls = document.getElementById("stat-controls") as HTMLElement;
  const statRequired = document.getElementById("stat-required") as HTMLElement;
  const statusDot = document.getElementById("status-dot") as HTMLElement;
  const statusText = document.getElementById("status-text") as HTMLElement;

  // Check connection status
  chrome.runtime.sendMessage({ type: "GET_CONNECTION_STATUS" }, (res) => {
    if (res && res.connected) {
      statusDot.className = "dot";
      statusText.textContent = `Connected :${res.port}`;
    } else {
      statusDot.className = "dot offline";
      statusText.textContent = "Standalone Mode";
    }
  });

  // Query active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  const inspectPage = () => {
    if (!tab || !tab.id) return;
    chrome.tabs.sendMessage(tab.id, { type: "CAPTURE_SNAPSHOT" }, (res) => {
      if (res && res.status === "success") {
        const snapshot: PageSnapshot = res.snapshot;
        statControls.textContent = snapshot.controls.length.toString();
        const requiredCount = snapshot.controls.filter((c) => c.is_required).length;
        statRequired.textContent = requiredCount.toString();
      } else {
        statControls.textContent = "0";
        statRequired.textContent = "0";
      }
    });
  };

  btnInspect.addEventListener("click", inspectPage);

  btnFill.addEventListener("click", () => {
    btnFill.textContent = "⏳ Inspecting & Filling...";
    inspectPage();
    setTimeout(() => {
      btnFill.textContent = "⚡ Fill Active Form";
    }, 1500);
  });

  // Auto-inspect on popup open
  inspectPage();
});
