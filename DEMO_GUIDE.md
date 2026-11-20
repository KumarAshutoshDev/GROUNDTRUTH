# GroundTruth: Complete Demo & Operations Guide

> **Governed Shared Context Layer for Autonomous Multi-Agent Teams**  
> Prevent cascading hallucinations, enforce cryptographic evidence provenance, eliminate duplicate tool queries, and halt ungrounded autonomous code execution.

---

## Table of Contents
1. [Quick Start (Run the Demo in 60 Seconds)](#1-quick-start-run-the-demo-in-60-seconds)
2. [Prerequisites & Environment Setup](#2-prerequisites--environment-setup)
3. [Seeding the Demo Database (The 8 Beats)](#3-seeding-the-demo-database-the-8-beats)
4. [Launching the Backend & Interactive Dashboard](#4-launching-the-backend--interactive-dashboard)
5. [Command Reference & Flag Breakdown](#5-command-reference--flag-breakdown)
6. [Interactive Dashboard Walkthrough (What to Show)](#6-interactive-dashboard-walkthrough-what-to-show)
7. [Running the Benchmark Evaluation Suite](#7-running-the-benchmark-evaluation-suite)
8. [Running Invariant & Unit Tests](#8-running-invariant--unit-tests)
9. [Troubleshooting & FAQ](#9-troubleshooting--faq)

---

## 1. Quick Start (Run the Demo in 60 Seconds)

If you already have the repository cloned and the virtual environment installed, run these two commands in separate terminal tabs:

### Terminal 1: Seed the Demo Incident Data
```bash
source .venv/bin/activate
python groundtruth/eval/demo_script.py --db groundtruth.db
```

### Terminal 2: Start the Web Server & Dashboard
```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn groundtruth.api.routes:app --host 127.0.0.1 --port 8000 --reload
```

Now open your web browser and navigate to:
👉 **[http://127.0.0.1:8000/dashboard/](http://127.0.0.1:8000/dashboard/)**  
*(Press `Ctrl + Shift + R` if you need to bypass browser caching).*

---

## 2. Prerequisites & Environment Setup

### 2.1 Python Environment
GroundTruth requires **Python 3.11+** (Python 3.12, 3.13, and 3.14 are supported).

```bash
# 1. Create a dedicated virtual environment
python3 -m venv .venv

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Upgrade pip and install GroundTruth in editable mode with development dependencies
pip install --upgrade pip
pip install -e ".[dev]"
```

### 2.2 LLM Provider Configuration (Optional)
GroundTruth supports **two execution modes**:
1. **Deterministic Mock / Offline Mode (Default, Zero-Cost, Instant):** Uses pre-recorded tool traces and fixtures. Does **not** require any API key or credit card.
2. **Live LLM Provider Mode (Real Groq LLaMA-3.3-70B):** Uses live Groq API inference for agent reasoning.

To run with live Groq inference:
```bash
# Get your API key from https://console.groq.com/keys
export GROQ_API_KEY="gsk_your_groq_api_key_here"
```
*(If `GROQ_API_KEY` is omitted, GroundTruth automatically falls back to offline fixture replay mode).*

---

## 3. Seeding the Demo Database (The 8 Beats)

GroundTruth includes an automated rehearsal driver (`groundtruth/eval/demo_script.py`) that runs through the **8 Canonical Demonstration Beats** of an enterprise CI/CD incident:

```bash
python groundtruth/eval/demo_script.py --db groundtruth.db
```

### What Happens During the 8 Beats:
* **Beat 1 (Incident Ingestion):** A CI/CD failure trigger (`NullPointerException` in `TokenValidator`) opens a new case in the SQLite ledger. Specialist agents (`LogAgent`, `RepoAgent`, `IntelAgent`) are dispatched under strict role contracts.
* **Beat 2 (Write Gate Admission):** Agents propose facts with raw evidence. The Write Gate validates schemas, computes base trust ($T_{\text{base}}$), and admits them to shared context.
* **Beat 3 (Hallucination Quarantine):** An agent speculates that an ungrounded `dependency_bump` broke production. The deterministic verifier **refutes** the claim and immediately **quarantines** it, preventing hallucination contagion.
* **Beat 4 (Negative Knowledge Recording):** The team rules out container memory crashes (`oom_pod_crash`). This is recorded as negative knowledge, suppressing redundant tool queries and saving **76%+ tokens**.
* **Beat 5 (Benchmark Comparison):** Measured tool calls, tokens, and duplicate queries are calculated against an ungoverned baseline ($N=15$).
* **Beat 6 (Taint Cascade):** An upstream premise (`log_anomaly`) is retracted. GroundTruth's Trust Algebra mathematically collapses downstream root cause trust to $0.00$, instantly flipping autonomous routing from `AUTO_FIX` to `ESCALATE` / `NEED_MORE`.
* **Beat 7 (Historical Replay):** The system state is replayed from the immutable event log at any historical sequence tick.
* **Beat 8 (Attributable Conclusion & Negative Knowledge):** The final report is generated, displaying the cryptographic provenance DAG and explicit *"WHAT WE COULD NOT DETERMINE"* callouts.

---

## 4. Launching the Backend & Interactive Dashboard

To start the FastAPI REST API and serve the high-tech Vanilla JS dashboard:

```bash
PYTHONPATH=. uvicorn groundtruth.api.routes:app --host 127.0.0.1 --port 8000 --reload
```

### URLs Available:
| Service | URL | Purpose |
| :--- | :--- | :--- |
| **Interactive Dashboard** | `http://127.0.0.1:8000/dashboard/` | Full multi-page web UI |
| **Interactive Swagger API Docs** | `http://127.0.0.1:8000/docs` | OpenAPI documentation |
| **Raw Cases REST Endpoint** | `http://127.0.0.1:8000/cases` | Active incident cases |
| **Live SSE Stream** | `http://127.0.0.1:8000/cases/{id}/stream` | Server-Sent Events |

---

## 5. Command Reference & Flag Breakdown

### Command 1: Starting the Web Server
```bash
PYTHONPATH=. uvicorn groundtruth.api.routes:app --host 127.0.0.1 --port 8000 --reload
```
* `PYTHONPATH=.` — Adds the current directory (`ContextOS/`) to Python's module search path so `import groundtruth...` works cleanly without packaging conflicts.
* `uvicorn` — Fast, production-grade ASGI web server for Python.
* `groundtruth.api.routes:app` — Points Uvicorn to the FastAPI application instance `app` inside `groundtruth/api/routes.py`.
* `--host 127.0.0.1` — Binds the server strictly to localhost for secure local operation.
* `--port 8000` — Specifies the HTTP port. If port 8000 is occupied, you can change this to `--port 8080`.
* `--reload` — Automatically reloads the server whenever backend Python files are saved (ideal for development).

---

### Command 2: Running the Demo Rehearsal Script
```bash
python groundtruth/eval/demo_script.py [FLAGS]
```
#### Available Flags:
* `--db <path>`  
  * **Example:** `--db groundtruth.db`  
  * **What it does:** Saves incident events and state to a persistent SQLite database file so the web dashboard can load and replay them. (Defaults to `:memory:` if omitted).
* `--offline`  
  * **What it does:** Forces deterministic offline fixture mode using pre-recorded mock tool data. Requires no network connection or API keys.
* `--live`  
  * **What it does:** Forces live LLM generation using your Groq API key (`llama-3.3-70b-versatile`).
* `--speed <seconds>`  
  * **Example:** `--speed 1.5`  
  * **What it does:** Adds an artificial pause (e.g. 1.5 seconds) between each beat, perfect for narrating live presentations while the audience watches the terminal output.

---

### Command 3: Running the Full Evaluation Benchmark ($N=15$)
```bash
python groundtruth/eval/gt_run.py
```
* **What it does:** Executes the governed GroundTruth multi-agent system across 5 diverse production incident fixtures $\times$ 3 runs each ($N=15$).
* **Output:** Measures accuracy, tool calls, duplicate calls, and token consumption, saving the results to `eval/results/gt_metrics.json`.

```bash
python groundtruth/eval/baseline_run.py
```
* **What it does:** Runs the ungoverned baseline agent system (without Write Gate or Negative Knowledge) across the same 15 fixtures for fair, apples-to-apples comparison.

```bash
python groundtruth/eval/report.py
```
* **What it does:** Aggregates and prints the final evaluation comparison table verifying GroundTruth's claims:
  * **-72.7% Tool Call Reduction**
  * **-100% Redundant/Duplicate Query Elimination**
  * **-76.3% Token Consumption Savings**

---

## 6. Interactive Dashboard Walkthrough (What to Show)

The dashboard is structured into dedicated focused pages accessible via the top navigation tabs:

```
[ 🌐 Causality Graph ]  [ ⚡ Gate Stream ]  [ 📋 Admitted Facts ]  [ 🎯 Root Cause & Decision ]  [ 📊 Benchmark Counters ]  [ 📐 Trust Formula ]  [ 🧭 All Panels ]
```

### Tab 1: 🌐 Causality Graph (`#/graph`)
* **What to Show:** An interactive SVG Directed Acyclic Graph (DAG) displaying how raw tool outputs (`commit_change`, `log_anomaly`) derive root causes.
* **The Highlight:** The **cyan glowing "Weakest Link" line** showing that a conclusion is only as strong as its weakest premise.
* **Historical Replay Scrubber:** Drag the yellow scrubber at the bottom to travel backwards in time and watch how the DAG evolved step-by-step.

### Tab 2: ⚡ Gate Stream (`#/verdicts`)
* **What to Show:** The real-time Write Gate admission log.
* **The Highlight:** Point out the **Amber `QUARANTINE` row** (`dependency_bump`). Explain: *"An agent guessed that a dependency version broke the build. The Write Gate challenged the claim, verified the lockfile, proved it false, and quarantined it—saving the team from a costly hallucination loop."*

### Tab 3: 📋 Admitted Facts (`#/facts`)
* **What to Show:** The immutable ledger of admitted context.
* **The Highlight:** Contrast `🛠 TOOL OUTPUT` (solid green 0.90 trust) with `🧠 AGENT INFERENCE` (0.60 trust).
* **Negative Knowledge:** Highlight `negative_check` showing that pod crashes were formally ruled out.

### Tab 4: 🎯 Root Cause & Decision (`#/conclusion`)
* **What to Show:** The epistemic resolution card.
* **The Highlight:** Show the **Red Danger Stripe pattern** on `cicd_root_cause` (`Trust: 0.00`). Explain **Invariant INV-9 (Taint Cascade)**: *"Because an upstream premise was retracted, downstream trust mathematically collapsed to 0.00."*
* **Autonomous Routing:** Note that autonomous execution halted safely at `NEED_MORE` instead of pushing broken code.

### Tab 5: 📊 Benchmark Counters (`#/counters`)
* **What to Show:** High-contrast Datadog-style comparison cards showing empirical performance:
  * **Tool Calls:** 3 vs 11 (-72.7%)
  * **Redundant Calls:** 0 vs 3 (-100%)
  * **Total Tokens:** 1,472 vs 6,204 (-76.3%)
* **Methodology:** Includes explicit sample size badge ($N=15$) and baseline definition.

### Tab 6: 📐 Trust Formula (`#/formula`)
* **What to Show:** The formal mathematical equations governing the context layer:
  $$\text{effective\_trust}(f) = \min\left(\text{own\_trust}(f), \min_{p \in \text{parents}} \text{effective\_trust}(p)\right)$$
* **Citation Threshold ($T_{\text{cite}} = 0.50$):** Agents cannot cite low-confidence facts.
* **Auto-Fix Threshold ($T_{\text{auto}} = 0.60$):** Autonomous fixes cannot execute unless trust exceeds 0.60.

---

## 7. Running Invariant & Unit Tests

To verify that all 119 system invariants, gate rules, and contracts pass:

```bash
# Run all 119 tests with pytest
.venv/bin/pytest groundtruth/tests/

# Run fast linter checks
.venv/bin/ruff check .

# Run strict static type checking on the core governance engine
.venv/bin/mypy --strict groundtruth/core/
```

**Expected Result:**
```
119 passed in ~5s
All checks passed!
Success: no issues found in 20 source files
```

---

## 8. Troubleshooting & FAQ

### Q: Port 8000 is already in use
**Fix:** Find the running process and terminate it, or run on port 8080:
```bash
# Find and terminate existing process on port 8000:
lsof -i :8000
kill -9 <PID>

# OR start Uvicorn on port 8080:
PYTHONPATH=. uvicorn groundtruth.api.routes:app --host 127.0.0.1 --port 8080 --reload
```

### Q: Dashboard shows blank or old cached styles
**Fix:** The dashboard uses ES modules with zero npm build step. Perform a hard refresh in your browser:
* **Linux / Windows:** `Ctrl + Shift + R` or `F5`
* **macOS:** `Cmd + Shift + R`

### Q: "sqlite3.OperationalError: no such table: cases"
**Fix:** Run the demo seed script to initialize and migrate the database schema:
```bash
python groundtruth/eval/demo_script.py --db groundtruth.db
```

### Q: Can I run this with my own Groq API key?
**Yes.** Simply export your key before running:
```bash
export GROQ_API_KEY="gsk_..."
python groundtruth/eval/demo_script.py --db groundtruth.db --live
```
GroundTruth will automatically detect your key and use `llama-3.3-70b-versatile` over Groq's high-speed inference engine.
