let socket: WebSocket | null = null;
let isConnected = false;
let desktopPort = 49152; // Default fallback; dynamically updated via configuration
let sessionToken = "";

// Initialize connection to desktop companion
function connectToDesktop() {
  chrome.storage.local.get(["webos_port", "webos_token"], (items) => {
    if (items.webos_port) desktopPort = items.webos_port;
    if (items.webos_token) sessionToken = items.webos_token;

    const url = `ws://127.0.0.1:${desktopPort}/ws?token=${encodeURIComponent(sessionToken)}`;
    try {
      socket = new WebSocket(url);

      socket.onopen = () => {
        isConnected = true;
        chrome.storage.local.set({ desktop_connected: true });
        console.log("[WebOS Extension] Connected to desktop control plane.");
      };

      socket.onmessage = async (event) => {
        try {
          const command = JSON.parse(event.data);
          handleDesktopCommand(command);
        } catch (err) {
          console.error("[WebOS Extension] Error parsing desktop message:", err);
        }
      };

      socket.onclose = () => {
        isConnected = false;
        chrome.storage.local.set({ desktop_connected: false });
        console.warn("[WebOS Extension] Desktop disconnected, retrying in 3s...");
        setTimeout(connectToDesktop, 3000);
      };

      socket.onerror = (err) => {
        console.warn("[WebOS Extension] WebSocket error:", err);
        socket?.close();
      };
    } catch (err) {
      setTimeout(connectToDesktop, 3000);
    }
  });
}

// Forward action requests from desktop to the active browser tab
async function handleDesktopCommand(command: any) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) return;

  if (command.type === "REQUEST_SNAPSHOT") {
    chrome.tabs.sendMessage(tab.id, { type: "CAPTURE_SNAPSHOT", sessionId: command.sessionId }, (res) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "SNAPSHOT_RECEIPT", payload: res?.snapshot }));
      }
    });
  } else if (command.type === "DISPATCH_ACTION") {
    chrome.tabs.sendMessage(tab.id, { type: "EXECUTE_ACTION", action: command.action }, (res) => {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ACTION_RECEIPT", payload: res?.outcome }));
      }
    });
  }
}

// Listen to messages from popup or options page
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_CONNECTION_STATUS") {
    sendResponse({ connected: isConnected, port: desktopPort });
    return true;
  }
  return false;
});

// Boot connection
connectToDesktop();
