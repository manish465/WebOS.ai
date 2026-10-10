# WebOS.ai — Complete User & Developer Guide

> **Autonomous, Hardware-Aware Browser Operating Substrate**  
> *Deterministic CDP Control • 0-Token AXTree Perception • SQLite Episodic Memory • Air-Gapped Privacy Gateway*

---

## Table of Contents
1. [Overview & Architecture](#1-overview--architecture)
2. [Prerequisites & System Setup](#2-prerequisites--system-setup)
3. [Starting the Chrome CDP Host](#3-starting-the-chrome-cdp-host)
4. [Python API Walkthrough](#4-python-api-walkthrough)
   - [Initializing and Connecting the Runtime](#initializing-and-connecting-the-runtime)
   - [Observing Interactive Elements (0-Token AXTree)](#observing-interactive-elements-0-token-axtree)
   - [Executing Browser Actions & Verification](#executing-browser-actions--verification)
   - [In-Browser HUD (Heads-Up Display) Overlay](#in-browser-hud-heads-up-display-overlay)
   - [Episodic Memory & Flight Recorder](#episodic-memory--flight-recorder)
   - [Privacy Sanitizer & Model Gateway](#privacy-sanitizer--model-gateway)
5. [Running the Test Suite](#5-running-the-test-suite)
6. [Packaging & Wheel Distribution](#6-packaging--wheel-distribution)
7. [Prompting & Browser Automation Guide](#7-prompting--browser-automation-guide)

---

## 1. Overview & Architecture

WebOS.ai is an operating substrate designed for autonomous web agents. Instead of feeding multi-megabyte raw HTML or expensive screenshots into multi-modal LLMs, WebOS.ai extracts a compact, pruned **Accessibility Tree (AXTree)** with 0 LLM tokens, computes interactive bounding boxes, and executes deterministic actions through the **Chrome DevTools Protocol (CDP)**.

```
                      Client Application / Domain Plugin (e.g. JobPilot.ai)
                                         │
                                         ▼
                            WebRuntime (src/webos/runtime.py)
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
  Browser Engine                  Storage Subsystem                 Model Gateway
  • CDP Client (port 9222)        • SQLite (runtime.db)             • PII Air-Gap Sanitizer
  • 0-Token AXTree Pruner         • Episodic Observation Logs       • Rate-Limit Key Ring
  • Action Executor Primitives    • Flight Recorder Telemetry       • Local 3B Grounder
  • Tier-1 & Tier-2 Verifier      • Site Skills (Macros)            • Free Cloud Pool (Gemini/Groq)
  • Shadow DOM HUD Overlay                                          • 1-Click Clipboard Fallback
```

---

## 2. Prerequisites & System Setup

### Requirements
- **Python**: 3.11 or higher
- **Google Chrome** or **Chromium** installed
- Optional: [Ollama](https://ollama.com/) running locally for local grounding (`ollama run llama3.2:3b`)

### Local Installation
```powershell
# Navigate to repository
cd D:\DEVLOPMENT\Projects\WebOS.ai

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Windows PowerShell
# source .venv/bin/activate  # macOS / Linux

# Install package in editable mode with development dependencies
pip install -e ".[dev]"
```

---

## 3. Starting the Chrome CDP Host

WebOS.ai connects to a running Chrome instance via port `9222` using Chrome DevTools Protocol.

### On Windows
```powershell
# Launch Chrome with remote debugging on port 9222
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:TEMP\chrome_debug_profile"
```

### On macOS
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="/tmp/chrome_debug_profile"
```

### On Linux / Headless Docker
```bash
chromium --remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 --headless --no-sandbox --disable-gpu
```

---

## 4. Python API Walkthrough

### Initializing and Connecting the Runtime

```python
import asyncio
from webos import WebRuntime

async def main():
    # Initialize runtime (uses SQLite database 'runtime.db' or in-memory ':memory:')
    runtime = WebRuntime(db_path="runtime.db")

    # Connect to Chrome on CDP port 9222
    target_id = await runtime.connect(host="127.0.0.1", port=9222)
    print(f"Connected to browser tab: {target_id}")

    # Navigate to target web page
    await runtime.navigate("https://news.ycombinator.com")

    await runtime.close()

if __name__ == "__main__":
    asyncio.run(main())
```

---

### Observing Interactive Elements (0-Token AXTree)

WebOS.ai inspects the Chrome Accessibility Tree, pruning non-interactive noise and assigning numerical candidate IDs to interactable elements (buttons, inputs, links, dropdowns).

```python
# Observe interactive candidate elements on current page
candidates = await runtime.observe(max_candidates=25)

for c in candidates:
    print(f"[#{c.candidate_id}] {c.role.upper()}: '{c.name}' at ({c.bbox.x}, {c.bbox.y}, {c.bbox.width}x{c.bbox.height})")
```

---

### Executing Browser Actions & Verification

WebOS.ai executes deterministic mouse and keyboard events and runs **Tier-1** (DOM attribute checks) and **Tier-2** (page structure stability) verification.

```python
from webos.types import BrowserAction

# 1. Ground an intent (find candidate matching 'search')
target = await runtime.ground_intent("search", candidates)

if target:
    # 2. Type search text
    type_action = BrowserAction(
        action_type="type",
        target_candidate_id=target.candidate_id,
        text_value="Artificial Intelligence"
    )
    result = await runtime.execute_step("Input search query", type_action, candidate=target)
    print(f"Step status: {result.success} - {result.message}")

    # 3. Press Enter / Click submit
    click_action = BrowserAction(
        action_type="key_press",
        key_code="Enter"
    )
    await runtime.execute_step("Submit search", click_action)
```

Supported action types:
- `click`: Coordinates-based mouse click with focus dispatch.
- `type`: Native text input with input/change events.
- `scroll`: Smooth wheel delta scrolling.
- `select`: Native `<select>` dropdown option selection.
- `key_press`: Keyboard key code dispatches.

---

### In-Browser HUD (Heads-Up Display) Overlay

When `runtime.connect()` is called, WebOS.ai injects an isolated Shadow DOM overlay into the active webpage. The overlay displays:
- Agent status pill (e.g. *Navigating...*, *Observing...*, *Filling Form...*).
- Candidate bounding boxes with color-coded tags.
- Latency and active telemetry session ID.

You can update the status message manually:
```python
await runtime.hud.set_status(runtime.cdp, "Filling application form...")
```

---

### Episodic Memory & Flight Recorder

Every observation and action sequence is stored locally in SQLite:

```python
# Query recent episodic memory
recent_episodes = runtime.episodic.get_recent_observations(limit=5)
for ep in recent_episodes:
    print(f"Time: {ep.timestamp} | URL: {ep.url} | Candidates observed: {len(ep.candidates)}")

# End telemetry recording session
runtime.flight_recorder.end_session(status="COMPLETED")
```

---

### Privacy Sanitizer & Model Gateway

WebOS.ai includes a built-in PII air-gap sanitizer that masks sensitive candidate data (emails, SSNs, phone numbers, addresses) before sending prompts to external LLMs:

```python
# Raw text with PII
raw_prompt = "Contact John Doe at john.doe@example.com or +1 (555) 123-4567 regarding the application."

# Mask PII
sanitized_text, redactions = runtime.sanitizer.sanitize(raw_prompt)
print(sanitized_text)
# Output: "Contact [NAME_REDACTED] at [EMAIL_REDACTED] or [PHONE_REDACTED] regarding the application."

# Restore PII locally
restored_text = runtime.sanitizer.restore(sanitized_text, redactions)
print(restored_text)
```

---

## 5. Running the Test Suite

WebOS.ai features 34 unit and integration tests covering the browser engine, storage, perception pruner, verifier, and model gateway:

```powershell
.\.venv\Scripts\pytest tests/ -v
```

Expected output:
```text
============================= 34 passed in 5.12s =============================
```

---

## 6. Packaging & Wheel Distribution

To package WebOS.ai as a standalone dependency wheel for downstream plugins (e.g. `JobPilot.ai` or Docker containers):

```powershell
pip wheel . -w wheels --no-deps
```
This produces `wheels/webos_ai-0.1.0-py3-none-any.whl`.

---

## 7. Prompting & Browser Automation Guide

There are three ways to initiate browser automation through prompting:

### 7.1 Chat Prompts to Antigravity (In this AI Chat)
You can directly command this AI assistant to run browser actions and inspect pages:

* **To connect and interact with an open Chrome page:**
  > *"Antigravity, connect to Chrome on port 9222 and tell me what interactive buttons are on the active tab."*

* **To run an end-to-end task on a URL:**
  > *"Antigravity, navigate to https://example.com/apply, observe the form fields, and fill out the contact inputs."*

* **To use Antigravity's interactive browser tool:**
  > Type `/browser <URL>` (e.g. `/browser https://news.ycombinator.com`) to have Antigravity browse directly with real-time feedback.

---

### 7.2 Natural Language Intent Prompts in Python Code
WebOS.ai translates high-level natural language intent prompts into physical browser actions:

```python
# 1. Inspect page elements
candidates = await runtime.observe(max_candidates=25)

# 2. Prompt runtime to ground high-level intent:
submit_target = await runtime.ground_intent("submit application", candidates)
search_target = await runtime.ground_intent("search query box", candidates)

# 3. Dispatch action with auto-verification:
if search_target:
    await runtime.execute_step(
        intent_description="Search for WebOS",
        action=BrowserAction(action_type="type", target_candidate_id=search_target.candidate_id, text_value="WebOS.ai"),
        candidate=search_target
    )
```

---

### 7.3 Multi-Provider LLM Gateway with PII Air-Gap
WebOS.ai routes prompts across local Ollama (`llama3.2:3b`), free cloud pools (Gemini/Groq), or 1-click clipboard prompts, automatically stripping PII:

```python
from webos.gateway.router import ModelRouter

# Prompt the router with automatic PII redaction and multi-key fallback:
response = await runtime.router.generate(
    system_prompt="You are a deterministic web navigation planner.",
    user_prompt=f"Given these interactive candidates: {candidates}, what is the next step to login?"
)
print(response.content)
```

