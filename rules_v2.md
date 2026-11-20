# GROUNDTRUTH: rules.md

*Constitution for anyone, human or AI assistant, who writes code in this repository. Read it before every task. If a rule here conflicts with a request, follow the rule and say so.*

**Revision 2.1.** Aligned with `Architecture.md` revision 2.1. Changes are listed in Appendix A.

**Source documents:** `PRD` (what and why) and `Architecture.md` (how). This file turns them into enforceable rules. If this file and Architecture.md disagree, stop and ask. Do not pick one silently.

---

## 0. How to Read This File

| Word | Meaning |
|---|---|
| **MUST / MUST NOT** | Absolute. No exceptions without an approved ADR (section 14). |
| **SHOULD / SHOULD NOT** | Default. Deviating requires a one-line reason in the PR or commit message. |
| **Invariant** | A property the tests must prove. Breaking one is a bug, never a tradeoff. |

Every rule has an ID (for example `INV-3`). Cite IDs in commits, reviews, and test names.

---

## 1. Project Identity

- **What it is:** a governed shared context layer for multi-agent systems. Agents propose facts, a gate admits them, trust is computed from derivations, and a ledger makes everything replayable.
- **What it is not:** a vector database, a chat history store, a general knowledge graph, an agent framework, or a prompt-injection firewall.
- **Reference workflow:** CI/CD failure diagnosis on pre-recorded fixtures. The security-triage pack is stretch.
- **Hackathon constraint:** 36 to 48 hours. A narrow, complete system beats a broad, broken one.

---

## 2. Inviolable Invariants

These are checked by tests in `tests/invariants/`. A change that breaks one MUST NOT be merged. Every invariant has at least one test (section 7).

| ID | Invariant |
|---|---|
| **INV-1** | **Append-only ledger.** No `UPDATE` or `DELETE` on `events` or `access_log`, ever. Corrections are new events. Enforced by database triggers (Architecture section 4.1), not by convention. |
| **INV-2** | **State is derived.** The `cases`, `facts`, `fact_edges`, and `negative_checks` tables MUST be reproducible by replaying events through the pure reducer. Replay at any index MUST yield identical state. |
| **INV-3** | **One write path.** No code path writes to `cases`, `facts`, `fact_edges`, or `negative_checks` except `core/projector.py`, and only by executing operations that `core/reducer.py` derived from a ledger event. A fact enters `facts` only through a `GATE_VERDICT` event. Agents, routes, and the dashboard have no direct write access. |
| **INV-4** | **Fail closed.** Verifier timeout, malformed output, exception, or missing config MUST result in QUARANTINE, never ADMIT. |
| **INV-5** | **Identity from the token.** `agent_id` and `role` MUST come from the authenticated, case-scoped token. Any `agent_id` in a request body is ignored and logged. |
| **INV-6** | **Deterministic governance.** Trust, conflict resolution, taint propagation, budget accounting, and the AUTO_FIX/ESCALATE decision MUST be plain code. No LLM call may compute or decide them. The Verifier's strict-JSON verdict is data that plain code maps to gate verdicts and trust caps. |
| **INV-7** | **Provenance or rejection.** Every ADMITTED fact has a non-null `source`, `source_type`, and `agent_id`. An `agent_inference` with empty `derived_from` is REJECTED. |
| **INV-8** | **Trust only goes down the chain.** `effective_trust = min(own_trust, min(parents' effective_trust))`. No code may raise a child above its weakest parent. |
| **INV-9** | **Taint is sticky.** A TAINTED fact returns to ACTIVE only through a `HUMAN_OVERRIDE` event or a superseding fact. Never automatically. |
| **INV-10** | **Isolation.** A token for case A MUST fail on case B. A role MUST NOT read or write fact types outside its contract. |
| **INV-11** | **One datastore.** SQLite (demo) or Postgres. No additional database, queue, or cache service without an ADR. In-process memory, such as the Verifier cache, is not a datastore. |
| **INV-12** | **The Verifier never sees the proposer's reasoning.** Its input is the claim plus raw evidence content only. |

---

## 3. Domain Rules

### 3.1 Gate verdicts

| Rule | Detail |
|---|---|
| **GATE-1** | REJECT is for structural failure: schema, contract, provenance, missing evidence, derivation cycle. |
| **GATE-2** | QUARANTINE is for substantive doubt: unresolved contradiction, an incoming fact that loses a resolved conflict, Verifier REFUTED or INSUFFICIENT, Verifier unavailable. |
| **GATE-3** | ADMIT requires every earlier step to pass and the Verifier to return SUPPORTED. |
| **GATE-4** | Every verdict is a ledger event with a human-readable `reason`. A verdict without a reason MUST NOT be emitted. |
| **GATE-5** | Order of checks is fixed: schema, contract, provenance (including evidence presence), contradiction, Verifier. Cheap deterministic checks run before any LLM call. |
| **GATE-6** | An incoming fact that loses a resolved conflict is QUARANTINED with reason `lost_conflict:<rule>`. `FACT_SUPERSEDED` is emitted for the loser only when the incoming fact is finally ADMITTED. |
| **GATE-7** | The gate sets `is_conclusion` in the `GATE_VERDICT` payload from the pack's `conclusion_type`. The reducer reads the flag and never reads pack config. |
| **REVERIFY-1** | Re-verification of an admitted fact happens only through `POST /reverify`. An overturning result is recorded as `FACT_DOWNGRADED`. In the demo it is a scripted fixture step. |

### 3.2 Trust

| Rule | Detail |
|---|---|
| **TRUST-1** | Starting trust comes from `BASE[source_type]` in the domain pack. Self-reported confidence MAY cap it and MUST NOT raise it. |
| **TRUST-2** | Trust values and thresholds (`T_cite`, `T_auto`), `decay_epsilon`, and the case budget live in the domain pack config, never as literals in core code. |
| **TRUST-3** | No agent may cite or derive from a fact whose effective trust is below `T_cite`, or whose status is not ACTIVE. |
| **TRUST-4** | Recompute in topological order. Emit `TRUST_RECOMPUTED` for each change, with either the `cause_event` (status or ancestor change) or `as_of` (decay tick). |
| **TRUST-5** | The trust formula and its inputs MUST be displayed in the dashboard. No hidden numbers. |
| **TRUST-6** | TAINTED and RETRACTED facts have own trust 0. Decay uses an injected `now`, and the result is recorded as `TRUST_RECOMPUTED` so replay never recomputes it. |
| **TRUST-7** | The pack loader MUST reject a pack unless `T_cite < T_auto <= BASE[agent_inference]`. Otherwise AUTO_FIX is unreachable. |
| **TRUST-8** | Decay ticks run before `/decision`, `/read`, `/graph`, and current-state `/state`, using the injected clock. They never run for `/state?at=N` or on a CLOSED case. A tick emits `TRUST_RECOMPUTED` only when a value changes by at least `decay_epsilon` or crosses `T_cite` or `T_auto`. |

### 3.3 Negative knowledge

| Rule | Detail |
|---|---|
| **NEG-1** | A negative fact MUST record `check_type`, `scope` (the exact entities checked), and a time window. `window_start` and `window_end` are NOT NULL in the schema. `expires_at` may be NULL, meaning no expiry. |
| **NEG-2** | Suppression applies only if type matches, requested scope is a subset of recorded scope, the window covers the request, the record has not expired, and the backing fact is ACTIVE at or above `T_cite`. |
| **NEG-3** | If any condition fails, return `NOT_COVERED` with the failing condition. Never answer "probably covered". |

### 3.4 Conflicts

| Rule | Detail |
|---|---|
| **CONF-1** | Resolution order is fixed: source authority, evidence specificity, recency (time-sensitive types only), else unresolved. |
| **CONF-2** | Unresolved conflicts set both facts CONTESTED and emit `CONFLICT_RAISED`. The decision endpoint then returns ESCALATE. |
| **CONF-3** | The LLM never adjudicates a conflict. |

### 3.5 Decision rule

`/decision` is computed by `core/decision.py` and returns one of three signals, evaluated in this order:

1. `ESCALATE` if the case budget is exhausted or any fact in the case is CONTESTED (CONF-2).
2. `NEED_MORE` if there is no conclusion, the rework queue is non-empty, or a check listed for the fixture in `checks.yaml` has not been recorded. The response lists what is missing.
3. With a conclusion present, `ESCALATE` if the conclusion is not ACTIVE, any ancestor is CONTESTED or TAINTED, or effective trust is below `T_auto`. Otherwise `AUTO_FIX`.

The conclusion is `cases.conclusion_fact_id` (CASE-1). The rework queue is that fact when its status is TAINTED, otherwise empty. A new admitted conclusion moves the pointer, which removes the old one from the queue.

The orchestrator MUST read this from `/decision` and MUST NOT re-derive it.

### 3.6 Cases, conclusion, and budget

| Rule | Detail |
|---|---|
| **CASE-1** | The conclusion pointer is set only by the reducer, on an ADMIT `GATE_VERDICT` whose `is_conclusion` is true. QUARANTINED facts never become the conclusion. |
| **CASE-2** | Case state changes are `CASE_STATE_CHANGED` events, requested through `/transition` by an orchestrator or human token. `concluded_at` is set from the event timestamp when the new state is CONCLUDED. |
| **CASE-3** | A CLOSED case's ledger is frozen. No event is appended to it. Attempts go to `access_log`. |
| **CASE-4** | Budget limits come from the pack. Usage is derived from `AGENT_ACTION` events, never stored separately. When a limit is reached, agent endpoints return `BUDGET_EXHAUSTED` and `/decision` returns ESCALATE. |
| **CASE-5** | The pack loader MUST reject a pack whose `conclusion_type` is missing, unknown to the schema, or not writable by any role. |

---

## 4. Code Standards

| Area | Rule |
|---|---|
| **Language** | Python 3.11+. Type hints on every function signature. |
| **Validation** | Pydantic models at every boundary (API in, API out, LLM output). |
| **Formatting and lint** | `ruff format` and `ruff check` clean. `mypy --strict` clean on `core/`. |
| **Purity** | `core/reducer.py` and `core/trust.py` MUST be pure: no I/O, no clock, no randomness, no network, no globals. SQL writes are confined: `projector.py` writes the projection tables, `ledger.py` writes `events` and `access_log`, and `pack.py` and `auth.py` write the config tables (`contracts`, `agent_tokens`) when a case opens. Other `core/` modules may read through the connection they are handed and never write. |
| **Time and IDs** | Time and ID generation are injected (`clock`, `id_gen`). Never call `datetime.now()` or `uuid4()` inside `core/`. |
| **Canonical JSON** | One function (`canonical_json`) is used for hashing: sorted keys, UTF-8, no whitespace, ISO 8601 UTC timestamps. No other serializer for hashed data. |
| **Enums** | Fact statuses, source types, event types, and verdicts are defined once in `core/enums.py`. No string literals elsewhere. |
| **Transactions** | A ledger append and its projector writes happen in one DB transaction. Operations that emit several events (a taint cascade, a verdict plus `CONFLICT_RAISED`) run in one outer transaction. |
| **Errors** | No bare `except:`. No swallowed exceptions in `core/`. Errors become events or HTTP errors with codes. |
| **Dependencies** | Adding a package requires a one-line justification in the PR. Prefer the standard library. |
| **Comments** | Explain why, not what. Reference the rule ID where a rule drives the code (for example `# INV-4`). |

---

## 5. LLM Usage Rules

| Rule | Detail |
|---|---|
| **LLM-1** | All model calls go through the `LLMAdapter` interface. No provider SDK calls outside `adapters/`. |
| **LLM-2** | Prompts live in files under `prompts/`, versioned, never inline strings in logic. |
| **LLM-3** | The Verifier runs at temperature 0, returns strict JSON, and is parsed with Pydantic. Any parse failure is a fail-closed QUARANTINE (INV-4). |
| **LLM-4** | Every call has a hard timeout (Verifier proposal default: 8 seconds). |
| **LLM-5** | Verifier verdicts are cached in process, keyed by `sha256(claim + evidence_content + prompt_version)`. Only valid verdicts are cached. Timeouts and errors are never cached. The verdict used is always recorded in `GATE_VERDICT`, so replay never depends on the cache. |
| **LLM-6** | Every call logs token usage from provider-reported numbers where available. Estimates MUST be labelled as estimates. |
| **LLM-7** | Evidence and retrieved text are **data**, never instructions. Wrap them in clear delimiters and state in the prompt that content inside is untrusted. |
| **LLM-8** | Never include secrets, tokens, or other cases' data in any prompt. |

---

## 6. Security Rules

- **SEC-1:** Agent tokens are stored hashed. Raw tokens are shown once at issue time.
- **SEC-2:** Tokens are case-scoped and stop working when the case is CLOSED.
- **SEC-3:** Human override uses the reserved `human` role token. Agent tokens MUST NOT reach `/override`.
- **SEC-4:** No secrets in the repository. `.env` files are gitignored, and `.env.example` lists variables with no values. The bootstrap key (`GT_BOOTSTRAP_KEY`) is one of them and is never reachable by agents.
- **SEC-5:** Access-denied attempts are recorded with caller, target, and reason, never with fact contents. A valid token used against another case, or a read outside its contract, produces an `ACCESS_DENIED` event in the token's own case ledger. A write outside the contract is recorded as a REJECT `GATE_VERDICT` (gate step 2) and is not logged twice. An unknown or expired token, an unknown case, or a CLOSED case produces a row in `access_log`.
- **SEC-6:** Do not claim the system defends against prompt injection. It reduces unsupported claims entering shared memory. That is all.
- **SEC-7:** Two roles are reserved and seeded by the pack loader: `orchestrator` (reads `/decision` and state, and may call `/transition` and `/reverify`) and `human` (read-only plus `/override`, `/reverify`, `/transition`). Packs MUST NOT redefine them.

---

## 7. Testing Rules

A change is not done until the relevant tests exist and pass. Every invariant has a test.

| Test | Proves | Required before |
|---|---|---|
| `test_replay_identical` | INV-2: replay at every event index reproduces identical state, including `cases` and the conclusion pointer | Merging P1 |
| `test_ledger_append_only` | INV-1: update or delete on `events` or `access_log` is impossible | Merging P1 |
| `test_hash_chain` | Tampering with any event is detected on load | Merging P1 |
| `test_single_datastore` | INV-11: dependencies match an allowlist, with no Redis, graph DB, queue, or second database driver, and one database URL in config | Merging P1 |
| `test_no_direct_fact_write` | INV-3: SQL writes to projection tables appear only in `projector.py`, and `agents/`, `dashboard/`, and `adapters/` do not import it | Merging P2 |
| `test_fail_closed` | INV-4: Verifier timeout, bad JSON, and exception all yield QUARANTINE | Merging P2 |
| `test_provenance_reject` | INV-7 | Merging P2 |
| `test_identity_from_token` | INV-5 | Merging P2 |
| `test_access_denied_logged` | SEC-5: cross-case, out-of-contract read, unknown-token, and CLOSED-case attempts land in the right place, with no fact contents | Merging P2 |
| `test_verifier_input_isolation` | INV-12: the Verifier prompt for an inference contains the claim and ancestors' raw evidence, and contains none of the proposer's reasoning or the ancestors' `value` text (checked with sentinel strings) | Merging P2 |
| `test_contract_isolation` | INV-10: cross-case and out-of-contract reads and writes are denied | Merging P3 |
| `test_conclusion_pointer` | CASE-1: only an ADMIT with `is_conclusion` sets the pointer, QUARANTINE never does, and replay reproduces it | Merging P3 |
| `test_trust_min_chain` | INV-8: child never exceeds weakest parent, including after recompute | Merging P4 |
| `test_pack_validation` | TRUST-7 and CASE-5: a pack with `T_auto` above the inference base, or a bad `conclusion_type`, is rejected | Merging P4 |
| `test_decay_replay` | TRUST-6, TRUST-8, and INV-2: recorded decay results replay identically, `trust.py` takes `now` as an argument, and ticks respect `decay_epsilon` | Merging P4 |
| `test_decision_rule` | Section 3.5 truth table, including NEED_MORE, the rework queue, and the budget and CONTESTED cases | Merging P4 |
| `test_budget_exhausted` | CASE-4: usage derived from `AGENT_ACTION` events, `BUDGET_EXHAUSTED` returned, `/decision` returns ESCALATE | Merging P4 |
| `test_governance_no_llm` | INV-6: `trust`, `taint`, `conflict`, `negative`, `decision`, and `budget` modules that exist at that phase import neither `adapters/` nor any provider SDK, and a full decision runs with the adapter unavailable | Merging P4 |
| `test_negative_scope` | NEG-1 to NEG-3: wider scope, later window, and expiry all return NOT_COVERED, and a missing window is rejected | Merging P5 |
| `test_taint_cascade` | INV-9 and taint reaches all descendants and invalidates conclusions | Merging P8 |

- Tests MUST NOT call a live LLM. Use recorded responses (fixtures) via the adapter.
- A bug fix MUST add a failing test first.
- `core/` coverage target: 90% lines. Report the real number.

---

## 8. Dashboard Rules

- **DASH-1:** The dashboard is read-only. The only mutation it may trigger is `/override`, with a human token.
- **DASH-2:** Rejected and quarantined writes MUST be shown prominently. They are a feature, not an error.
- **DASH-3:** Every displayed fact shows source type, trust, status, and provenance.
- **DASH-4:** Counters compare the baseline run and the GroundTruth run on the same fixture, with the sample size shown.
- **DASH-5:** The replay view reads recorded events. It never re-invokes agents.

---

## 9. Fixtures and Demo Rules

- **FIX-1:** Fixtures are recorded real logs with hand-written ground-truth causes, stored under `packs/cicd/fixtures/`.
- **FIX-2:** Say plainly in the demo: fixtures are recorded, the reasoning is live.
- **FIX-3:** The demo run MUST work with no network access to anything but the LLM provider. Provide a recorded-response mode for the Verifier and agents as a fallback.
- **FIX-4:** Fixture-specific logic is forbidden in `core/`. It belongs in the domain pack.
- **FIX-5:** The baseline uses the same agents, model, fixtures, and tools. It MUST NOT be weakened to look worse. Report what it actually produced.
- **FIX-6:** Demo and evaluation runs use an injected fixture clock derived from fixture timestamps, not the wall clock. Wall-clock decay is for live mode only. Otherwise a volatile fact can fall below `T_cite` mid-demo.

---

## 10. Claims and Pitch Rules

| Rule | Detail |
|---|---|
| **CLAIM-1** | Do not write "novel", "first", "nobody does this", or "unique" in code, docs, slides, or README. Related work exists (agent taint tracking, provenance-capped memory, append-only provenance logs). Say: "we apply and compose established ideas and measure the result." |
| **CLAIM-2** | Metrics shown anywhere MUST be measured values from a recorded run. Targets are goals, not results. Never hard-code a number into a slide or UI. |
| **CLAIM-3** | Always show sample size and baseline definition next to any improvement figure. |
| **CLAIM-4** | The Verifier is a model. Never describe it as ground truth or as a guarantee. |
| **CLAIM-5** | Never claim to replace LangGraph, a vector DB, or any existing tool. The layer adds policy on top of persistence. |

---

## 11. Scope and Cut Rules

Follow the PRD build plan. When behind, cut in this order:

1. Second domain pack (security triage)
2. Salience routing (N4)
3. Third agent (cut to two)
4. Replay scrubber (reduce to a step list)

**Never cut:** ledger (including the hash chain), gate, token identity and isolation, trust algebra, dashboard, demo hardening. Contamination quarantine (N5, P8) starts only once the trust algebra (P4) is solid. Negative knowledge (P5) is cheap, so protect it (PRD).

- **SCOPE-1:** Do not start a phase while an earlier non-cuttable phase has failing tests.
- **SCOPE-2:** No new feature that is not in the PRD or Architecture.md without a one-line approval from the team lead recorded in the PR.
- **SCOPE-3:** If a feature will not be finished, cut it cleanly. Half-built code behind a flag is worse than no code.

---

## 12. Rules for AI Coding Assistants

You are a contributor, not an owner. Follow these on every task.

**Before writing code**
1. Read this file, then the relevant section of `Architecture.md`.
2. State which rule IDs and files the task touches.
3. If the task is ambiguous or conflicts with a rule, ask one specific question before coding.

**While writing code**
4. Make the smallest change that completes the task. Do not refactor unrelated code.
5. Never invent API endpoints, table columns, fact types, or config keys. If it is not in Architecture.md, propose it and wait.
6. Never add a dependency, datastore, or service without stating it and getting approval (INV-11, section 4).
7. Never weaken a test, skip a test, or change an assertion to make code pass. If a test is wrong, say why and propose the fix separately.
8. Never put governance logic (trust, conflicts, taint, budget, decision) behind an LLM call (INV-6).
9. Never bypass the gate, even for "test data" or "quick demos". Use the fixture loader, which goes through the gate.
10. Never hard-code a metric, trust value, threshold, or budget outside the domain pack config.
11. Never write to a projection table outside `core/projector.py` (INV-3).

**After writing code**
12. Run lint, type check, and the relevant tests. Report the actual output.
13. If something could not be verified (for example, no network or no model access), say so. Do not claim it works.
14. List any rule you had to deviate from and why.

**Stop and ask when**
- Two documents disagree.
- A rule would have to be broken to finish the task.
- The task needs a secret, a credential, or a paid service.
- You are unsure whether a change touches an invariant.

---

## 13. Git and Review

- **Branches:** `feat/<phase>-<short-name>`, for example `feat/p2-write-gate`.
- **Commits:** imperative mood, with rule IDs where relevant, for example `Fail closed on verifier timeout (INV-4)`.
- **Pull requests** need: what changed, rule IDs touched, tests added, and output of lint, types, and tests.
- **Review checklist:** every invariant test still passes, no new literals for thresholds, no new datastore, no unmeasured claims, no direct writes to projection tables.
- **Main branch** MUST always run the demo. Broken work stays on branches.

**Definition of done (any task):** code merged, tests for the touched rules pass, lint and types clean, docs updated if behavior changed, and the demo path still runs.

---

## 14. Change Control (ADR)

An ADR (Architecture Decision Record) is required to:
- add a datastore, queue, or external service,
- change an invariant, verdict meaning, or the decision rule,
- change the ledger or hash format,
- swap the LLM provider or add a second one,
- add a fact type to the core (domain-pack types do not need an ADR),
- change any entry in Architecture.md section 19 "Decided".

**ADR format** (`docs/adr/NNNN-title.md`): context, decision, alternatives considered, consequences, and the rule IDs affected. Keep it to one page. Status is Proposed, Accepted, or Superseded.

---

## 15. Quick Reference

| Question | Answer |
|---|---|
| Can an agent write a fact directly? | No. It proposes through the gate (INV-3). |
| Who writes the projection tables? | Only `core/projector.py`, running reducer ops (INV-3). |
| What if the Verifier times out? | QUARANTINE (INV-4). |
| Who decides auto-fix versus escalate? | `/decision`, plain code (INV-6, 3.5). |
| What is "the conclusion"? | `cases.conclusion_fact_id`, set on an admitted `is_conclusion` fact (CASE-1). |
| Can trust rise along a chain? | No (INV-8). |
| Can a tainted fact recover by itself? | No (INV-9). |
| Where do thresholds and budgets live? | The domain pack config (TRUST-2). |
| Where do denied accesses go? | `ACCESS_DENIED` event in the token's case, else `access_log` (SEC-5). |
| What if an incoming fact loses a conflict? | QUARANTINE, `lost_conflict:<rule>` (GATE-6). |
| Which clock does the demo use? | The fixture clock (FIX-6). |
| Can I say "novel"? | No (CLAIM-1). |
| Can I add Redis or a graph DB? | Not without an ADR (INV-11). |

---

## Appendix A. Change Log (revisions 2 and 2.1)

| ID | Change |
|---|---|
| C1 | SEC-5 now says where denials are recorded. INV-1 covers `access_log`. SEC-7 reserves roles. |
| C2 | INV-3 names `projector.py` as the single write path. INV-2 includes `cases`. Section 4 allows SQL in `projector.py` and `ledger.py` only. |
| C3 | NEG-1 makes the window mandatory, with `expires_at` as the only nullable field. |
| C4 | TRUST-4 allows `cause_event` or `as_of`. Added TRUST-8 for decay ticks. |
| C5 | Added CASE-1 to CASE-5, GATE-7, and the clarified decision rule (3.5). |
| C6 | Test table lists every required test per phase. Never-cut list now includes the hash chain and token identity. |
| C7 | Added tests for INV-6, INV-11, and INV-12. Every invariant now has a test. |
| C8 | LLM-5 specifies an in-process cache. TRUST-2 covers the budget. CASE-4 defines budget accounting. |
| D1 | Added GATE-6, REVERIFY-1, FIX-6, and the ADR rule for "Decided" items. |
| F1 | Purity row no longer says only two modules may touch SQL. Read-side modules read, and writes are confined by table. |
| F2 | INV-3 says "no direct write access", since routes append events through `core/` services. The INV-3 test checks `agents/`, `dashboard/`, and `adapters/`. |
| F3 | TRUST-8 excludes `/state?at=N` and CLOSED cases. |
| F4 | SEC-5 and the access-denied test separate out-of-contract reads (`ACCESS_DENIED`) from out-of-contract writes (REJECT verdict). SEC-7 lets the orchestrator call `/reverify`. |
| F5 | `test_governance_no_llm` covers modules that exist at each phase. |
