"""
WebOS.ai — High-Craft Autonomous Browser Copilot Server & UI

Designed following the /ideate principles:
- High craft, clean minimalist workspace inspired by Cursor and Perplexity
- Eliminates visual clutter, fake bloated sidebars, and "vibe-coded" amateur styling
- Rock-solid Windows console safety (zero non-ASCII emojis in console prints)
- Native @ mention autocomplete system (@jobpilot, @browser, @dossier)
- Non-blocking, congestion-free CDP status streaming with Cache-Control headers
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
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


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#3b82f6"><rect width="24" height="24" rx="6" fill="#18181b"/><circle cx="12" cy="12" r="5" fill="#3b82f6"/></svg>"""

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebOS Copilot</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {
      --bg: #09090b;
      --surface: #121215;
      --card: #18181b;
      --card-hover: #202024;
      --border: #27272a;
      --border-subtle: #1f1f23;
      --text: #f4f4f5;
      --text-muted: #a1a1aa;
      --text-dim: #71717a;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --jobpilot: #10b981;
      --font-mono: "JetBrains Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* Top Navigation */
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      height: 52px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      z-index: 40;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .brand-badge {
      width: 22px;
      height: 22px;
      border-radius: 5px;
      background: var(--accent);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 12px;
      color: #fff;
    }
    .brand-text {
      font-size: 14px;
      font-weight: 600;
      color: #fff;
      letter-spacing: -0.2px;
    }
    .brand-sub {
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-dim);
      background: #18181b;
      padding: 2px 6px;
      border-radius: 4px;
      border: 1px solid var(--border);
    }

    .header-status {
      display: flex;
      align-items: center;
      gap: 16px;
    }
    .status-indicator {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-family: var(--font-mono);
      color: var(--text-dim);
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #ef4444;
    }
    .dot.connected {
      background: #10b981;
      box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
    }

    .btn {
      background: #18181b;
      border: 1px solid var(--border);
      color: var(--text);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .btn:hover { background: #27272a; border-color: #3f3f46; }
    .btn-accent {
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }
    .btn-accent:hover { background: var(--accent-hover); }

    /* Main Container */
    .main-layout {
      flex: 1;
      display: flex;
      height: calc(100vh - 52px);
      overflow: hidden;
      position: relative;
    }

    /* Primary Chat Workspace (Centered) */
    .chat-container {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      height: 100%;
      overflow: hidden;
      position: relative;
    }

    .chat-scroll {
      width: 100%;
      max-width: 800px;
      flex: 1;
      overflow-y: auto;
      padding: 32px 24px;
      display: flex;
      flex-direction: column;
      gap: 28px;
    }

    /* Welcome Hero */
    .hero-view {
      margin: auto 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      gap: 14px;
    }
    .hero-title {
      font-size: 26px;
      font-weight: 700;
      color: #fff;
      letter-spacing: -0.5px;
    }
    .hero-desc {
      font-size: 14px;
      color: var(--text-muted);
      max-width: 480px;
      line-height: 1.5;
    }

    .hero-chips {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px;
      margin-top: 10px;
      max-width: 600px;
    }
    .chip {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s;
    }
    .chip:hover {
      border-color: var(--accent);
      color: #fff;
      background: var(--card);
    }
    .chip.jobpilot {
      border-color: rgba(16, 185, 129, 0.3);
      color: #34d399;
      background: rgba(16, 185, 129, 0.05);
    }
    .chip.jobpilot:hover {
      background: rgba(16, 185, 129, 0.15);
      border-color: #10b981;
      color: #fff;
    }

    /* Message Rows */
    .msg-row {
      display: flex;
      gap: 14px;
      width: 100%;
    }
    .avatar {
      width: 28px;
      height: 28px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
      font-weight: 700;
      flex-shrink: 0;
    }
    .avatar.user { background: #27272a; color: #fff; }
    .avatar.copilot { background: var(--accent); color: #fff; }
    .avatar.jobpilot { background: var(--jobpilot); color: #fff; }

    .msg-content {
      flex: 1;
      line-height: 1.6;
      font-size: 14px;
      color: #e4e4e7;
    }
    .msg-author {
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .badge-plugin {
      font-size: 10px;
      font-family: var(--font-mono);
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    .msg-content p { margin-bottom: 8px; }
    .msg-content p:last-child { margin-bottom: 0; }
    .msg-content h1, .msg-content h2, .msg-content h3 { color: #fff; margin: 12px 0 6px 0; }
    .msg-content h3 { font-size: 15px; }
    .msg-content ul, .msg-content ol { margin-left: 20px; margin-bottom: 8px; }
    .msg-content a { color: #60a5fa; text-decoration: none; }
    .msg-content a:hover { text-decoration: underline; }
    .msg-content code {
      font-family: var(--font-mono);
      background: #18181b;
      border: 1px solid #27272a;
      padding: 2px 5px;
      border-radius: 4px;
      font-size: 12px;
      color: #f43f5e;
    }
    .msg-content pre {
      background: #121215;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      overflow-x: auto;
      margin: 10px 0;
    }
    .msg-content pre code { background: transparent; border: none; padding: 0; color: #e4e4e7; }
    .msg-content table {
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      font-size: 13px;
    }
    .msg-content th, .msg-content td {
      border: 1px solid var(--border);
      padding: 8px 12px;
      text-align: left;
    }
    .msg-content th { background: #18181b; color: #fff; }

    /* Trace Details */
    .trace-card {
      margin-top: 10px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #121215;
      font-family: var(--font-mono);
      font-size: 11px;
    }
    .trace-title {
      padding: 6px 10px;
      background: #18181b;
      color: var(--text-dim);
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      user-select: none;
    }
    .trace-body {
      padding: 8px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .trace-row { display: flex; gap: 8px; }
    .trace-tag {
      font-size: 9px;
      padding: 1px 4px;
      border-radius: 3px;
      font-weight: 700;
      text-transform: uppercase;
      flex-shrink: 0;
    }
    .trace-tag.thought { background: #27272a; color: #a1a1aa; }
    .trace-tag.action { background: #1e3a8a; color: #93c5fd; }
    .trace-tag.observation { background: #064e3b; color: #6ee7b7; }
    .trace-tag.error { background: #7f1d1d; color: #fca5a5; }

    /* Input Dock */
    .chat-dock {
      width: 100%;
      max-width: 800px;
      padding: 0 24px 24px 24px;
      position: relative;
    }
    .dock-box {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px 14px;
      transition: all 0.15s;
      position: relative;
    }
    .dock-box:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent), 0 0 20px rgba(59, 130, 246, 0.12);
    }

    .mention-badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      font-family: var(--font-mono);
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 4px;
      margin-bottom: 6px;
    }
    .mention-remove { cursor: pointer; color: #a1a1aa; }
    .mention-remove:hover { color: #fff; }

    .dock-textarea {
      width: 100%;
      background: transparent;
      border: none;
      outline: none;
      color: #fff;
      font-size: 14px;
      line-height: 1.5;
      resize: none;
      height: 48px;
      max-height: 180px;
    }

    .dock-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px solid var(--border-subtle);
    }
    .dock-hint {
      font-size: 11px;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .dock-send {
      background: var(--accent);
      color: #fff;
      border: none;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }
    .dock-send:hover { background: var(--accent-hover); }
    .dock-send:disabled { background: #27272a; color: #71717a; cursor: not-allowed; }

    /* Floating Autocomplete Popover */
    .mention-menu {
      position: absolute;
      bottom: calc(100% + 8px);
      left: 24px;
      background: #18181b;
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
      width: 340px;
      display: none;
      z-index: 100;
      overflow: hidden;
    }
    .menu-header {
      padding: 8px 12px;
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-dim);
      background: #121215;
      border-bottom: 1px solid var(--border);
    }
    .menu-item {
      padding: 9px 12px;
      display: flex;
      flex-direction: column;
      gap: 2px;
      cursor: pointer;
      border-bottom: 1px solid var(--border-subtle);
      transition: background 0.1s;
    }
    .menu-item:last-child { border-bottom: none; }
    .menu-item:hover, .menu-item.active { background: #27272a; }
    .menu-tag {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 12px;
      color: #34d399;
    }
    .menu-desc { font-size: 11px; color: var(--text-muted); }

    .btn-session {
      background: rgba(16, 185, 129, 0.15);
      border-color: rgba(16, 185, 129, 0.4);
      color: #34d399;
    }
    .btn-session:hover {
      background: rgba(16, 185, 129, 0.25);
      border-color: #10b981;
      color: #fff;
    }
  </style>
</head>
<body>
  <!-- Header -->
  <header>
    <div class="brand">
      <div class="brand-badge">W</div>
      <div class="brand-text">WebOS Copilot</div>
      <span class="brand-sub">Runtime</span>
    </div>

    <div class="header-status">
      <div class="status-indicator">
        <span id="statusDot" class="dot"></span>
        <span id="statusText">Checking Chrome...</span>
      </div>
      <button class="btn btn-session" onclick="launchMainChrome()" title="Restarts Chrome with remote debugging on port 9222 so your real Amazon/LinkedIn sessions and open tabs are preserved">Attach Real Session</button>
      <button class="btn" onclick="launchChrome()">Open Window</button>
      <button class="btn btn-accent" onclick="connectChrome()">Connect</button>
      <button class="btn" onclick="openNewTab()">+ New Tab</button>
    </div>
  </header>

  <!-- Main Split Layout -->
  <div class="main-layout">
    <!-- Chat Workspace -->
    <div class="chat-container">
      <div id="chatScroll" class="chat-scroll">
        <!-- Hero Initial Screen -->
        <div id="heroView" class="hero-view">
          <div class="hero-title">What would you like to automate?</div>
          <div class="hero-desc">
            Autonomous web agent for general browsing, page navigation, and late-binding career autofill.
          </div>
          <div class="hero-chips">
            <div class="chip" onclick="quickPrompt('open amazon and search for cheap headphones')">
              🎧 Search Amazon for Headphones
            </div>
            <div class="chip jobpilot" onclick="quickPrompt('@jobpilot scan active role and auto-apply')">
              💼 @jobpilot: Auto-Apply
            </div>
            <div class="chip" onclick="quickPrompt('Attach my real Chrome session')">
              🔑 Attach My Real Session
            </div>
            <div class="chip" onclick="quickPrompt('Go to news.ycombinator.com and summarize top story')">
              📰 Hacker News Summary
            </div>
            <div class="chip" onclick="quickPrompt('Go to github.com/trending')">
              ⭐ Trending Repos
            </div>
          </div>
        </div>
      </div>

      <!-- Docked Input -->
      <div class="chat-dock">
        <!-- Autocomplete Menu -->
        <div id="mentionMenu" class="mention-menu">
          <div class="menu-header">AVAILABLE PLUGINS & AGENTS</div>
          <div class="menu-item active" onclick="chooseMention('@jobpilot')">
            <div class="menu-tag">@jobpilot</div>
            <div class="menu-desc">Career Alignment, 24-Line LaTeX Resume & ATS Auto-Apply (Greenhouse/Lever/Workday)</div>
          </div>
          <div class="menu-item" onclick="chooseMention('@browser')">
            <div class="menu-tag">@browser</div>
            <div class="menu-desc">Autonomous Web Navigation, 0-Token AXTree Perception & DOM Execution</div>
          </div>
        </div>

        <div class="dock-box">
          <div id="attachedMention" style="display: none;"></div>
          <textarea
            id="promptInput"
            class="dock-textarea"
            placeholder="Type any task, or write '@jobpilot' for career automation... (Press Enter to send)"
            onkeydown="onInputKeyDown(event)"
            oninput="onInputChange(event)"
          ></textarea>
          <div class="dock-bar">
            <div class="dock-hint">Tip: Type <strong>@</strong> for plugins • Shift+Enter for newline</div>
            <button id="sendBtn" class="dock-send" onclick="sendPrompt()">
              <span>Run Task</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let activeMention = null;

    // Status polling
    async function pollStatus() {
      try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error('Server not reachable');
        const data = await res.json();
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');

        if (data.connected) {
          dot.className = 'dot connected';
          const isExt = !!data.extension_connected;
          const isMain = data.session_type === 'main' || isExt;
          const title = data.title ? (data.title.length > 20 ? data.title.substring(0, 20) + '...' : data.title) : 'Connected';
          text.innerText = isExt ? `Real Chrome Attached • ${title}` : (title + (isMain ? ' • Real Profile' : ' • WebOS Profile'));
          text.title = isExt ? 'Live Chrome Session Bridge active (0 isolated profiles, active logins preserved)' : ((data.title || '') + ' - ' + (data.url || ''));
        } else {
          dot.className = 'dot';
          text.innerText = 'Chrome Disconnected';
          text.title = 'Connect via Extension or launch on port 9222';
        }
      } catch (err) {
        document.getElementById('statusDot').className = 'dot';
        document.getElementById('statusText').innerText = 'Server offline';
      }
    }

    // Connection & Tab Controls
    async function launchMainChrome() {
      appendMessage('copilot', `
### ⚡ Attach Your Real Chrome Session (0 Logins, 0 Isolated Windows)
To control your current Chrome browser directly with all your personal accounts (LinkedIn, Amazon, Google):

1. Open **\`chrome://extensions\`** in your browser.
2. Enable **Developer mode** in the top right.
3. Click **Load unpacked** and select:
   \`D:\\DEVLOPMENT\\Projects\\WebOS.ai\\extension\`

*(Or run \`attach_real_chrome.bat\` in the WebOS folder.)*
Once loaded, WebOS automatically attaches to your active tabs!
      `);
      await fetch('/api/launch_extension_chrome', { method: 'POST' });
    }

    async function launchChrome() {
      appendMessage('copilot', 'Connecting to Chrome with your real session and remote debugging...');
      await fetch('/api/launch_chrome', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ main_session: true })
      });
      setTimeout(connectChrome, 2500);
    }

    async function connectChrome() {
      appendMessage('copilot', 'Connecting to Chrome DevTools Protocol...');
      try {
        const res = await fetch('/api/connect', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          appendMessage('copilot', 'Successfully connected to Chrome session.');
          pollStatus();
        } else {
          appendMessage('copilot', 'Connection failed: ' + (data.error || 'Check Chrome is running.'));
        }
      } catch (err) {
        appendMessage('copilot', 'Server connection error: ' + err);
      }
    }

    async function openNewTab() {
      const url = prompt("Enter URL for new tab:", "https://www.linkedin.com");
      if (!url) return;
      appendMessage('copilot', `Opening new tab: ${url}...`);
      try {
        const res = await fetch('/api/new_tab', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url })
        });
        const data = await res.json();
        if (data.success) {
          appendMessage('copilot', `Opened and focused tab in Chrome.`);
          pollStatus();
        } else {
          appendMessage('copilot', `Could not open tab: ${data.error}`);
        }
      } catch (err) {
        appendMessage('copilot', `Error opening tab: ${err}`);
      }
    }

    // @ Mention Logic
    function onInputChange(e) {
      const val = e.target.value;
      const menu = document.getElementById('mentionMenu');
      if (val.endsWith('@') || val.includes('@job') || val.includes('@bro')) {
        menu.style.display = 'block';
      } else {
        menu.style.display = 'none';
      }
    }

    function onInputKeyDown(e) {
      const menu = document.getElementById('mentionMenu');
      if (menu.style.display === 'block') {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const items = Array.from(menu.querySelectorAll('.menu-item'));
          let idx = items.findIndex(el => el.classList.contains('active'));
          items[idx].classList.remove('active');
          if (e.key === 'ArrowDown') idx = (idx + 1) % items.length;
          else idx = (idx - 1 + items.length) % items.length;
          items[idx].classList.add('active');
          return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          const sel = menu.querySelector('.menu-item.active');
          if (sel) {
            chooseMention(sel.querySelector('.menu-tag').innerText);
          }
          return;
        }
        if (e.key === 'Escape') {
          menu.style.display = 'none';
          return;
        }
      }

      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendPrompt();
      }
    }

    function chooseMention(tag) {
      document.getElementById('mentionMenu').style.display = 'none';
      activeMention = tag;
      const badge = document.getElementById('attachedMention');
      badge.style.display = 'inline-flex';
      badge.className = 'mention-badge';
      badge.innerHTML = `<span>${tag}</span><span class="mention-remove" onclick="removeMention()">&times;</span>`;

      const input = document.getElementById('promptInput');
      input.value = input.value.replace(/@[a-zA-Z0-9_-]*$/, '').trim();
      input.focus();
    }

    function removeMention() {
      activeMention = null;
      const badge = document.getElementById('attachedMention');
      badge.style.display = 'none';
      badge.innerHTML = '';
    }

    function quickPrompt(text) {
      const input = document.getElementById('promptInput');
      input.value = text;
      sendPrompt();
    }

    // Submit Prompt
    async function sendPrompt() {
      const input = document.getElementById('promptInput');
      let text = input.value.trim();
      if (!text && !activeMention) return;

      if (activeMention && !text.includes(activeMention)) {
        text = activeMention + ' ' + text;
      }

      input.value = '';
      removeMention();

      // Hide hero view once conversation begins
      const hero = document.getElementById('heroView');
      if (hero) hero.style.display = 'none';

      // Append User message
      appendMessage('user', text);

      const btn = document.getElementById('sendBtn');
      btn.disabled = true;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        const isJobPilot = text.includes('@jobpilot');
        appendMessage(isJobPilot ? 'jobpilot' : 'copilot', data.answer || "Completed.", data.events || []);
        pollStatus();
      } catch (err) {
        appendMessage('copilot', '⚠️ Automation error: ' + err);
      } finally {
        btn.disabled = false;
      }
    }

    function appendMessage(sender, text, events = []) {
      const scroll = document.getElementById('chatScroll');
      const isJob = sender === 'jobpilot';
      const isUser = sender === 'user';

      const avatarClass = isUser ? 'avatar user' : (isJob ? 'avatar jobpilot' : 'avatar copilot');
      const avatarText = isUser ? 'You' : (isJob ? 'JP' : 'W');
      const authorText = isUser ? 'You' : (isJob ? 'JobPilot.ai Plugin' : 'WebOS Copilot');
      const tagHtml = isJob ? '<span class="badge-plugin">@jobpilot</span>' : (!isUser ? '<span class="badge-plugin" style="border-color:rgba(59,130,246,0.3);color:#60a5fa;background:rgba(59,130,246,0.15)">@browser</span>' : '');

      let traceHtml = '';
      if (events && events.length > 0) {
        traceHtml = `
          <div class="trace-card">
            <div class="trace-title" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">
              <span>EXECUTION TRACE (${events.length} STEPS)</span>
              <span>▼</span>
            </div>
            <div class="trace-body">
              ${events.map(ev => {
                let tag = ev.type || 'info';
                let desc = ev.content || ev.details || ev.message || '';
                return `
                  <div class="trace-row">
                    <span class="trace-tag ${tag}">${tag}</span>
                    <span style="color:#d1d5db;">${escapeHtml(desc)}</span>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        `;
      }

      const parsedHtml = marked.parse(text);

      const row = document.createElement('div');
      row.className = 'msg-row';
      row.innerHTML = `
        <div class="${avatarClass}">${avatarText}</div>
        <div class="msg-content">
          <div class="msg-author">
            <span>${authorText}</span>
            ${tagHtml}
          </div>
          ${parsedHtml}
          ${traceHtml}
        </div>
      `;

      scroll.appendChild(row);
      scroll.scrollTop = scroll.scrollHeight;
    }

    function escapeHtml(str) {
      return (str || '').replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[m]));
    }

    setInterval(pollStatus, 3000);
    pollStatus();
  </script>
</body>
</html>
"""

_CURRENT_SESSION_TYPE: str = "main"


async def launch_chrome_browser(use_main_session: bool = True) -> Dict[str, Any]:
    """Launches Chrome with remote debugging on port 9222 with persistent profile and session restoration."""
    global _CURRENT_SESSION_TYPE
    import urllib.request

    # Check if port 9222 is already open and responsive
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.0) as resp:
            _CURRENT_SESSION_TYPE = "main"
            return {"success": True, "message": "Chrome is already running and connected on port 9222."}
    except Exception:
        pass

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

    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    debug_dir = os.path.join(os.path.expanduser("~"), ".webos", "chrome_profile")
    os.makedirs(debug_dir, exist_ok=True)

    cmd = [
        target_path,
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        f"--user-data-dir={debug_dir}",
        "--restore-last-session",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    subprocess.Popen(cmd, creationflags=flags)
    _CURRENT_SESSION_TYPE = "main"
    await asyncio.sleep(2.0)
    return {"success": True, "message": "Chrome launched on port 9222 with persistent session profile."}


class WebOSRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler providing REST API and serving UI."""

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(HTML_UI.encode("utf-8"))
            return

        elif self.path == "/favicon.ico":
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(FAVICON_SVG.encode("utf-8"))
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

        elif self.path == "/api/candidates":
            runtime, _ = get_or_create_runtime()
            future = asyncio.run_coroutine_threadsafe(self._get_candidates(runtime), _GLOBAL_LOOP)
            try:
                data = future.result(timeout=6.0)
            except Exception as e:
                data = {"candidates": [], "error": str(e)}

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
            use_main = bool(req_data.get("main_session", True))
            future = asyncio.run_coroutine_threadsafe(self._launch_chrome(use_main_session=use_main), _GLOBAL_LOOP)
            res = future.result(timeout=10.0)
            self._send_json(res)
            return

        elif self.path == "/api/launch_extension_chrome":
            ext_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "extension"))
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            if os.path.exists(chrome_path):
                subprocess.Popen([chrome_path, f"--load-extension={ext_dir}", "http://127.0.0.1:8080"], creationflags=flags)
                self._send_json({"success": True, "message": "Chrome launched with WebOS Real Session Extension."})
            else:
                self._send_json({"success": False, "error": "Chrome executable not found."})
            return

        elif self.path == "/api/connect":
            future = asyncio.run_coroutine_threadsafe(runtime.connect(port=9222), _GLOBAL_LOOP)
            try:
                target_id = future.result(timeout=6.0)
                self._send_json({"success": True, "target_id": target_id})
            except Exception as err:
                self._send_json({"success": False, "error": str(err)})
            return

        elif self.path == "/api/reload":
            future = asyncio.run_coroutine_threadsafe(self._reload_page(runtime), _GLOBAL_LOOP)
            try:
                res = future.result(timeout=4.0)
                self._send_json(res)
            except Exception as err:
                self._send_json({"success": False, "error": str(err)})
            return

        elif self.path == "/api/new_tab":
            url = req_data.get("url", "https://www.google.com")
            future = asyncio.run_coroutine_threadsafe(runtime.open_tab(url), _GLOBAL_LOOP)
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
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    async def _get_status_data(self, runtime: WebRuntime) -> Dict[str, Any]:
        """Lightweight status check returning connection status and active tab title."""
        from webos.browser.extension_bridge import get_global_bridge
        bridge = get_global_bridge()
        ext_connected = bridge.is_connected

        if not runtime.cdp.is_connected and not ext_connected:
            return {"connected": False, "extension_connected": False}
        url = await runtime.get_current_url()
        title = ""
        try:
            val = await runtime.cdp.evaluate("document.title")
            title = str(val or "")
        except Exception:
            pass
        return {
            "connected": True,
            "url": url,
            "title": title,
            "session_type": "extension_real" if ext_connected else _CURRENT_SESSION_TYPE,
            "extension_connected": ext_connected,
        }

    async def _get_candidates(self, runtime: WebRuntime) -> Dict[str, Any]:
        """On-demand candidate fetch when user inspects the AXTree tab."""
        if not runtime.cdp.is_connected:
            return {"candidates": []}
        try:
            candidates = await runtime.observe(max_candidates=25)
            cand_dicts = [
                {"id": c.candidate_id, "name": c.name, "role": c.role} for c in candidates
            ]
            return {"candidates": cand_dicts}
        except Exception as e:
            return {"candidates": [], "error": str(e)}

    async def _reload_page(self, runtime: WebRuntime) -> Dict[str, Any]:
        if not runtime.cdp.is_connected:
            return {"success": False, "error": "Not connected"}
        await runtime.cdp.send("Page.reload")
        return {"success": True}

    async def _launch_chrome(self, use_main_session: bool = False) -> Dict[str, Any]:
        return await launch_chrome_browser(use_main_session=use_main_session)

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
                final_answer = f"Error: {event.get('message', 'An error occurred.')}"

        if not final_answer and events:
            final_answer = events[-1].get("message") or "Action completed."

        return {"answer": final_answer, "events": events}


def run_server(host: str = "127.0.0.1", port: int = 8080, open_browser: bool = False) -> None:
    """Starts the WebOS interactive chat server and event loop safely without unicode errors."""
    global _GLOBAL_LOOP
    _GLOBAL_LOOP = asyncio.new_event_loop()

    # Background thread running asyncio loop
    def start_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        try:
            from webos.browser.extension_bridge import get_global_bridge
            loop.create_task(get_global_bridge().start())
        except Exception as err:
            logger.warning("Could not start Extension Bridge: %s", err)
        loop.run_forever()

    t = threading.Thread(target=start_loop, args=(_GLOBAL_LOOP,), daemon=True)
    t.start()

    server = ThreadingHTTPServer((host, port), WebOSRequestHandler)
    print("=======================================================")
    print("       WebOS.ai Copilot Chat Server Running            ")
    print("=======================================================")
    print(f" URL: http://{host}:{port}")
    print(f" Chrome CDP Target: http://127.0.0.1:9222")
    print(" Supported mentions: @jobpilot, @browser")
    print(" Press Ctrl+C to terminate.")
    print("=======================================================")
    sys.stdout.flush()

    if open_browser:
        webbrowser.open(f"http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down WebOS server...")
        server.shutdown()


if __name__ == "__main__":
    run_server()
