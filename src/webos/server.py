"""
WebOS.ai — Interactive Browser Automation Web Server & Chat UI

Provides a local, zero-friction graphical Chat Interface at http://localhost:8080
allowing users to command browser automation in plain English with live
perception inspector, screenshot viewer, and JobPilot plugin integration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Any, List, Optional
import webbrowser

from webos.runtime import WebRuntime
from webos.agent import AutonomousBrowserAgent

logger = logging.getLogger(__name__)

# Global runtime & event loop for the server thread
_GLOBAL_LOOP: Optional[asyncio.AbstractEventLoop] = None
_GLOBAL_RUNTIME: Optional[WebRuntime] = None
_GLOBAL_AGENT: Optional[AutonomousBrowserAgent] = None


def get_or_create_runtime() -> tuple[WebRuntime, AutonomousBrowserAgent]:
    global _GLOBAL_RUNTIME, _GLOBAL_AGENT
    if _GLOBAL_RUNTIME is None:
        _GLOBAL_RUNTIME = WebRuntime()
        _GLOBAL_AGENT = AutonomousBrowserAgent(_GLOBAL_RUNTIME)
    return _GLOBAL_RUNTIME, _GLOBAL_AGENT


HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebOS.ai — Autonomous Browser OS</title>
  <style>
    :root {
      --bg: #090d16;
      --card: #111827;
      --card-border: #1f293d;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

    /* Header */
    header {
      background: var(--card);
      border-bottom: 1px solid var(--card-border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 18px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
    .brand span { font-size: 12px; background: rgba(59, 130, 246, 0.2); color: #60a5fa; padding: 2px 8px; border-radius: 99px; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .status-pill {
      font-size: 12px;
      padding: 4px 10px;
      border-radius: 99px;
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
    }
    .status-pill.connected { background: rgba(16, 185, 129, 0.15); color: #34d399; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
    .btn {
      background: var(--accent);
      color: white;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.15s;
    }
    .btn:hover { background: var(--accent-hover); }
    .btn-secondary { background: #1f293d; color: var(--text); }
    .btn-secondary:hover { background: #374151; }

    /* Layout */
    .app-body { display: grid; grid-template-columns: 480px 1fr; flex: 1; height: calc(100vh - 61px); overflow: hidden; }

    /* Left Pane: Browser Inspector */
    .browser-pane {
      background: #0d121f;
      border-right: 1px solid var(--card-border);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      padding: 16px;
      gap: 16px;
    }
    .pane-title { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); }
    .card { background: var(--card); border: 1px solid var(--card-border); border-radius: 8px; padding: 14px; }
    .url-bar {
      display: flex;
      align-items: center;
      background: #0b0f19;
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 13px;
      color: #60a5fa;
      font-family: monospace;
      word-break: break-all;
    }
    .screenshot-box {
      width: 100%;
      height: 240px;
      background: #000;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      border: 1px solid var(--card-border);
    }
    .screenshot-box img { width: 100%; height: 100%; object-fit: contain; }
    .candidates-list { display: flex; flex-direction: column; gap: 6px; max-height: 240px; overflow-y: auto; }
    .candidate-pill {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #131c2e;
      border: 1px solid #1f2b45;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
    }
    .cand-id { color: #60a5fa; font-weight: bold; }
    .cand-role { color: #9ca3af; font-size: 11px; text-transform: uppercase; }

    /* Right Pane: Chat Window */
    .chat-pane { display: flex; flex-direction: column; height: 100%; position: relative; }
    .chat-messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
    .msg { display: flex; flex-direction: column; max-width: 85%; line-height: 1.5; font-size: 14px; }
    .msg.user { align-self: flex-end; }
    .msg.user .bubble { background: #2563eb; color: #fff; border-radius: 12px 12px 2px 12px; padding: 10px 16px; }
    .msg.agent { align-self: flex-start; }
    .msg.agent .bubble { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px 12px 12px 2px; padding: 14px 18px; }
    .steps-accordion {
      margin-top: 8px;
      background: #0b0f19;
      border: 1px solid #1f293d;
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 12px;
      font-family: monospace;
      color: #9ca3af;
    }
    .step-item { margin: 4px 0; display: flex; gap: 6px; }
    .badge { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 600; text-transform: uppercase; }
    .badge-thought { background: #374151; color: #9ca3af; }
    .badge-action { background: #1e3a8a; color: #93c5fd; }
    .badge-obs { background: #064e3b; color: #6ee7b7; }

    /* Quick Action Chips */
    .quick-chips { display: flex; gap: 8px; padding: 0 24px 12px 24px; overflow-x: auto; }
    .chip {
      background: #111827;
      border: 1px solid #1f293d;
      color: #9ca3af;
      padding: 6px 12px;
      border-radius: 99px;
      font-size: 12px;
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .chip:hover { border-color: #3b82f6; color: #fff; }

    /* Input Footer */
    .chat-input-bar {
      padding: 16px 24px;
      background: var(--card);
      border-top: 1px solid var(--card-border);
      display: flex;
      gap: 12px;
    }
    .chat-input {
      flex: 1;
      background: #090d16;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 12px 16px;
      color: #fff;
      font-size: 14px;
      outline: none;
    }
    .chat-input:focus { border-color: var(--accent); }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>🌐 WebOS.ai</h1>
      <span>Browser OS Core</span>
      <span style="background: rgba(16, 185, 129, 0.2); color: #34d399;">JobPilot Plugin Active</span>
    </div>
    <div class="header-actions">
      <div id="statusPill" class="status-pill">
        <span class="status-dot"></span>
        <span id="statusText">Checking Chrome...</span>
      </div>
      <button class="btn btn-secondary" onclick="launchChrome()">Launch Chrome</button>
      <button class="btn" onclick="connectChrome()">Connect (9222)</button>
    </div>
  </header>

  <div class="app-body">
    <!-- Left Pane: Browser Inspector -->
    <div class="browser-pane">
      <div class="pane-title">Active Browser Tab</div>
      <div id="urlDisplay" class="url-bar">about:blank</div>

      <div class="pane-title">Viewport View</div>
      <div class="screenshot-box">
        <img id="screenshotImg" alt="No browser session connected. Click Launch Chrome." />
      </div>

      <div class="pane-title">0-Token AXTree Candidates (<span id="candCount">0</span>)</div>
      <div id="candidatesList" class="candidates-list">
        <div style="font-size: 12px; color: #6b7280; padding: 8px;">No elements detected. Connect to Chrome to scan.</div>
      </div>
    </div>

    <!-- Right Pane: Chat Window -->
    <div class="chat-pane">
      <div id="chatMessages" class="chat-messages">
        <div class="msg agent">
          <div class="bubble">
            <strong>Welcome to WebOS.ai Browser Automation! 👋</strong><br><br>
            I am your autonomous web agent. Type any command in plain English, and I will navigate, inspect, click, search, and automate the browser for you.<br><br>
            <em>Try clicking one of the suggested prompts below, or type your own instructions.</em>
          </div>
        </div>
      </div>

      <div class="quick-chips">
        <div class="chip" onclick="sendPrompt('Go to news.ycombinator.com')">📰 Open Hacker News</div>
        <div class="chip" onclick="sendPrompt('Go to wikipedia.org and search for Quantum Computing')">🔍 Search Wikipedia</div>
        <div class="chip" onclick="sendPrompt('Go to github.com/trending')">⭐ Trending GitHub</div>
        <div class="chip" onclick="sendPrompt('Run JobPilot on this tab to tailor resume and auto-apply')">💼 JobPilot: Auto-Apply</div>
        <div class="chip" onclick="sendPrompt('Scroll down')">⬇️ Scroll Down</div>
      </div>

      <div class="chat-input-bar">
        <input id="chatInput" class="chat-input" type="text" placeholder="Tell WebOS what to do (e.g., 'Go to amazon.com and search for headphones')..." onkeydown="if(event.key==='Enter') submitChat()" />
        <button id="sendBtn" class="btn" onclick="submitChat()">Run Task</button>
      </div>
    </div>
  </div>

  <script>
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const pill = document.getElementById('statusPill');
        const text = document.getElementById('statusText');
        const urlDisplay = document.getElementById('urlDisplay');

        if (data.connected) {
          pill.className = 'status-pill connected';
          text.innerText = 'Connected (Port 9222)';
          urlDisplay.innerText = data.url || 'about:blank';
          if (data.screenshot) {
            document.getElementById('screenshotImg').src = 'data:image/jpeg;base64,' + data.screenshot;
          }
          document.getElementById('candCount').innerText = data.candidates ? data.candidates.length : 0;
          if (data.candidates && data.candidates.length) {
            const list = document.getElementById('candidatesList');
            list.innerHTML = data.candidates.map(c => `
              <div class="candidate-pill">
                <span class="cand-id">#${c.id}</span>
                <span style="font-weight: 500; color: #fff;">${c.name || 'unnamed'}</span>
                <span class="cand-role">${c.role}</span>
              </div>
            `).join('');
          }
        } else {
          pill.className = 'status-pill';
          text.innerText = 'Disconnected';
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function launchChrome() {
      appendAgentMsg("Launching Google Chrome with remote debugging on port 9222...");
      await fetch('/api/launch_chrome', { method: 'POST' });
      setTimeout(connectChrome, 2000);
    }

    async function connectChrome() {
      appendAgentMsg("Connecting to Chrome DevTools Protocol on port 9222...");
      const res = await fetch('/api/connect', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        appendAgentMsg("Successfully connected to Chrome tab! Ready for automation.");
        updateStatus();
      } else {
        appendAgentMsg("Connection failed: " + data.error + ". Make sure Chrome is running.");
      }
    }

    function appendUserMsg(text) {
      const box = document.getElementById('chatMessages');
      box.innerHTML += `<div class="msg user"><div class="bubble">${text}</div></div>`;
      box.scrollTop = box.scrollHeight;
    }

    function appendAgentMsg(text, steps = []) {
      const box = document.getElementById('chatMessages');
      let stepsHtml = '';
      if (steps.length > 0) {
        stepsHtml = '<div class="steps-accordion">' + steps.map(s => {
          let bClass = 'badge-thought';
          if (s.type === 'action') bClass = 'badge-action';
          if (s.type === 'observation') bClass = 'badge-obs';
          return `<div class="step-item"><span class="badge ${bClass}">${s.type}</span> <span>${s.content || s.details || s.message || ''}</span></div>`;
        }).join('') + '</div>';
      }
      box.innerHTML += `<div class="msg agent"><div class="bubble">${text}${stepsHtml}</div></div>`;
      box.scrollTop = box.scrollHeight;
    }

    function sendPrompt(text) {
      document.getElementById('chatInput').value = text;
      submitChat();
    }

    async function submitChat() {
      const input = document.getElementById('chatInput');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';
      appendUserMsg(text);

      const sendBtn = document.getElementById('sendBtn');
      sendBtn.disabled = true;
      sendBtn.innerText = 'Executing...';

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        appendAgentMsg(data.answer || data.message || "Completed.", data.events || []);
        updateStatus();
      } catch (err) {
        appendAgentMsg("Error executing automation: " + err);
      } finally {
        sendBtn.disabled = false;
        sendBtn.innerText = 'Run Task';
      }
    }

    setInterval(updateStatus, 3000);
    updateStatus();
  </script>
</body>
</html>
"""


class WebOSRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler providing REST API and serving UI."""

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_UI.encode("utf-8"))
            return

        elif self.path == "/api/status":
            runtime, _ = get_or_create_runtime()
            future = asyncio.run_coroutine_threadsafe(self._get_status_data(runtime), _GLOBAL_LOOP)
            try:
                data = future.result(timeout=4.0)
            except Exception as e:
                data = {"connected": False, "error": str(e)}

            self._send_json(data)
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            req_data = {}

        runtime, agent = get_or_create_runtime()

        if self.path == "/api/launch_chrome":
            future = asyncio.run_coroutine_threadsafe(self._launch_chrome(), _GLOBAL_LOOP)
            res = future.result(timeout=5.0)
            self._send_json(res)
            return

        elif self.path == "/api/connect":
            future = asyncio.run_coroutine_threadsafe(runtime.connect(port=9222), _GLOBAL_LOOP)
            try:
                target_id = future.result(timeout=6.0)
                self._send_json({"success": True, "target_id": target_id})
            except Exception as err:
                self._send_json({"success": False, "error": str(err)})
            return

        elif self.path == "/api/chat":
            msg = req_data.get("message", "")
            future = asyncio.run_coroutine_threadsafe(self._run_chat_task(agent, msg), _GLOBAL_LOOP)
            try:
                result = future.result(timeout=60.0)
                self._send_json(result)
            except Exception as err:
                self._send_json({"error": str(err)})
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: Dict[str, Any]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    async def _get_status_data(self, runtime: WebRuntime) -> Dict[str, Any]:
        if not runtime.cdp.is_connected:
            return {"connected": False}
        url = await runtime.get_current_url()
        screenshot = await runtime.get_screenshot()
        try:
            candidates = await runtime.observe(max_candidates=25)
            cand_dicts = [
                {"id": c.candidate_id, "name": c.name, "role": c.role} for c in candidates
            ]
        except Exception:
            cand_dicts = []

        return {
            "connected": True,
            "url": url,
            "screenshot": screenshot,
            "candidates": cand_dicts,
        }

    async def _launch_chrome(self) -> Dict[str, Any]:
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ]
        target_path = None
        for p in chrome_paths:
            if os.path.exists(p):
                target_path = p
                break

        if not target_path:
            return {"success": False, "error": "Chrome executable not found on host."}

        debug_dir = os.path.join(os.environ.get("TEMP", "C:/Temp"), "webos_chrome_profile")
        cmd = [
            target_path,
            "--remote-debugging-port=9222",
            f"--user-data-dir={debug_dir}",
        ]
        subprocess.Popen(cmd)
        return {"success": True, "message": "Chrome launched."}

    async def _run_chat_task(
        self, agent: AutonomousBrowserAgent, message: str
    ) -> Dict[str, Any]:
        events: List[Dict[str, Any]] = []
        final_answer = ""
        async for event in agent.execute_instruction(message):
            events.append(event)
            if event.get("type") == "answer":
                final_answer = event.get("content", "")
            elif event.get("type") == "error":
                final_answer = f"⚠️ {event.get('message', 'An error occurred.')}"

        if not final_answer and events:
            final_answer = events[-1].get("message") or "Action completed."

        return {"answer": final_answer, "events": events}


def run_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = True) -> None:
    """Starts the WebOS interactive chat server and event loop."""
    global _GLOBAL_LOOP
    _GLOBAL_LOOP = asyncio.new_event_loop()

    # Background thread running asyncio loop
    def start_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    t = threading.Thread(target=start_loop, args=(_GLOBAL_LOOP,), daemon=True)
    t.start()

    server = ThreadingHTTPServer((host, port), WebOSRequestHandler)
    print(f"\n=======================================================")
    print(f"       🌐 WebOS.ai Interactive Chat UI Running         ")
    print(f"=======================================================")
    print(f" URL: http://{host}:{port}")
    print(f" Chrome CDP Target: http://127.0.0.1:9222")
    print(f" Press Ctrl+C to terminate.")
    print(f"=======================================================\n")

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down WebOS server...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
