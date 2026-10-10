# WebOS.ai — System Architecture & Low-Level Design

## 1. Executive Summary

**WebOS.ai** is a decoupled, task-agnostic browser operating runtime. It combines deterministic Chrome DevTools Protocol (CDP) control, zero-token accessibility tree perception, local SQLite episodic memory, and a resilient, privacy-preserving LLM gateway.

### Core Constraints & Invariants:
* **Zero Token Waste**: Full page DOMs and raw HTML are never passed to LLMs. Deterministic CDP filtering reduces ~10,000 DOM nodes to $\le 30$ interactive candidates.
* **Local-First & Hardware Aware**: Runs comfortably on 6 GB VRAM GPUs using small local models (~3B class, e.g. Llama 3.2 3B) for micro-grounding, consuming ~2.55 GB VRAM at ~110 tok/s.
* **Privacy Air-Gap**: All PII (emails, phone numbers, exact addresses) is redacted via deterministic regex tokens before cloud dispatch and rehydrated locally before browser input.
* **Resilient Key Ring**: Groups free-tier LLM providers (Gemini Flash, Groq, OpenRouter), handles rate limits (HTTP 429) automatically, and falls back to a 1-click clipboard prompt for web ChatGPT/Claude if all keys are exhausted.
* **Real Browser Integration**: Operates inside the user's real Chrome profile via `--remote-debugging-port=9222`, preserving authentic sessions and cookies.

---

## 2. Architecture Diagram

```mermaid
flowchart TD
    App["Domain Plugin / Client (e.g., JobPilot.ai)"] --> Runtime["WebRuntime Engine (src/runtime.py)"]
    
    subgraph Browser Engine (src/browser/)
        Runtime --> CDP["CDP Client (cdp_client.py)"]
        CDP --> Perception["0-Token Perception Pruner (perception.py)"]
        CDP --> Executor["Action Executor (executor.py)"]
        CDP --> Verifier["2-Tier State Verifier (verifier.py)"]
        CDP --> HUD["Interactive HUD Overlay (hud.py)"]
        CDP --> Skills["Self-Healing Skill Engine (skills.py)"]
    end
    
    subgraph Storage Subsystem (src/storage/)
        Runtime --> DB["SQLite Manager (db.py)"]
        DB --> Episodic["Episodic Observation Log (episodic.py)"]
        DB --> Recorder["Flight Recorder & Telemetry (flight_recorder.py)"]
    end
    
    subgraph Model Gateway (src/gateway/)
        Runtime --> Router["Model Router (router.py)"]
        Router --> Sanitizer["PII Sanitizer & Air-Gap (sanitizer.py)"]
        Sanitizer --> KeyRing["Rate-Limit Key Ring (key_ring.py)"]
        KeyRing --> LocalLLM["Local 3B Grounder (Ollama / llama.cpp)"]
        KeyRing --> CloudPool["Free Cloud Pool (Gemini / Groq)"]
        KeyRing --> Clipboard["1-Click Clipboard Fallback (clipboard.py)"]
    end
```

---

## 3. Core Data Contracts (`src/types.py`)

```python
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, List
import datetime

@dataclass
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

@dataclass
class ElementCandidate:
    candidate_id: int
    backend_node_id: int
    role: str
    name: str
    value: Optional[str]
    box: BoundingBox
    is_clickable: bool = True
    is_editable: bool = False
    attributes: Dict[str, str] = field(default_factory=dict)

@dataclass
class BrowserAction:
    action_type: Literal["click", "fill", "select", "upload", "scroll", "wait"]
    target_candidate_id: Optional[int] = None
    value: Optional[str] = None
    file_path: Optional[str] = None
    selector_hint: Optional[str] = None

@dataclass
class VerificationResult:
    success: bool
    tier: Literal["tier1_deterministic", "tier2_semantic"]
    message: str
    url_changed: bool = False
    value_matches: bool = False
    network_settled: bool = True
    diff_summary: Optional[str] = None

@dataclass
class ObservationRecord:
    timestamp: datetime.datetime
    domain: str
    url: str
    field_label: str
    entered_value: str
    field_type: str
    context_tag: Optional[str] = None

@dataclass
class ModelResponse:
    content: str
    model_used: str
    tokens_prompt: int
    tokens_completion: int
    latency_ms: float
    is_fallback: bool = False
```

---

## 4. SQLite Schema (`~/.webos/runtime.db`)

```sql
CREATE TABLE IF NOT EXISTS episodic_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    domain TEXT NOT NULL,
    url TEXT NOT NULL,
    field_label TEXT NOT NULL,
    entered_value TEXT NOT NULL,
    field_type TEXT NOT NULL,
    context_tag TEXT
);

CREATE TABLE IF NOT EXISTS flight_recorder_sessions (
    session_id TEXT PRIMARY KEY,
    start_time TEXT NOT NULL,
    end_time TEXT,
    domain TEXT NOT NULL,
    status TEXT NOT NULL,
    steps_count INTEGER DEFAULT 0,
    failure_reason TEXT,
    screenshot_path TEXT
);

CREATE TABLE IF NOT EXISTS site_skills (
    skill_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    task_name TEXT NOT NULL,
    action_graph_json TEXT NOT NULL,
    success_rate REAL DEFAULT 1.0,
    last_verified TEXT NOT NULL
);
```
