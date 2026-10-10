# WebOS.ai — Incremental Milestone Roadmap

Welcome to the development roadmap for **WebOS.ai**.
This roadmap guides the step-by-step implementation of the autonomous, hardware-aware browser runtime.

---

## 🗺️ Milestones Overview

- [x] **Milestone 0: Project Scaffolding & Tooling** (Completed: 2026-10-10)
- [x] **Milestone 1: Core Domain Models & Persistent SQLite Storage** (Completed: 2026-10-10)
- [ ] **Milestone 2: Resilient Model Gateway & Privacy Air-Gap**
- [ ] **Milestone 3: Chrome CDP Engine & 0-Token Perception Pruner**
- [ ] **Milestone 4: Verification Loop, Interactive HUD & Self-Healing Skills**
- [ ] **Milestone 5: Unified WebOS.ai Runtime Engine & Verification**

---

### Milestone 0: Project Scaffolding & Tooling
* **Description**: Set up Python 3.11+ packaging, virtual environment conventions, directory structure, linters/type checks, and test runner.
* **Deliverables**:
  * `pyproject.toml` with packaging configuration and dependencies (`websockets`, `httpx`, `pydantic`, `pytest`, `pytest-asyncio`).
  * Directory layout: `src/` (`browser/`, `storage/`, `gateway/`), `tests/`.
  * Initial test harness asserting environment and dependency integrity.
* **Acceptance Criteria**:
  * `pytest` runs and passes cleanly.
  * Python environment passes import tests without dependency conflicts.
* **Verification Command**:
  ```bash
  pytest -v
  ```

---

### Milestone 1: Core Domain Models & Persistent SQLite Storage
* **Description**: Implement foundational data contracts (Action DSL, Candidate representation) and the local SQLite storage engine with episodic memory logging and flight recorder telemetry.
* **Deliverables**:
  * `src/types.py`: Dataclasses for `BoundingBox`, `ElementCandidate`, `BrowserAction`, `VerificationResult`, `ObservationRecord`.
  * `src/storage/db.py`: SQLite connection manager, thread safety / WAL mode, automatic directory initialization (`~/.webos/runtime.db`).
  * `src/storage/episodic.py`: Persistent logging and querying of past user inputs by recency, domain, and label.
  * `src/storage/flight_recorder.py`: Session trace recorder and failure telemetry.
* **Acceptance Criteria**:
  * All data models instantiate, serialize, and validate correctly.
  * SQLite database creates tables automatically.
  * Episodic memory correctly saves records and prioritizes recency/domain in retrieval queries.
* **Verification Command**:
  ```bash
  pytest tests/test_storage.py -v
  ```

---

### Milestone 2: Resilient Model Gateway & Privacy Air-Gap
* **Description**: Build the privacy-preserving model gateway that protects sensitive data, manages a free-tier cloud pool (Gemini, Groq) with rate-limit tracking, connects to local Llama 3.2 3B, and falls back to a 1-click clipboard prompt.
* **Deliverables**:
  * `src/gateway/sanitizer.py`: Regex PII redaction (email, phone, address) to `<USER_...>` tokens and local re-hydration.
  * `src/gateway/key_ring.py`: Rate-limit tracker (RPM/RPD), automatic failover on HTTP 429, and round-robin.
  * `src/gateway/providers.py`: Adapters for local model (Ollama / llama.cpp) and free-tier cloud models.
  * `src/gateway/router.py` & `src/gateway/clipboard.py`: Unified model dispatcher with 1-click clipboard fallback prompt generator.
* **Acceptance Criteria**:
  * PII is 100% scrubbed before cloud dispatch and rehydrated locally without data loss.
  * Key Ring rotates keys on rate limit and detects exhaustion cleanly.
  * Clipboard fallback generates copy-ready markdown when all keys are depleted.
* **Verification Command**:
  ```bash
  pytest tests/test_gateway.py -v
  ```

---

### Milestone 3: Chrome CDP Engine & 0-Token Perception Pruner
* **Description**: Connect to the user's real running Chrome profile via WebSocket, prune the 10,000-node DOM down to $\le 30$ interactive candidates using accessibility and box models, and execute action primitives.
* **Deliverables**:
  * `src/browser/cdp_client.py`: Asynchronous JSON-RPC WebSocket client attaching to Chrome port 9222.
  * `src/browser/perception.py`: Zero-token pruner using `Accessibility.getFullAXTree` and `DOM.getBoxModel` viewport culling.
  * `src/browser/executor.py`: Action dispatcher for `click`, `fill`, `upload`, and `scroll` using native CDP input events.
* **Acceptance Criteria**:
  * CDP client connects to active Chrome tab and executes commands.
  * Perception pipeline extracts $\le 30$ ranked interactive candidates with 0 LLM tokens in $< 100\text{ ms}$.
  * Actions (click, text typing, file upload) execute accurately at target coordinates.
* **Verification Command**:
  ```bash
  pytest tests/test_browser_mock.py -v
  ```

---

### Milestone 4: Verification Loop, Interactive HUD & Self-Healing Skills
* **Description**: Implement Tier-1 deterministic state verification, inject a shadow DOM floating HUD for Pause/Record/Resume, and create the self-healing multi-anchor skill graph engine.
* **Deliverables**:
  * `src/browser/verifier.py`: Deterministic verification checking URL diffs, DOM mutation idle, value reflection, and network quiet.
  * `src/browser/hud.py`: Floating status pill overlay in shadow DOM with Pause/Record/Resume event hooks.
  * `src/browser/skills.py`: Replayable state transition graph with anchor hierarchy (Selector $\to$ ARIA $\to$ Text $\to$ Repair).
* **Acceptance Criteria**:
  * Verifier detects successful state transitions and catches failures deterministically without model evaluation.
  * HUD injects cleanly and captures user clicks/inputs during Pause mode.
  * Skill graph successfully re-identifies moved elements via secondary anchors.
* **Verification Command**:
  ```bash
  pytest tests/test_verifier_and_skills.py -v
  ```

---

### Milestone 5: Unified WebOS.ai Runtime Engine & Verification
* **Description**: Assemble all components into the high-level `WebRuntime` master class, build end-to-end integration tests, and provide a clean public API for domain plugins like `JobPilot.ai`.
* **Deliverables**:
  * `src/runtime.py`: Master `WebRuntime` class orchestrating Browser, Storage, and Model Gateway.
  * `src/__init__.py`: Clean public library exports.
  * `examples/demo_run.py`: End-to-end runnable demonstration script against a live browser form.
  * `README.md`: Quickstart guide, architecture summary, and API reference.
* **Acceptance Criteria**:
  * External scripts can control the browser, log to episodic memory, and verify actions through the high-level `WebRuntime` API.
  * Full test suite passes end-to-end with zero regressions.
* **Verification Command**:
  ```bash
  pytest tests/ -v
  ```
