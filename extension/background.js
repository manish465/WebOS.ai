// WebOS Copilot — Chrome Extension Bridge Service Worker
// Enables 0-login, real-session automation via chrome.debugger CDP API

const BRIDGE_URL = "ws://127.0.0.1:9223";
let socket = null;
let isConnected = false;
let attachedTabs = new Set();
let currentActiveTabId = null;

// Connect to WebOS backend bridge
function connectToBridge() {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    socket = new WebSocket(BRIDGE_URL);
  } catch (err) {
    setTimeout(connectToBridge, 2000);
    return;
  }

  socket.onopen = async () => {
    isConnected = true;
    console.log("[WebOS Bridge] Connected to backend on port 9223");
    // Send initial handshake with active tab info
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      currentActiveTabId = tab.id;
      sendToBridge({
        type: "handshake",
        activeTab: { id: String(tab.id), title: tab.title, url: tab.url }
      });
    }
  };

  socket.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data);
      await handleBridgeCommand(msg);
    } catch (e) {
      console.error("[WebOS Bridge] Error handling message:", e);
    }
  };

  socket.onclose = () => {
    isConnected = false;
    socket = null;
    console.log("[WebOS Bridge] Disconnected. Reconnecting in 2s...");
    setTimeout(connectToBridge, 2000);
  };

  socket.onerror = (err) => {
    console.warn("[WebOS Bridge] Socket error:", err);
  };
}

function sendToBridge(data) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data));
  }
}

// Forward CDP events to WebOS
chrome.debugger.onEvent.addListener((source, method, params) => {
  sendToBridge({
    type: "event",
    tabId: String(source.tabId),
    method: method,
    params: params
  });
});

chrome.debugger.onDetach.addListener((source, reason) => {
  attachedTabs.delete(source.tabId);
  sendToBridge({
    type: "detached",
    tabId: String(source.tabId),
    reason: reason
  });
});

// Ensure debugger is attached to the tab
async function ensureAttached(tabId) {
  if (attachedTabs.has(tabId)) return true;
  try {
    await chrome.debugger.attach({ tabId: tabId }, "1.3");
    attachedTabs.add(tabId);
    return true;
  } catch (e) {
    if (e.message && e.message.includes("Already attached")) {
      attachedTabs.add(tabId);
      return true;
    }
    console.error(`[WebOS Bridge] Failed to attach debugger to tab ${tabId}:`, e);
    return false;
  }
}

// Handle commands from WebOS backend
async function handleBridgeCommand(msg) {
  const { id, method, params = {} } = msg;

  // 1. Target Discovery
  if (method === "Target.getTargets" || method === "WebOS.getTargets") {
    const tabs = await chrome.tabs.query({});
    const targets = tabs.map(t => ({
      id: String(t.id),
      targetId: String(t.id),
      title: t.title || "",
      url: t.url || "",
      type: "page",
      webSocketDebuggerUrl: "extension_bridge"
    }));
    sendToBridge({ id, result: { targetInfos: targets, targets: targets } });
    return;
  }

  // 2. Open / Activate New Tab
  if (method === "Target.createTarget" || method === "WebOS.newTab") {
    const targetUrl = params.url || "https://www.google.com";
    const newTab = await chrome.tabs.create({ url: targetUrl, active: true });
    currentActiveTabId = newTab.id;
    await ensureAttached(newTab.id);
    sendToBridge({
      id,
      result: {
        targetId: String(newTab.id),
        id: String(newTab.id),
        url: targetUrl
      }
    });
    return;
  }

  if (method === "Target.activateTarget" || method === "Page.bringToFront" || method === "WebOS.activateTab") {
    let targetTabId = params.targetId ? parseInt(params.targetId, 10) : currentActiveTabId;
    if (!targetTabId) {
      const [cur] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (cur) targetTabId = cur.id;
    }
    if (targetTabId) {
      await chrome.tabs.update(targetTabId, { active: true });
      const tab = await chrome.tabs.get(targetTabId);
      if (tab && tab.windowId) {
        await chrome.windows.update(tab.windowId, { focused: true });
      }
    }
    sendToBridge({ id, result: { success: true } });
    return;
  }

  // Determine which tab to run command on
  let tabId = params.targetId ? parseInt(params.targetId, 10) : null;
  if (!tabId && msg.tabId) tabId = parseInt(msg.tabId, 10);
  if (!tabId) {
    if (currentActiveTabId) {
      tabId = currentActiveTabId;
    } else {
      const [cur] = await chrome.tabs.query({ active: true, currentWindow: true });
      tabId = cur ? cur.id : null;
    }
  }

  if (!tabId) {
    sendToBridge({ id, error: { message: "No active browser tab found to execute command." } });
    return;
  }

  currentActiveTabId = tabId;
  const attached = await ensureAttached(tabId);
  if (!attached) {
    sendToBridge({ id, error: { message: `Could not attach debugger to tab ${tabId}.` } });
    return;
  }

  // Execute CDP command via chrome.debugger.sendCommand
  chrome.debugger.sendCommand({ tabId: tabId }, method, params, (res) => {
    const lastErr = chrome.runtime.lastError;
    if (lastErr) {
      sendToBridge({ id, error: { message: lastErr.message } });
    } else {
      sendToBridge({ id, result: res || {} });
    }
  });
}

// Keep-alive heartbeat and tab update listener
chrome.tabs.onActivated.addListener((info) => {
  currentActiveTabId = info.tabId;
});

// Start connection
connectToBridge();
