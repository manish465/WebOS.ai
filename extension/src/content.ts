import { PerceptionEngine } from "./perception.js";
import { ActionExecutor } from "./executor.js";
import { BrowserAction } from "./types.js";

// Content script message listener
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "PING") {
    sendResponse({ status: "ok", url: window.location.href, title: document.title });
    return true;
  }

  if (message.type === "CAPTURE_SNAPSHOT") {
    try {
      const snapshot = PerceptionEngine.captureSnapshot(message.sessionId || "default");
      sendResponse({ status: "success", snapshot });
    } catch (err: any) {
      sendResponse({ status: "error", error: err.message });
    }
    return true;
  }

  if (message.type === "EXECUTE_ACTION") {
    const action: BrowserAction = message.action;
    ActionExecutor.execute(action)
      .then((outcome) => {
        sendResponse({ status: "success", outcome });
      })
      .catch((err) => {
        sendResponse({ status: "error", error: err.message });
      });
    return true; // Asynchronous response
  }

  return false;
});
