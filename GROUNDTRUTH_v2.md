# GROUNDTRUTH

*The shared brain that agents can actually trust.*

**Product Requirements Document · Hackathon Edition · Draft for build · Revised November 2026**

|  |  |
| --- | --- |
| **Codename** | GROUNDTRUTH (GT) |
| **Scope** | 36–48 hour build, one reference workflow, demonstrable end to end |
| **Primary demo** | CI/CD pipeline failure diagnosis |
| **Secondary demo** | Security alert triage (stretch) |
| **Status** | Ready for build |

## 1. Executive Summary

Many multi-agent failures in production are not model-quality failures: **agents do not share a trustworthy understanding of reality**. Each agent re-fetches the same logs, re-derives the same facts, contradicts its peers, and produces conclusions nobody can audit.

GROUNDTRUTH is a **context layer**: one structured, governed representation of an in-flight case that every agent reads from and writes to. It is not a vector database and not a chat history. It is the **system of record for what is known, who knows it, how sure we are, and why**.

> **Core claim:** if agents share a governed context, the team becomes cheaper (fewer tool calls and tokens), no less accurate, and auditable, and we measure it against a fair baseline to test that claim.

**Positioning note.** Persistence, provenance, and memory tooling already exist (LangGraph, Mem0, Letta, Cognee and others). GROUNDTRUTH does not claim to invent those. It composes them into one governed layer with explicit admission, trust, conflict, and taint policy, and it measures the effect.

## 2. Problem Statement

### 2.1 The three failure modes

| # | Failure | What happens |
| --- | --- | --- |
| 1 | **Redundant work** | Agent B re-reads the same 40,000-line log Agent A already summarized. Cost and latency grow with agent count instead of staying flat. |
| 2 | **Conflicting reality** | Agent A blames a config change, Agent B blames a dependency bump. Neither knows the other exists, and the orchestrator picks whichever spoke last. |
| 3 | **Unauditable conclusions** | The final answer is prose with no trail. When it is wrong, nobody can tell which fact, from which source, at which step, caused the error. |

### 2.2 Why existing tooling falls short

| Approach | Gap |
| --- | --- |
| Vector DB / RAG | Retrieves similar text, not current structured state. Provenance, conflict handling, and write control are left to the application. |
| Chat history | Unstructured and unbounded. Every agent must re-parse it, and there is no attribution. |
| LangGraph checkpointer and store | Excellent persistence primitives, but mechanisms rather than policy. They do not govern admission, trust, or conflict. |
| Classic blackboard systems | Structurally closest, but typically without an explicit trust model or audit trail. |

**The gap GT fills:** governance and trust semantics on top of persistence primitives.

## 3. Goals and Non-Goals

**Goals**

1. One typed context object per case, shared by all agents.
2. Every fact is attributable: source, timestamp, agent, and verification state.
3. Unsourced or contradictory facts are prevented from entering shared memory.
4. Every decision is replayable: any past state can be reconstructed exactly.
5. Shared context is measurably better than no shared context, quantified against a fair baseline.
6. The layer stays domain-agnostic through pluggable domain packs.

**Non-goals**

- A general-purpose enterprise knowledge graph.
- Perfect prompt-injection defense (a firewall product is complementary).
- Autonomous remediation without human approval.
- Fine-tuning models.
- More than one domain pack in the hackathon build.

## 4. Personas

| Persona | Need |
| --- | --- |
| **On-call engineer / SOC analyst** | Tell me what is happening, why, and how sure you are, and let me verify it. |
| **Agent developer** | Give me a stable contract so I can write an agent without knowing what other agents exist. |
| **Engineering manager / auditor** | Show me the decision trail. If this was wrong, show me where. |
| **The orchestrator (system)** | Give me a routing signal based on what is known and what is still missing. |

## 5. Core Concepts

| Term | Definition |
| --- | --- |
| **Case** | One investigation instance (a CI failure, a security alert). The scoped unit of context. |
| **Fact** | An atomic, typed assertion about the case. The unit of context. |
| **Provenance** | The source, agent, timestamp, and derivation chain behind a fact. |
| **Trust score** | A computed trust on a fact, bounded by its weakest supporting ancestor. |
| **Write Gate** | The admission checkpoint every fact must pass before entering shared memory. |
| **Context Contract** | The typed schema defining what an agent role may read and must write. |
| **Negative knowledge** | A recorded absence: we checked X and found nothing. Prevents re-checking. |
| **Domain pack** | A pluggable bundle (schema, tools, fixtures) for one problem domain. |

## 6. System Architecture

```
          ORCHESTRATOR  (routes by what is known / missing)
                 |
          AGENT WORKERS  (LogAgent, RepoAgent, IntelAgent)
                 |  read / propose-write
  +--------------v-----------------------------------+
  |              GROUNDTRUTH LAYER                    |
  |  WRITE GATE -> TRUST ALGEBRA -> CONTEXT STORE     |
  |        \            |              /              |
  |      APPEND-ONLY EVENT LEDGER (replay)            |
  |   CAUSALITY GRAPH        SALIENCE / BUDGET ROUTER |
  +---------------------------------------------------+
```

| Layer | Responsibility |
| --- | --- |
| **Ingress** | Agents propose facts. They never write directly. |
| **Admission** | The Write Gate validates schema, requires provenance, and runs adversarial verification. |
| **Scoring** | The trust algebra computes bounded trust. |
| **Storage** | The context store holds current state. The ledger holds immutable history. |
| **Egress** | Agents read a filtered projection of context, never the whole store. |

The orchestrator routes on context state. It does not hold state.

## 7. Functional Requirements

Priority: **P0** must ship for the demo · **P1** strong differentiator · **P2** stretch.

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-1 | **Case lifecycle.** Create a case from a domain pack and trigger payload. States: OPEN, INVESTIGATING, CONCLUDED, CLOSED. All agents operate inside exactly one case. | P0 |
| FR-2 | **Typed fact model.** Every fact conforms to the domain pack schema (see section 9). An inference with no `derived_from` is rejected outright. | P0 |
| FR-3 | **Write Gate.** Schema validation, contract check, provenance check, contradiction check, Verifier pass, then a verdict of ADMIT, QUARANTINE, or REJECT with a logged reason. Rejections are shown on the dashboard as a feature, not an error path. | P0 |
| FR-4 | **Trust algebra.** Effective trust is the minimum of a fact's own trust and the trust of everything it derives from, recomputed transitively. Volatile fact types decay with age. Agents may not cite facts below the pack's threshold. | P0 |
| FR-5 | **Contracts and projections.** Each role declares `reads`, `writes`, and `max_context_tokens`. Reads return a ranked, budgeted projection. Writes outside the contract are rejected at the gate. | P0 |
| FR-6 | **Ledger and replay.** Every proposal, verdict, trust recomputation, and action is an immutable event. Context at any event index can be reconstructed and stepped through. | P0 |
| FR-7 | **Causality graph.** Facts and derivations form a DAG with multi-hop traversal, used to walk from symptom back to the weakest or earliest contributing fact. | P1 |
| FR-8 | **Conflict resolution.** Compare source authority, then evidence specificity, then recency for time-sensitive types. If unresolved, mark both CONTESTED and surface to a human. The LLM never adjudicates its own conflicts. | P1 |
| FR-9 | **Audit dashboard.** Live fact set with provenance chips and trust, verdict stream, weakest-link visualization, replay scrubber, token / tool-call counters, and a conclusion view with its full provenance chain and an explicit "what we could not determine" list (missing checks, contested facts). | P0 |
| FR-10 | **Domain pack interface.** A pack supplies schema, tool adapters, fixture loader, trust thresholds, and verification heuristics. | P1 |

## 8. Differentiators

| # | Feature | What it does | Demo moment | Build risk |
| --- | --- | --- | --- | --- |
| **N1** | **Trust algebra** | Trust is computed, transitive, and bounded. A conclusion resting on one shaky inference inherits that shakiness. | Verifier downgrades one early fact, trust collapses down the chain, and the recommendation flips from auto-remediate to escalate. | Low |
| **N2** | **Write Gate with adversarial Verifier** | Agents propose. An independent Verifier with a different prompt and tools tries to falsify the claim before admission. | A plausible but wrong inference arrives, gets challenged, and is quarantined with the reason on screen. | Low |
| **N3** | **Negative knowledge registry** | Absences are first-class facts: LogAgent checked 12 pods for OOMKilled and found none. | A second agent's tool-call counter stays at zero for a whole branch. | Low |
| **N4** | **Salience routing and budgeting** | Facts are scored against the agent's goal, ranked, and truncated to its token budget. Start with recency × type relevance × trust. | Side-by-side token counters with and without routing. | Medium |
| **N5** | **Contamination quarantine** | When a fact is overturned, everything downstream is tainted and its conclusions are invalidated and re-queued. | Overturn one fact and watch three conclusions turn red and one agent get re-dispatched. | Medium |
| **N6** | **Case similarity** (stretch) | Compare the current fact graph to closed cases to surface similar incidents. | This looks like incident 47. | High |

**Recommended core for the demo: N1, N2, N3, N5.** N1 and N5 share the same traversal code. N2 provides the system-says-no moment. N3 provides the cost-savings number.

**On novelty.** These mechanisms (taint tracking, write gates, lineage) are established ideas in security and data engineering. The contribution is applying them as a governed layer for agent memory and measuring the result. Pitch it as a composition that we built and benchmarked, not as a first.

## 9. Trust Model and Data Model

### 9.1 How trust is computed

Self-reported LLM confidence is not evidence. GT therefore derives starting trust from rules that can be shown on screen:

| Input | Rule |
| --- | --- |
| **Base trust by source type** | `human_input` > `tool_output` > `document` > `agent_inference`, with explicit values defined in the domain pack. The same order drives conflict resolution (FR-8). |
| **Verification state** | Only facts the Verifier marks SUPPORTED are admitted, so admission needs no trust boost. A later Verifier downgrade caps a fact's own trust at a pack-defined value below the citation threshold. |
| **Self-reported confidence** | Recorded for transparency, used only as a cap, never as a boost. |
| **Effective trust** | `min(own trust, min(effective trust of every derived_from fact))`, recomputed transitively. TAINTED and RETRACTED facts count as zero. |
| **Decay** | Volatile fact types lose trust with age at a rate configured per type. |

The formula and its inputs are displayed in the dashboard. No magic numbers.

### 9.2 Fact

| Field | Required | Purpose |
| --- | --- | --- |
| `fact_id` | Yes | Stable identity |
| `case_id` | Yes | Case scope |
| `type` | Yes | Domain-typed, e.g. `log_anomaly`, `commit_change`, `intel_match` |
| `value` | Yes | The payload |
| `source` | Yes | Tool call, document, or agent derivation |
| `source_type` | Yes | `tool_output`, `document`, `agent_inference`, `human_input` |
| `agent_id` | Yes | Who proposed it |
| `timestamp` | Yes | When (stored as `created_at`) |
| `self_confidence` | Yes | 0.0 to 1.0, self-reported |
| `derived_from` | Conditional | Supporting fact IDs (mandatory for inferences) |
| `evidence_ref` | Conditional | Raw artifact pointer: log line, diff hunk, URL |
| `effective_trust` | Computed | Output of the trust algebra |
| `status` | Computed | ACTIVE, CONTESTED, QUARANTINED, RETRACTED, TAINTED |

### 9.3 Other entities

| Entity | Fields |
| --- | --- |
| **Event** (immutable ledger) | `event_id`, `case_id`, `seq`, `event_type`, `actor`, `payload`, `prev_hash`, `hash`, `ts` |
| **Event types** | `CASE_OPENED`, `CASE_STATE_CHANGED`, `FACT_PROPOSED`, `GATE_VERDICT`, `TRUST_RECOMPUTED`, `FACT_DOWNGRADED`, `FACT_SUPERSEDED`, `FACT_TAINTED`, `CONFLICT_RAISED`, `AGENT_ACTION`, `HUMAN_OVERRIDE`, `ACCESS_DENIED` |
| **AgentContract** | `role`, `reads[]`, `writes[]`, `max_context_tokens`, `min_trust_threshold` |
| **Case** | `case_id`, `domain_pack`, `trigger`, `state`, `opened_at`, `concluded_at`, `conclusion_fact_id` |

**Invariant:** the ledger is append-only. Current state is a derived projection of the ledger, which makes replay free.

## 10. Agent Integration Contract

An agent author needs to know five things:

1. `context.read(projection_spec)` returns a ranked, budgeted fact projection.
2. `context.propose(fact)` returns `{verdict, reason, fact_id}`.
3. `context.check_negative(check_spec)` returns `COVERED` or `NOT_COVERED` before the agent re-runs a check.
4. `context.record_negative(check_spec, evidence)` records a ruled-out hypothesis.
5. The contract the agent operates under: which fact types it may read and write.

Agents are **stateless between invocations**. All continuity lives in the layer, so any agent can be swapped out and the case survives.

## 11. Reference Workflow and Demo Script

**Workflow:** CI/CD failure diagnosis on 5 pre-recorded failure cases with hand-written ground-truth causes. Fixtures are real recorded logs; the reasoning is live.

| # | Beat (about 4 minutes total) | Shows |
| --- | --- | --- |
| 1 | A pipeline fails. The orchestrator opens a case and dispatches LogAgent, RepoAgent, and IntelAgent. | Setup |
| 2 | Facts stream onto the dashboard, each with a provenance chip and trust score. | FR-2, FR-9 |
| 3 | RepoAgent proposes that a dependency bump caused the failure. **The gate quarantines it** because the evidence does not support the version range. | N2 |
| 4 | LogAgent records a negative fact: no OOMKilled across 12 pods. RepoAgent is later asked to re-check, and the layer tells it the answer already exists. | N3 |
| 5 | Counter comparison: same task with no context versus with GROUNDTRUTH. | Value proof |
| 6 | The Verifier downgrades one early fact. Trust collapses down the chain, two conclusions fall below the threshold and turn red, and the orchestrator flips from auto-fix to escalate. A second variant retracts the fact, which taints its descendants and re-dispatches an agent. | N1, N5 |
| 7 | Replay scrubber steps back to event 14 and shows exactly what each agent knew. | FR-6 |
| 8 | The conclusion renders with its full provenance chain and an explicit **what we could not determine** section. | FR-7 |

> *By design, every one of those agents could be replaced with a different model or vendor and the case would survive, because the understanding lives in the layer, not in the agent.*

## 12. Evaluation and Success Metrics

Results are measured live on the dashboard and reported only after they are measured.

**Benchmark design**

- **Test set:** the 5 fixtures, each with a labelled correct root cause.
- **Baseline:** a reasonable no-governance setup (agents share a plain history plus basic retrieval). Not a strawman that sends everything.
- **Controls:** same model, same fixtures, same tools in both runs.
- **Repetition:** multiple runs per fixture, with sample size reported.

| Metric | Target | Why it matters |
| --- | --- | --- |
| Redundant tool-call reduction | 40% or more vs baseline | Core cost argument |
| Token reduction | 35% or more per case | Core economics argument |
| Correct root cause | Equal or better than baseline | Proves governance does not hurt accuracy |
| Provenance coverage | 100% of admitted facts | Trust argument |
| Ungrounded writes blocked | At least 1 demonstrated | Proves the gate works |
| Contract violations leaking through | 0 in a controlled test | Proves isolation works |
| Wrong-conclusion catch | At least 1 via trust collapse | Headline moment |
| Replay fidelity | Exact reconstruction, verified | Proves auditability |

Targets are goals, not promises. If a number misses, report the real number.

## 13. Non-Functional Requirements

| Category | Requirement |
| --- | --- |
| **Determinism** | Replaying the same ledger yields byte-identical context state. |
| **Latency** | Gate verdict in 3s or less per proposal, excluding the Verifier timeout. Context read in 300ms or less. |
| **Fail-closed** | If the Verifier times out, the write is QUARANTINED, never ADMITTED. |
| **Auditability** | 100% of admitted facts carry non-null provenance. |
| **Cost control** | Per-case token and tool-call budgets enforced by the layer, not by agents. |
| **Extensibility** | A new domain pack requires zero changes to the core layer. |
| **Isolation** | No agent can read outside its case or contract. |

## 14. Hackathon Build Plan

**Cut lines are mandatory.** Ship a narrow, complete system, not a broad, broken one.

| Phase | Hours | Deliverable | Cut rule |
| --- | --- | --- | --- |
| P1 Spine | 0–8 | Fact model, ledger, case lifecycle, store | Cannot cut |
| P2 Gate | 8–14 | Schema, contract, provenance, and contradiction checks, Verifier agent, verdict logging | Cannot cut |
| P3 Agents | 12–20 | Log, Repo, Intel agents plus orchestrator on fixtures | Cut to 2 agents if behind |
| P4 Trust | 18–26 | N1 trust algebra and causality traversal | Cannot cut: the headline |
| P5 Negative knowledge | 22–28 | N3 registry and suppression | Cheap and high value, protect it |
| P6 Dashboard | 24–34 | Fact list, verdict stream, trust view, replay | Replay scrubber can shrink to a step list |
| P7 Salience | 30–36 | N4 budget router and counters | Cut second, after P10 |
| P8 Contamination | 32–40 | N5 taint propagation | Only if P4 is solid |
| P9 Demo hardening | 34–44 | Fixed fixtures, rehearsed script, benchmark baselines | Cannot cut |
| P10 Second pack | 40–46 | Security triage pack | Cut first |

**Minimum viable demo: P1 + P2 + P3 + P4 + P6 + P9.** That alone shows a governed context layer with trust propagation and a working audit trail.

## 15. Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A judge says this is just a vector DB | Fatal to the pitch | Open with the three failure modes and show a rejected write in the first 60 seconds. |
| A judge says LangGraph already does this | Weakens novelty | Concede: it gives persistence, and GT adds policy on top (admission, trust, conflict, taint). Never claim to replace it. |
| Verifier adds latency and cost | Demo drags | Cache verdicts for fixture-identical facts, verify async where allowed, hard timeout with fail-closed. |
| Trust numbers look arbitrary | Credibility loss | Derive them from stated rules and show the formula on screen. |
| Too many features, none finished | Weak demo | Enforce the cut lines. N1 + N2 + N3 finished beats all six half-built. |
| Fixtures look fake | Judge skepticism | State it openly: fixtures are recorded real logs, and the reasoning is live. |
| Orchestrator becomes a god-object | Architecture criticism | It routes on context state and holds none. Say so explicitly. |
| Overclaiming novelty | Credibility loss | Pitch it as a composition of known ideas, built and benchmarked. |

## 16. Post-Hackathon Roadmap

1. Live integrations: real GitHub Actions and a real SIEM webhook.
2. Learned salience ranking in place of heuristics.
3. Cross-case institutional memory (N6).
4. Human-in-the-loop console where analysts propose facts and override trust through the same ledger.
5. Multi-case fleet view with pattern detection.
6. Policy DSL for declarative trust thresholds and admission rules.

## Appendix A. Implementation Notes

| Layer | Suggested approach | Rationale |
| --- | --- | --- |
| Short-term state | None needed: the ledger and projection tables hold case state, and agents and the orchestrator are stateless. A graph-framework checkpointer is optional inside an agent. | One source of truth for case state |
| Facts and ledger | One relational DB (Postgres, or SQLite for a local prototype): facts table with JSON payload, append-only hash-chained ledger | One datastore, easy replay, easy dashboard joins |
| Causality graph | Traversal in Python over the facts table | Graph depth is small in a hackathon. A graph DB is a post-hackathon upgrade |
| Read path | In-process cache over the fact table (not a separate cache service) | Reads under 300ms |
| Dashboard | Simple web app over ledger projections | Speed over polish |
| Backend | Python, FastAPI, Pydantic | Fast to build and validate |

**Rule:** every extra datastore is integration time stolen from the demo.

## Appendix B. The One-Paragraph Pitch

> Many multi-agent failures aren't model failures. Agents don't share a trustworthy picture of what is happening, so they repeat each other's work, contradict each other, and produce conclusions nobody can audit. GROUNDTRUTH is the shared context layer underneath them. Every fact is typed, sourced, and admitted through an adversarial gate. Trust propagates from evidence, so a conclusion is only as strong as its weakest fact. Rule out a hypothesis once and, within the scope and window that were checked, no agent re-checks it. Overturn a fact and everything downstream is automatically invalidated. Every step is replayable, and we benchmarked the result against a fair baseline. Agents are designed to be interchangeable, because the understanding lives in the layer.
