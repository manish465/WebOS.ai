# WebOS.ai

> **Autonomous, Hardware-Aware Browser Operating Substrate**

WebOS.ai is a decoupled, task-agnostic browser runtime. It provides deterministic Chrome DevTools Protocol (CDP) control, zero-token accessibility tree perception, local SQLite episodic memory, and a resilient, privacy-preserving LLM gateway.

---

## Architecture Overview

```
                      Client / Domain Plugin (e.g., JobPilot.ai)
                                         │
                                         ▼
                            WebRuntime (src/runtime.py)
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
  Browser Engine                  Storage Subsystem                 Model Gateway
  • CDP Client (port 9222)        • Local SQLite (runtime.db)       • PII Air-Gap Sanitizer
  • 0-Token AXTree Pruner         • Episodic Observation Logs       • Rate-Limit Key Ring
  • Action Executor Primitives    • Flight Recorder & Telemetry     • Local 3B Grounder
  • Tier-1 & Tier-2 Verifier                                        • Free Cloud Pool (Gemini/Groq)
  • Shadow DOM HUD Overlay                                          • 1-Click Clipboard Fallback
```

---

## Quickstart

### 1. Prerequisites
* Python 3.11+
* Google Chrome (running with `--remote-debugging-port=9222`)
* Optional: Local Ollama running Llama 3.2 3B

### 2. Installation
```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -e ".[dev]"
```

### 3. Run Verification Tests
```bash
pytest -v
```
