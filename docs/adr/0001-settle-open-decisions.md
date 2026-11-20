# ADR 0001: Resolution of Open Architectural and Design Decisions

- **Status:** Accepted
- **Date:** 2026-11-19
- **Context:** `Architecture_v2.md` (Section 19) and `Design.md` (Section 15) listed several open decisions to be settled before implementation.
- **Rule IDs Affected:** `INV-6`, `INV-11`, `INV-12`, `TRUST-2`, `TRUST-7`, `DES-1`, `DES-10`, `DES-12`, `DES-13`, `SCOPE-2`.

---

## 1. Verifier Model & Provider Independence
- **Decision:** Use the same LLM provider with an independent temperature-0 falsification prompt, isolated evidence-only context, and separate config. Support an optional environment variable `VERIFIER_MODEL` for multi-provider deployments, and implement `MockFixtureLLMAdapter` for guaranteed offline deterministic demo execution (`FIX-3`).
- **Alternatives Considered:** Requiring a hard second provider (e.g., Anthropic + OpenAI) out of the box. Rejected because dual-credential setup increases hackathon build risk, rate-limit failure modes, and test fragility.
- **Consequences:** Verifier input isolation (`INV-12`) is strictly preserved in code; demo is 100% reliable offline; external credential overhead is minimized.

## 2. Dashboard Stack
- **Decision:** Build a lightweight, single-page dashboard served directly by FastAPI using Vanilla JavaScript (ES modules), native Server-Sent Events (`EventSource`), and standard CSS custom properties (`tokens.css`).
- **Alternatives Considered:** React/Next.js/Vite SPA. Rejected because npm dependencies, build steps, and hydration overhead add non-trivial moving parts and violate `DES-13` ("No extra weight").
- **Consequences:** Instant startup (`uvicorn groundtruth.api.routes:app`), zero Node.js tooling required, clean SSE streaming, sub-millisecond local latency.

## 3. Causality Graph Rendering
- **Decision:** Implement pure programmatic inline SVG with an algorithmic, layered DAG layout in vanilla JavaScript.
- **Alternatives Considered:** External graph libraries (Cytoscape.js, D3-dag, vis.js). Rejected to avoid external runtime bundles and maintain direct, pixel-level control over CSS tokens (`--gt-cobalt`, `--gt-lime`), glow filters, and the 150ms-per-hop taint cascade animation.
- **Consequences:** Zero external frontend dependencies, native CSS animation, exact compliance with `DES-1` and `DES-10`.

## 4. Numeric Thresholds & Budget Limits
- **Decision:** Adopt the proposed default values into `packs/cicd/trust.yaml`:
  - `BASE`: `human_input: 0.95`, `tool_output: 0.90`, `document: 0.70`, `agent_inference: 0.60`
  - `DOWNGRADE_CAP`: `0.30`
  - `T_cite`: `0.50`, `T_auto`: `0.60`, `decay_epsilon`: `0.01`
  - Volatile half-lives: `pod_status: 900` (15m), `log_anomaly: 21600` (6h), `commit_change: null`
  - Budget: `max_tool_calls: 20`, `max_tokens: 100000`
- **Alternatives Considered:** Lowering `T_auto` to 0.55 or raising `BASE[agent_inference]`. Rejected because the proposed values strictly satisfy `TRUST-7` (`0.50 < 0.60 <= 0.60`), ensuring `AUTO_FIX` is achievable while making verifier downgrades to 0.30 decisively trigger `ESCALATE`.
- **Consequences:** Threshold crossings during the demo (Beat 6) are crisp and mathematically predictable.

## 5. Datastore Selection
- **Decision:** Standard SQLite with Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) and busy timeout.
- **Alternatives Considered:** PostgreSQL. Rejected because SQLite requires zero external server setup, runs everywhere, and easily handles the single-process, in-memory concurrency needed for the hackathon and demo.
- **Consequences:** Preserves `INV-11` (Single datastore), instantaneous test runs, zero setup friction.

## 6. Visual Theme, Status Colors & Typography
- **Decision:**
  - Strictly enforce Dark theme (`DES-12`); pitch surface and light theme are deferred post-hackathon (`SCOPE-2`).
  - Adopt functional colors: Amber `#FFB020` for doubt/quarantine, Coral `#FF4D5E` for alert/taint (`DES-3`).
  - Typography: Inter for body/display, Instrument Serif italic for accent headline, JetBrains Mono for codes/hashes/formulas, with system fallbacks to prevent font-load flashes.
- **Consequences:** 100% adherence to WCAG AA contrast standards and palette reference guidelines.

## 7. Behavior of `FACT_SUPERSEDED` on Descendants
- **Decision:** When an existing fact is superseded and marked `RETRACTED`, it does not trigger an explicit taint cascade; its own trust becomes 0.0, which causes topological trust recomputation to drop all descendants' effective trust to 0.0 (`INV-8`), causing `/decision` to escalate to a human.
- **Consequences:** Simpler, robust deterministic behavior without unnecessary agent re-dispatch churn.
