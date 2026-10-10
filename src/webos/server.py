"""
WebOS.ai — Copilot-Grade Autonomous Browser Web Server & Chat UI

A modern, developer-centric interface inspired by GitHub Copilot and Cursor IDE.
Features:
- Copilot-style '@' mention system (@jobpilot, @browser, @dossier)
- Clean, un-vibe-coded design system (Zinc/Slate theme, no speech bubble tails)
- Real Markdown rendering with syntax highlighting & tables
- Live Browser Viewport & 0-Token AXTree Inspector
- Deterministic CDP control with congestion-free status streaming
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


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#3b82f6"><circle cx="12" cy="12" r="10" stroke="#60a5fa" stroke-width="2" fill="#18181b"/><path d="M12 2a10 10 0 0 1 10 10M12 22a10 10 0 0 1-10-10" stroke="#3b82f6" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="#60a5fa"/></svg>"""

HTML_UI = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WebOS.ai — Autonomous Browser Copilot</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <!-- Lightweight Markdown & Syntax Styler -->
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {
      --bg: #09090b;
      --sidebar: #121215;
      --card: #18181b;
      --card-hover: #222227;
      --border: #27272a;
      --border-subtle: #1f1f23;
      --text: #fafafa;
      --text-muted: #a1a1aa;
      --text-dim: #71717a;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --accent-glow: rgba(59, 130, 246, 0.15);
      --success: #10b981;
      --danger: #ef4444;
      --font-mono: "JetBrains Mono", SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* Top Navigation Bar */
    header {
      background: var(--sidebar);
      border-bottom: 1px solid var(--border);
      padding: 10px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 52px;
      z-index: 50;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-logo {
      width: 24px;
      height: 24px;
      border-radius: 6px;
      background: linear-gradient(135deg, #3b82f6, #1d4ed8);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 13px;
      color: #fff;
    }
    .brand-title {
      font-size: 15px;
      font-weight: 600;
      letter-spacing: -0.3px;
      color: #fff;
    }
    .brand-badge {
      font-size: 11px;
      font-family: var(--font-mono);
      background: #27272a;
      color: #a1a1aa;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid #3f3f46;
    }

    .header-center {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .plugin-pill {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      background: rgba(59, 130, 246, 0.1);
      border: 1px solid rgba(59, 130, 246, 0.25);
      color: #60a5fa;
      padding: 3px 10px;
      border-radius: 99px;
      font-family: var(--font-mono);
    }
    .plugin-pill.active {
      background: rgba(16, 185, 129, 0.1);
      border-color: rgba(16, 185, 129, 0.25);
      color: #34d399;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .status-badge {
      font-size: 12px;
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--danger);
    }
    .status-dot.connected {
      background: var(--success);
      box-shadow: 0 0 8px rgba(16, 185, 129, 0.4);
    }

    .btn {
      background: var(--card);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }
    .btn:hover { background: var(--card-hover); border-color: #3f3f46; }
    .btn-primary {
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }
    .btn-primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }

    /* App Split Workspace */
    .app-workspace {
      display: grid;
      grid-template-columns: 500px 1fr;
      flex: 1;
      height: calc(100vh - 52px);
      overflow: hidden;
    }

    /* Left Panel: Browser Viewport & Inspector */
    .browser-panel {
      background: var(--sidebar);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .browser-toolbar {
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 8px;
      background: #0f0f12;
    }
    .nav-btn {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .nav-btn:hover { background: #1e1e24; color: #fff; }
    .address-bar {
      flex: 1;
      display: flex;
      align-items: center;
      background: #18181b;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 12px;
      font-family: var(--font-mono);
      color: #93c5fd;
      gap: 6px;
    }
    .address-bar input {
      background: transparent;
      border: none;
      outline: none;
      color: inherit;
      font-family: inherit;
      font-size: inherit;
      width: 100%;
    }

    .panel-tabs {
      display: flex;
      border-bottom: 1px solid var(--border);
      background: #121215;
    }
    .panel-tab {
      padding: 8px 16px;
      font-size: 12px;
      font-weight: 500;
      color: var(--text-dim);
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.15s;
    }
    .panel-tab.active {
      color: #fff;
      border-bottom-color: var(--accent);
      background: rgba(255, 255, 255, 0.02);
    }

    .tab-content {
      flex: 1;
      overflow-y: auto;
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    /* Live Screenshot Viewport */
    .viewport-container {
      width: 100%;
      height: 320px;
      background: #000;
      border: 1px solid var(--border);
      border-radius: 8px;
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .viewport-img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
    .viewport-overlay {
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(0, 0, 0, 0.65);
      backdrop-filter: blur(4px);
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-family: var(--font-mono);
      color: #34d399;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }

    /* Candidates Inspector */
    .inspector-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }
    .inspector-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .search-filter {
      width: 100%;
      background: #18181b;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      color: #fff;
      font-size: 12px;
      outline: none;
      margin-bottom: 8px;
    }
    .search-filter:focus { border-color: var(--accent); }
    .candidates-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-height: calc(100vh - 460px);
      overflow-y: auto;
    }
    .candidate-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .candidate-card:hover {
      background: var(--card-hover);
      border-color: var(--accent);
    }
    .cand-name {
      font-weight: 500;
      color: #f3f4f6;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 320px;
    }
    .cand-badge {
      font-family: var(--font-mono);
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 4px;
      background: #27272a;
      color: #93c5fd;
    }

    /* Right Panel: Copilot Chat */
    .chat-panel {
      display: flex;
      flex-direction: column;
      height: 100%;
      background: var(--bg);
      position: relative;
    }
    .chat-header {
      padding: 12px 24px;
      border-bottom: 1px solid var(--border);
      background: #0d0d10;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .chat-header-title {
      font-size: 13px;
      font-weight: 600;
      color: #e4e4e7;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .chat-stream {
      flex: 1;
      overflow-y: auto;
      padding: 24px 32px;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    /* Copilot Flat Message Block */
    .copilot-msg {
      display: flex;
      gap: 16px;
      max-width: 900px;
      width: 100%;
    }
    .msg-avatar {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      font-weight: 600;
      flex-shrink: 0;
    }
    .msg-avatar.user { background: #27272a; color: #fff; border: 1px solid #3f3f46; }
    .msg-avatar.copilot {
      background: linear-gradient(135deg, #2563eb, #1d4ed8);
      color: #fff;
    }
    .msg-avatar.jobpilot {
      background: linear-gradient(135deg, #059669, #047857);
      color: #fff;
    }

    .msg-body {
      flex: 1;
      line-height: 1.6;
      font-size: 14px;
      color: #e4e4e7;
    }
    .msg-sender {
      font-size: 13px;
      font-weight: 600;
      color: #fff;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .plugin-tag {
      font-size: 11px;
      font-family: var(--font-mono);
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      padding: 1px 6px;
      border-radius: 4px;
    }

    /* Markdown Elements */
    .msg-body p { margin-bottom: 8px; }
    .msg-body p:last-child { margin-bottom: 0; }
    .msg-body h1, .msg-body h2, .msg-body h3 {
      color: #fff;
      margin: 12px 0 6px 0;
      font-weight: 600;
    }
    .msg-body h3 { font-size: 15px; }
    .msg-body ul, .msg-body ol {
      margin-left: 20px;
      margin-bottom: 8px;
    }
    .msg-body li { margin-bottom: 4px; }
    .msg-body a { color: #60a5fa; text-decoration: none; }
    .msg-body a:hover { text-decoration: underline; }
    .msg-body code {
      font-family: var(--font-mono);
      background: #18181b;
      border: 1px solid #27272a;
      padding: 2px 5px;
      border-radius: 4px;
      font-size: 12px;
      color: #f43f5e;
    }
    .msg-body pre {
      background: #121215;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      overflow-x: auto;
      margin: 10px 0;
    }
    .msg-body pre code {
      background: transparent;
      border: none;
      padding: 0;
      color: #e4e4e7;
    }
    .msg-body table {
      width: 100%;
      border-collapse: collapse;
      margin: 12px 0;
      font-size: 13px;
    }
    .msg-body th, .msg-body td {
      border: 1px solid var(--border);
      padding: 8px 12px;
      text-align: left;
    }
    .msg-body th { background: #18181b; color: #fff; font-weight: 600; }
    .msg-body tr:nth-child(even) { background: rgba(255, 255, 255, 0.015); }

    /* Action Steps Timeline */
    .step-timeline {
      margin-top: 10px;
      background: #121215;
      border: 1px solid var(--border);
      border-radius: 6px;
      overflow: hidden;
    }
    .timeline-header {
      padding: 6px 12px;
      background: #18181b;
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-muted);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      user-select: none;
    }
    .timeline-steps {
      padding: 8px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-family: var(--font-mono);
      font-size: 11px;
    }
    .timeline-row {
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }
    .row-type {
      padding: 1px 5px;
      border-radius: 3px;
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      flex-shrink: 0;
    }
    .row-type.thought { background: #27272a; color: #a1a1aa; }
    .row-type.action { background: #1e3a8a; color: #93c5fd; }
    .row-type.observation { background: #064e3b; color: #6ee7b7; }
    .row-type.error { background: #7f1d1d; color: #fca5a5; }

    /* Copilot Prompt Input Area */
    .chat-footer {
      padding: 16px 32px 24px 32px;
      background: var(--bg);
      position: relative;
    }
    .input-wrapper {
      background: #121215;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 10px 14px;
      transition: all 0.15s;
      position: relative;
    }
    .input-wrapper:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent), 0 0 16px var(--accent-glow);
    }

    /* Active Mentions Bar */
    .mentions-attached {
      display: flex;
      gap: 6px;
      margin-bottom: 6px;
    }
    .mention-chip {
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid rgba(59, 130, 246, 0.3);
      color: #60a5fa;
      font-family: var(--font-mono);
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .mention-remove { cursor: pointer; color: #93c5fd; font-weight: bold; }
    .mention-remove:hover { color: #fff; }

    .prompt-textarea {
      width: 100%;
      background: transparent;
      border: none;
      outline: none;
      color: #fff;
      font-size: 14px;
      line-height: 1.5;
      resize: none;
      height: 48px;
      max-height: 200px;
    }

    .input-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px solid #1f1f23;
    }
    .input-hints {
      font-size: 11px;
      color: var(--text-dim);
      font-family: var(--font-mono);
    }
    .btn-send {
      background: var(--accent);
      color: white;
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
    .btn-send:hover { background: var(--accent-hover); }
    .btn-send:disabled { background: #27272a; color: #71717a; cursor: not-allowed; }

    /* Copilot @ Mention Autocomplete Popover */
    .mention-popover {
      position: absolute;
      bottom: calc(100% + 8px);
      left: 32px;
      background: #18181b;
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.6);
      width: 340px;
      overflow: hidden;
      display: none;
      z-index: 100;
    }
    .popover-header {
      padding: 8px 12px;
      font-size: 11px;
      font-family: var(--font-mono);
      color: var(--text-dim);
      border-bottom: 1px solid #27272a;
      background: #121215;
    }
    .mention-item {
      padding: 10px 14px;
      display: flex;
      flex-direction: column;
      gap: 2px;
      cursor: pointer;
      border-bottom: 1px solid #1f1f23;
      transition: background 0.1s;
    }
    .mention-item:last-child { border-bottom: none; }
    .mention-item:hover, .mention-item.selected {
      background: #27272a;
    }
    .mention-tag {
      font-family: var(--font-mono);
      font-weight: 600;
      font-size: 13px;
      color: #60a5fa;
    }
    .mention-desc {
      font-size: 11px;
      color: var(--text-muted);
    }

    /* Suggested Action Chips */
    .quick-bar {
      display: flex;
      gap: 8px;
      padding: 0 32px 10px 32px;
      overflow-x: auto;
    }
    .quick-chip {
      background: #121215;
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-family: var(--font-mono);
      cursor: pointer;
      white-space: nowrap;
      transition: all 0.15s;
    }
    .quick-chip:hover {
      border-color: var(--accent);
      color: #fff;
      background: #18181b;
    }
  </style>
</head>
<body>
  <!-- Header -->
  <header>
    <div class="brand">
      <div class="brand-logo">W</div>
      <div class="brand-title">WebOS.ai</div>
      <span class="brand-badge">v0.1.0</span>
    </div>

    <div class="header-center">
      <div class="plugin-pill active">
        <span>●</span> @jobpilot ready
      </div>
      <div class="plugin-pill">
        <span>●</span> @browser ready
      </div>
    </div>

    <div class="header-actions">
      <div class="status-badge">
        <span id="statusDot" class="status-dot"></span>
        <span id="statusLabel">Checking Port 9222...</span>
      </div>
      <button class="btn" onclick="launchChrome()">Launch Chrome</button>
      <button class="btn btn-primary" onclick="connectChrome()">Connect</button>
    </div>
  </header>

  <!-- Workspace -->
  <div class="app-workspace">
    <!-- Left: Browser Inspector & Live View -->
    <div class="browser-panel">
      <!-- Toolbar & Address Bar -->
      <div class="browser-toolbar">
        <button class="nav-btn" title="Reload" onclick="reloadPage()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
        </button>
        <div class="address-bar">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          <input id="urlInput" type="text" placeholder="about:blank" onkeydown="if(event.key==='Enter') navigateToUrl()" />
        </div>
        <button class="nav-btn" title="Open in New Tab" onclick="window.open(document.getElementById('urlInput').value, '_blank')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>
        </button>
      </div>

      <!-- Panel Tabs -->
      <div class="panel-tabs">
        <div id="tabViewport" class="panel-tab active" onclick="switchTab('viewport')">Live Viewport</div>
        <div id="tabAXTree" class="panel-tab" onclick="switchTab('axtree')">0-Token AXTree (<span id="candCount">0</span>)</div>
      </div>

      <!-- Tab Content: Live Viewport -->
      <div id="contentViewport" class="tab-content">
        <div class="viewport-container">
          <img id="viewportImg" class="viewport-img" alt="Connecting to Chrome on port 9222..." />
          <div class="viewport-overlay">● LIVE CDP</div>
        </div>
        <div style="font-size: 11px; color: var(--text-dim); font-family: var(--font-mono); line-height: 1.4;">
          The viewport streams high-frequency CDP page captures without interfering with the user session.
        </div>
      </div>

      <!-- Tab Content: AXTree Inspector -->
      <div id="contentAXTree" class="tab-content" style="display: none;">
        <input id="candFilter" class="search-filter" type="text" placeholder="Filter candidates by name or role..." oninput="filterCandidates()" />
        <div id="candidatesList" class="candidates-list">
          <div style="font-size: 12px; color: var(--text-dim); padding: 8px;">No elements detected. Connect to Chrome tab.</div>
        </div>
      </div>
    </div>

    <!-- Right: Copilot Chat -->
    <div class="chat-panel">
      <div class="chat-header">
        <div class="chat-header-title">
          <span>Copilot Agent</span>
          <span style="font-size: 11px; font-weight: normal; color: var(--text-dim);">• Hardware-Aware Autonomous Web Loop</span>
        </div>
        <button class="btn" style="font-size: 11px;" onclick="clearChat()">Clear Session</button>
      </div>

      <!-- Chat Stream -->
      <div id="chatStream" class="chat-stream">
        <div class="copilot-msg">
          <div class="msg-avatar copilot">W</div>
          <div class="msg-body">
            <div class="msg-sender">WebOS Copilot</div>
            <p>Welcome to <strong>WebOS.ai</strong>. I am your autonomous web agent.</p>
            <p>You can command general browser navigation, or type <code>@jobpilot</code> to invoke the late-binding career alignment & ATS application plugin.</p>
          </div>
        </div>
      </div>

      <!-- Quick Action Chips -->
      <div class="quick-bar">
        <div class="quick-chip" onclick="applyPrompt('@jobpilot scan role and auto-apply')">💼 @jobpilot Auto-Apply</div>
        <div class="quick-chip" onclick="applyPrompt('Go to news.ycombinator.com')">📰 Hacker News</div>
        <div class="quick-chip" onclick="applyPrompt('Go to wikipedia.org and search for Quantum Computing')">🔍 Search Wikipedia</div>
        <div class="quick-chip" onclick="applyPrompt('Scroll down')">⬇️ Scroll Down</div>
      </div>

      <!-- Input Bar with @ Mention Popover -->
      <div class="chat-footer">
        <!-- Floating @ Mention Menu -->
        <div id="mentionPopover" class="mention-popover">
          <div class="popover-header">COPILOT PLUGINS & AGENTS</div>
          <div class="mention-item selected" onclick="selectMention('@jobpilot')">
            <div class="mention-tag">@jobpilot</div>
            <div class="mention-desc">Career Alignment, 24-Line LaTeX Resume & ATS Auto-Apply (Greenhouse/Lever/Workday)</div>
          </div>
          <div class="mention-item" onclick="selectMention('@browser')">
            <div class="mention-tag">@browser</div>
            <div class="mention-desc">Autonomous Web Navigation, 0-Token AXTree Perception & DOM Actions</div>
          </div>
          <div class="mention-item" onclick="selectMention('@dossier')">
            <div class="mention-tag">@dossier</div>
            <div class="mention-desc">Inspect Master Career Dossier skills and metrics</div>
          </div>
        </div>

        <div class="input-wrapper">
          <div id="attachedMentions" class="mentions-attached" style="display: none;"></div>
          <textarea
            id="promptInput"
            class="prompt-textarea"
            placeholder="Type a task, or write '@jobpilot' to run career automation... (Press Enter to send)"
            onkeydown="handleKeyDown(event)"
            oninput="handleInput(event)"
          ></textarea>
          <div class="input-actions">
            <div class="input-hints">Tip: Type <strong>@</strong> to mention plugins • Shift+Enter for newline</div>
            <button id="sendBtn" class="btn-send" onclick="submitPrompt()">
              <span>Run Task</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    let allCandidates = [];
    let currentMention = null;

    // Switch between Live Viewport and AXTree Inspector tabs
    function switchTab(tab) {
      document.getElementById('tabViewport').className = 'panel-tab' + (tab === 'viewport' ? ' active' : '');
      document.getElementById('tabAXTree').className = 'panel-tab' + (tab === 'axtree' ? ' active' : '');
      document.getElementById('contentViewport').style.display = tab === 'viewport' ? 'flex' : 'none';
      document.getElementById('contentAXTree').style.display = tab === 'axtree' ? 'flex' : 'none';
      if (tab === 'axtree') {
        fetchCandidates();
      }
    }

    // Status polling (lightweight, zero-congestion)
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const dot = document.getElementById('statusDot');
        const label = document.getElementById('statusLabel');
        const urlInput = document.getElementById('urlInput');

        if (data.connected) {
          dot.className = 'status-dot connected';
          label.innerText = 'Connected (9222)';
          if (document.activeElement !== urlInput && data.url) {
            urlInput.value = data.url;
          }
          if (data.screenshot) {
            document.getElementById('viewportImg').src = 'data:image/jpeg;base64,' + data.screenshot;
          }
          if (data.candidate_count !== undefined) {
            document.getElementById('candCount').innerText = data.candidate_count;
          }
        } else {
          dot.className = 'status-dot';
          label.innerText = 'Disconnected';
        }
      } catch (err) {
        console.error(err);
      }
    }

    async function fetchCandidates() {
      try {
        const res = await fetch('/api/candidates');
        const data = await res.json();
        allCandidates = data.candidates || [];
        document.getElementById('candCount').innerText = allCandidates.length;
        renderCandidates(allCandidates);
      } catch (e) {
        console.error(e);
      }
    }

    function renderCandidates(cands) {
      const list = document.getElementById('candidatesList');
      if (!cands || cands.length === 0) {
        list.innerHTML = '<div style="font-size:12px;color:var(--text-dim);padding:8px;">No candidates matching filter.</div>';
        return;
      }
      list.innerHTML = cands.map(c => `
        <div class="candidate-card" onclick="insertCandidateTarget('${c.name || c.role}')">
          <div class="cand-name">${escapeHtml(c.name || 'unnamed')}</div>
          <div class="cand-badge">#${c.id} ${c.role.toUpperCase()}</div>
        </div>
      `).join('');
    }

    function filterCandidates() {
      const q = document.getElementById('candFilter').value.toLowerCase().trim();
      if (!q) {
        renderCandidates(allCandidates);
        return;
      }
      const filtered = allCandidates.filter(c =>
        (c.name && c.name.toLowerCase().includes(q)) ||
        (c.role && c.role.toLowerCase().includes(q))
      );
      renderCandidates(filtered);
    }

    function insertCandidateTarget(name) {
      const input = document.getElementById('promptInput');
      input.value = `Click on "${name}"`;
      input.focus();
    }

    // Actions
    async function launchChrome() {
      appendCopilotMsg("Launching Google Chrome with remote debugging on port 9222...");
      await fetch('/api/launch_chrome', { method: 'POST' });
      setTimeout(connectChrome, 2000);
    }

    async function connectChrome() {
      appendCopilotMsg("Connecting to Chrome DevTools Protocol WebSocket...");
      const res = await fetch('/api/connect', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        appendCopilotMsg("Connected successfully to Chrome target.");
        updateStatus();
      } else {
        appendCopilotMsg("Connection failed: " + data.error);
      }
    }

    async function reloadPage() {
      await fetch('/api/reload', { method: 'POST' });
      setTimeout(updateStatus, 800);
    }

    async function navigateToUrl() {
      const url = document.getElementById('urlInput').value.trim();
      if (!url) return;
      applyPrompt('Go to ' + url);
    }

    // @ Mention Handling
    function handleInput(e) {
      const val = e.target.value;
      const popover = document.getElementById('mentionPopover');
      if (val.endsWith('@') || val.includes('@job') || val.includes('@bro') || val.includes('@dos')) {
        popover.style.display = 'block';
      } else {
        popover.style.display = 'none';
      }
    }

    function handleKeyDown(e) {
      const popover = document.getElementById('mentionPopover');
      if (popover.style.display === 'block') {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          const items = Array.from(popover.querySelectorAll('.mention-item'));
          let selIdx = items.findIndex(el => el.classList.contains('selected'));
          items[selIdx].classList.remove('selected');
          if (e.key === 'ArrowDown') selIdx = (selIdx + 1) % items.length;
          else selIdx = (selIdx - 1 + items.length) % items.length;
          items[selIdx].classList.add('selected');
          return;
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault();
          const sel = popover.querySelector('.mention-item.selected');
          if (sel) {
            const tag = sel.querySelector('.mention-tag').innerText;
            selectMention(tag);
          }
          return;
        }
        if (e.key === 'Escape') {
          popover.style.display = 'none';
          return;
        }
      }

      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitPrompt();
      }
    }

    function selectMention(tag) {
      const input = document.getElementById('promptInput');
      document.getElementById('mentionPopover').style.display = 'none';
      currentMention = tag;

      // Add attached mention pill
      const bar = document.getElementById('attachedMentions');
      bar.style.display = 'flex';
      bar.innerHTML = `
        <div class="mention-chip">
          <span>${tag}</span>
          <span class="mention-remove" onclick="removeMention()">&times;</span>
        </div>
      `;

      // Remove raw @ from input if typed
      input.value = input.value.replace(/@[a-zA-Z0-9_-]*$/, '').trim();
      input.focus();
    }

    function removeMention() {
      currentMention = null;
      const bar = document.getElementById('attachedMentions');
      bar.style.display = 'none';
      bar.innerHTML = '';
    }

    function applyPrompt(text) {
      const input = document.getElementById('promptInput');
      input.value = text;
      submitPrompt();
    }

    // Submit Prompt
    async function submitPrompt() {
      const input = document.getElementById('promptInput');
      let text = input.value.trim();
      if (!text && !currentMention) return;

      if (currentMention && !text.includes(currentMention)) {
        text = currentMention + ' ' + text;
      }

      input.value = '';
      removeMention();

      // Append User message
      appendUserMsg(text);

      const sendBtn = document.getElementById('sendBtn');
      sendBtn.disabled = true;

      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await res.json();
        const isJobPilot = text.includes('@jobpilot');
        appendCopilotMsg(data.answer || "Action completed.", data.events || [], isJobPilot);
        updateStatus();
      } catch (err) {
        appendCopilotMsg("Error executing automation: " + err);
      } finally {
        sendBtn.disabled = false;
      }
    }

    function appendUserMsg(text) {
      const stream = document.getElementById('chatStream');
      stream.innerHTML += `
        <div class="copilot-msg">
          <div class="msg-avatar user">You</div>
          <div class="msg-body">
            <div class="msg-sender">You</div>
            <p>${escapeHtml(text)}</p>
          </div>
        </div>
      `;
      stream.scrollTop = stream.scrollHeight;
    }

    function appendCopilotMsg(markdownText, steps = [], isJobPilot = false) {
      const stream = document.getElementById('chatStream');
      const avatarClass = isJobPilot ? 'msg-avatar jobpilot' : 'msg-avatar copilot';
      const avatarLabel = isJobPilot ? 'JP' : 'W';
      const senderTitle = isJobPilot ? 'JobPilot.ai Plugin' : 'WebOS Copilot';
      const tagHtml = isJobPilot ? '<span class="plugin-tag">@jobpilot</span>' : '<span class="plugin-tag">@browser</span>';

      let timelineHtml = '';
      if (steps.length > 0) {
        timelineHtml = `
          <div class="step-timeline">
            <div class="timeline-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">
              <span>EXECUTION TRACE (${steps.length} EVENTS)</span>
              <span>▼</span>
            </div>
            <div class="timeline-steps">
              ${steps.map(s => {
                let badgeClass = 'thought';
                if (s.type === 'action') badgeClass = 'action';
                if (s.type === 'observation') badgeClass = 'observation';
                if (s.type === 'error') badgeClass = 'error';
                const desc = s.content || s.details || s.message || '';
                return `
                  <div class="timeline-row">
                    <span class="row-type ${badgeClass}">${s.type}</span>
                    <span style="color: #d1d5db;">${escapeHtml(desc)}</span>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        `;
      }

      const htmlContent = marked.parse(markdownText);

      stream.innerHTML += `
        <div class="copilot-msg">
          <div class="${avatarClass}">${avatarLabel}</div>
          <div class="msg-body">
            <div class="msg-sender">
              <span>${senderTitle}</span>
              ${tagHtml}
            </div>
            ${htmlContent}
            ${timelineHtml}
          </div>
        </div>
      `;
      stream.scrollTop = stream.scrollHeight;
    }

    function clearChat() {
      document.getElementById('chatStream').innerHTML = '';
      appendCopilotMsg("Session cleared. Ready for next command.");
    }

    function escapeHtml(str) {
      return (str || '').replace(/[&<>"']/g, m => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[m]));
    }

    // Initialize polling
    setInterval(updateStatus, 3000);
    updateStatus();
  </script>
</body>
</html>
"""


class WebOSRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler providing REST API and serving UI."""

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_UI.encode("utf-8"))
            return

        elif self.path == "/favicon.ico":
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
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

        elif self.path == "/api/reload":
            future = asyncio.run_coroutine_threadsafe(self._reload_page(runtime), _GLOBAL_LOOP)
            try:
                res = future.result(timeout=4.0)
                self._send_json(res)
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
        """Lightweight status check without congested full AXTree scans."""
        if not runtime.cdp.is_connected:
            return {"connected": False}
        url = await runtime.get_current_url()
        screenshot = await runtime.get_screenshot(quality=55)
        return {
            "connected": True,
            "url": url,
            "screenshot": screenshot,
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
    print(f"       🌐 WebOS.ai Copilot Chat Server Running         ")
    print(f"=======================================================")
    print(f" URL: http://{host}:{port}")
    print(f" Chrome CDP Target: http://127.0.0.1:9222")
    print(f" Supported mentions: @jobpilot, @browser, @dossier")
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
