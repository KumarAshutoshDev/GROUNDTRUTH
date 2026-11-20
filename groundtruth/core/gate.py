"""Write Gate Pipeline: Deterministic admission, provenance checks, and verifier pass.

Enforces:
- INV-7: Provenance or rejection (non-empty derived_from for inferences, source info).
- GATE-1: REJECT for structural failures (schema, contract, provenance, cycles).
- GATE-2: QUARANTINE for substantive doubt (conflicts, Verifier refuted/insufficient).
- GATE-3: ADMIT requires all checks to pass and Verifier to return SUPPORTED.
- GATE-4: Every verdict is recorded with a logged human-readable reason.
- GATE-5: Fixed check sequence: schema -> contract -> provenance -> conflict -> verifier.
- GATE-6: Incoming fact that loses conflict is QUARANTINED with reason lost_conflict:<rule>.
- GATE-7: Sets is_conclusion flag from pack.conclusion_type.
- TRUST-3: No agent may cite a fact below T_cite or non-ACTIVE.
"""

import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from groundtruth.adapters.llm import LLMAdapter
from groundtruth.core.budget import calculate_budget_usage
from groundtruth.core.conflict import ConflictDecision, resolve_conflict
from groundtruth.core.enums import EventType, GateVerdict, SourceType
from groundtruth.core.models import FactModel
from groundtruth.core.pack import DomainPack
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.utils import IdGenerator, UUIDGenerator, canonical_json
from groundtruth.core.verifier import compute_cache_key, verify_claim


class FactProposal(BaseModel):
    """Proposal payload submitted by an agent."""

    fact_id: str | None = None
    type: str
    value: dict[str, Any]
    source: str
    source_type: str
    agent_id: str | None = None
    self_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    derived_from: list[str] = Field(default_factory=list)
    evidence_ref: str | None = None
    entity_key: str | None = None


@dataclass(frozen=True)
class GateResult:
    """Outcome of Write Gate evaluation."""

    verdict: GateVerdict
    reason: str
    fact_id: str
    own_trust: float
    effective_trust: float
    event_id: str


def has_derivation_cycle(
    child_id: str, derived_from: list[str], facts: dict[str, FactModel]
) -> bool:
    """Check if adding child_id -> derived_from introduces a cycle in the DAG."""
    visited = set()

    def visit(node_id: str) -> bool:
        if node_id == child_id:
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        parent = facts.get(node_id)
        if parent:
            for p_id in parent.derived_from:
                if visit(p_id):
                    return True
        return False

    for parent_id in derived_from:
        if visit(parent_id):
            return True
    return False


def get_raw_evidence_content(
    evidence_ref: str | None,
    derived_from: list[str],
    facts: dict[str, FactModel],
    pack: DomainPack,
) -> str:
    """Retrieve raw evidence text for verification (INV-12: raw content only)."""
    if evidence_ref:
        return f"Referenced artifact: {evidence_ref}"

    # For inferences, collect raw evidence_ref of non-inference ancestors only (INV-12)
    ancestor_refs: list[str] = []
    for pid in derived_from:
        parent = facts.get(pid)
        if parent and parent.evidence_ref:
            ancestor_refs.append(f"Ancestor evidence ({parent.type}): {parent.evidence_ref}")

    return "\n".join(ancestor_refs) if ancestor_refs else "No raw evidence references attached"


def evaluate_proposal(
    conn: sqlite3.Connection,
    case_id: str,
    caller_role: str,
    proposal: FactProposal,
    pack: DomainPack,
    verifier_adapter: LLMAdapter,
    id_gen: IdGenerator | None = None,
) -> GateResult:
    """Run proposal through the 5-step Write Gate pipeline (GATE-5)."""
    generator = id_gen or UUIDGenerator()
    fact_id = proposal.fact_id or generator.generate("fact")

    state = load_case_projection(conn, case_id)
    contract = pack.contracts.get(caller_role)

    # Check budget exhaustion (CASE-4)
    usage = calculate_budget_usage(conn, case_id, pack)
    if usage.is_exhausted:
        reason = f"budget_exhausted: {usage.exhaustion_reason}"
        evt = append_and_project(
            conn,
            case_id,
            EventType.GATE_VERDICT,
            caller_role,
            {
                "fact": {"fact_id": fact_id, "type": proposal.type},
                "verdict": GateVerdict.REJECT,
                "reason": reason,
            },
        )
        return GateResult(
            verdict=GateVerdict.REJECT,
            reason=reason,
            fact_id=fact_id,
            own_trust=0.0,
            effective_trust=0.0,
            event_id=evt.event_id,
        )

    # -------------------------------------------------------------
    # Step 1: Schema Check (GATE-1)
    # -------------------------------------------------------------
    fact_types = pack.schema_def.get("fact_types", {})
    if proposal.type not in fact_types:
        reason = f"schema_violation: unknown fact type '{proposal.type}'"
        evt = append_and_project(
            conn,
            case_id,
            EventType.GATE_VERDICT,
            caller_role,
            {
                "fact": {"fact_id": fact_id, "type": proposal.type},
                "verdict": GateVerdict.REJECT,
                "reason": reason,
            },
        )
        return GateResult(
            verdict=GateVerdict.REJECT,
            reason=reason,
            fact_id=fact_id,
            own_trust=0.0,
            effective_trust=0.0,
            event_id=evt.event_id,
        )

    # NEG-1: Mandatory scope and window for negative_check facts
    if proposal.type == "negative_check":
        neg_val = proposal.value if isinstance(proposal.value, dict) else {}
        if (
            not neg_val.get("check_type")
            or "scope" not in neg_val
            or not isinstance(neg_val.get("scope"), list)
            or not neg_val.get("window_start")
            or not neg_val.get("window_end")
        ):
            reason = (
                "schema_violation: negative_check requires 'check_type', 'scope' (list), "
                "'window_start', and 'window_end' (NEG-1)"
            )
            evt = append_and_project(
                conn,
                case_id,
                EventType.GATE_VERDICT,
                caller_role,
                {
                    "fact": {"fact_id": fact_id, "type": proposal.type},
                    "verdict": GateVerdict.REJECT,
                    "reason": reason,
                },
            )
            return GateResult(
                verdict=GateVerdict.REJECT,
                reason=reason,
                fact_id=fact_id,
                own_trust=0.0,
                effective_trust=0.0,
                event_id=evt.event_id,
            )

    # -------------------------------------------------------------
    # Step 2: Contract Check (GATE-1)
    # -------------------------------------------------------------
    if not contract or proposal.type not in contract.writes:
        reason = f"contract_violation: role '{caller_role}' cannot write '{proposal.type}'"
        evt = append_and_project(
            conn,
            case_id,
            EventType.GATE_VERDICT,
            caller_role,
            {
                "fact": {"fact_id": fact_id, "type": proposal.type},
                "verdict": GateVerdict.REJECT,
                "reason": reason,
            },
        )
        return GateResult(
            verdict=GateVerdict.REJECT,
            reason=reason,
            fact_id=fact_id,
            own_trust=0.0,
            effective_trust=0.0,
            event_id=evt.event_id,
        )

    # -------------------------------------------------------------
    # Step 3: Provenance & Evidence Checks (INV-7, GATE-1, TRUST-3)
    # -------------------------------------------------------------
    is_inference = proposal.source_type == SourceType.AGENT_INFERENCE

    if is_inference:
        # Inferences must have non-empty derived_from (INV-7)
        if not proposal.derived_from:
            reason = "provenance_violation: agent_inference requires non-empty derived_from"
            evt = append_and_project(
                conn,
                case_id,
                EventType.GATE_VERDICT,
                caller_role,
                {
                    "fact": {"fact_id": fact_id, "type": proposal.type},
                    "verdict": GateVerdict.REJECT,
                    "reason": reason,
                },
            )
            return GateResult(
                verdict=GateVerdict.REJECT,
                reason=reason,
                fact_id=fact_id,
                own_trust=0.0,
                effective_trust=0.0,
                event_id=evt.event_id,
            )

        # Check all parents exist, are ACTIVE, and have trust >= T_cite (TRUST-3)
        for parent_id in proposal.derived_from:
            parent = state.facts.get(parent_id)
            if not parent:
                reason = f"provenance_violation: derived_from parent '{parent_id}' does not exist"
                evt = append_and_project(
                    conn,
                    case_id,
                    EventType.GATE_VERDICT,
                    caller_role,
                    {
                        "fact": {"fact_id": fact_id, "type": proposal.type},
                        "verdict": GateVerdict.REJECT,
                        "reason": reason,
                    },
                )
                return GateResult(
                    verdict=GateVerdict.REJECT,
                    reason=reason,
                    fact_id=fact_id,
                    own_trust=0.0,
                    effective_trust=0.0,
                    event_id=evt.event_id,
                )

            if parent.status != "ACTIVE":
                reason = f"provenance_violation: parent '{parent_id}' status is {parent.status}"
                evt = append_and_project(
                    conn,
                    case_id,
                    EventType.GATE_VERDICT,
                    caller_role,
                    {
                        "fact": {"fact_id": fact_id, "type": proposal.type},
                        "verdict": GateVerdict.REJECT,
                        "reason": reason,
                    },
                )
                return GateResult(
                    verdict=GateVerdict.REJECT,
                    reason=reason,
                    fact_id=fact_id,
                    own_trust=0.0,
                    effective_trust=0.0,
                    event_id=evt.event_id,
                )

            if parent.effective_trust < pack.trust.T_cite:
                reason = (
                    f"provenance_violation: parent '{parent_id}' trust "
                    f"({parent.effective_trust}) below T_cite ({pack.trust.T_cite})"
                )
                evt = append_and_project(
                    conn,
                    case_id,
                    EventType.GATE_VERDICT,
                    caller_role,
                    {
                        "fact": {"fact_id": fact_id, "type": proposal.type},
                        "verdict": GateVerdict.REJECT,
                        "reason": reason,
                    },
                )
                return GateResult(
                    verdict=GateVerdict.REJECT,
                    reason=reason,
                    fact_id=fact_id,
                    own_trust=0.0,
                    effective_trust=0.0,
                    event_id=evt.event_id,
                )

        # Check derivation cycles (GATE-1)
        if has_derivation_cycle(fact_id, proposal.derived_from, state.facts):
            reason = "provenance_violation: cycle detected in derivation chain"
            evt = append_and_project(
                conn,
                case_id,
                EventType.GATE_VERDICT,
                caller_role,
                {
                    "fact": {"fact_id": fact_id, "type": proposal.type},
                    "verdict": GateVerdict.REJECT,
                    "reason": reason,
                },
            )
            return GateResult(
                verdict=GateVerdict.REJECT,
                reason=reason,
                fact_id=fact_id,
                own_trust=0.0,
                effective_trust=0.0,
                event_id=evt.event_id,
            )

    else:
        # Non-inference fact requires evidence_ref
        if not proposal.evidence_ref:
            reason = f"evidence_violation: {proposal.source_type} requires non-null evidence_ref"
            evt = append_and_project(
                conn,
                case_id,
                EventType.GATE_VERDICT,
                caller_role,
                {
                    "fact": {"fact_id": fact_id, "type": proposal.type},
                    "verdict": GateVerdict.REJECT,
                    "reason": reason,
                },
            )
            return GateResult(
                verdict=GateVerdict.REJECT,
                reason=reason,
                fact_id=fact_id,
                own_trust=0.0,
                effective_trust=0.0,
                event_id=evt.event_id,
            )

    # Calculate trust
    base_trust = pack.trust.BASE.get(proposal.source_type, 0.50)
    own_trust = min(base_trust, proposal.self_confidence)
    if is_inference:
        parent_trusts = [state.facts[p].effective_trust for p in proposal.derived_from]
        effective_trust = min([own_trust] + parent_trusts)
    else:
        effective_trust = own_trust

    is_conclusion = proposal.type == pack.conclusion_type

    # -------------------------------------------------------------
    # Step 4: Contradiction Check (CONF-1, CONF-2, GATE-6)
    # -------------------------------------------------------------
    displaced_existing_fact_id: str | None = None
    if proposal.entity_key:
        is_ts = bool(fact_types.get(proposal.type, {}).get("time_sensitive", False))
        for existing in state.facts.values():
            if (
                existing.entity_key == proposal.entity_key
                and existing.status == "ACTIVE"
                and existing.value != proposal.value
            ):
                conf_res = resolve_conflict(
                    existing, proposal.model_dump(), is_time_sensitive=is_ts
                )

                if conf_res.decision == ConflictDecision.UNRESOLVED:
                    reason = f"unresolved_conflict:{conf_res.rule_applied}"
                    # QUARANTINE incoming, then emit CONFLICT_RAISED (GATE-2, CONF-2)
                    evt = append_and_project(
                        conn,
                        case_id,
                        EventType.GATE_VERDICT,
                        caller_role,
                        {
                            "fact": {
                                "fact_id": fact_id,
                                "type": proposal.type,
                                "value": proposal.value,
                                "source": proposal.source,
                                "source_type": proposal.source_type,
                                "agent_id": proposal.agent_id or caller_role,
                                "self_confidence": proposal.self_confidence,
                                "evidence_ref": proposal.evidence_ref,
                                "entity_key": proposal.entity_key,
                                "derived_from": proposal.derived_from,
                            },
                            "verdict": GateVerdict.QUARANTINE,
                            "reason": reason,
                            "own_trust": 0.0,
                            "effective_trust": 0.0,
                            "is_conclusion": False,
                        },
                    )
                    append_and_project(
                        conn,
                        case_id,
                        EventType.CONFLICT_RAISED,
                        "conflict_engine",
                        {"fact_ids": [existing.fact_id, fact_id], "rule": conf_res.rule_applied},
                    )
                    return GateResult(
                        verdict=GateVerdict.QUARANTINE,
                        reason=reason,
                        fact_id=fact_id,
                        own_trust=0.0,
                        effective_trust=0.0,
                        event_id=evt.event_id,
                    )

                elif conf_res.decision == ConflictDecision.EXISTING_WINS:
                    reason = f"lost_conflict:{conf_res.rule_applied}"
                    evt = append_and_project(
                        conn,
                        case_id,
                        EventType.GATE_VERDICT,
                        caller_role,
                        {
                            "fact": {
                                "fact_id": fact_id,
                                "type": proposal.type,
                                "value": proposal.value,
                                "source": proposal.source,
                                "source_type": proposal.source_type,
                                "agent_id": proposal.agent_id or caller_role,
                                "self_confidence": proposal.self_confidence,
                                "evidence_ref": proposal.evidence_ref,
                                "entity_key": proposal.entity_key,
                                "derived_from": proposal.derived_from,
                            },
                            "verdict": GateVerdict.QUARANTINE,
                            "reason": reason,
                            "own_trust": 0.0,
                            "effective_trust": 0.0,
                            "is_conclusion": False,
                        },
                    )
                    return GateResult(
                        verdict=GateVerdict.QUARANTINE,
                        reason=reason,
                        fact_id=fact_id,
                        own_trust=0.0,
                        effective_trust=0.0,
                        event_id=evt.event_id,
                    )

                elif conf_res.decision == ConflictDecision.INCOMING_WINS:
                    displaced_existing_fact_id = existing.fact_id

    # -------------------------------------------------------------
    # Step 5: Adversarial Verifier Pass (INV-4, GATE-2, GATE-3)
    # -------------------------------------------------------------
    raw_evidence = get_raw_evidence_content(
        proposal.evidence_ref, proposal.derived_from, state.facts, pack
    )
    v_output = verify_claim(proposal.model_dump(), raw_evidence, verifier_adapter)

    # Record Verifier LLM action in ledger (Architecture 4.6)
    v_cache_key = compute_cache_key(proposal.model_dump(), raw_evidence)
    v_result_hash = hashlib.sha256(
        canonical_json(v_output.model_dump()).encode("utf-8")
    ).hexdigest()
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.AGENT_ACTION,
        actor="verifier",
        payload={
            "actor": "verifier",
            "tool": "adversarial_verifier",
            "args_hash": v_cache_key,
            "result_hash": v_result_hash,
            "tokens_in": v_output.tokens_in,
            "tokens_out": v_output.tokens_out,
            "cache_hit": v_output.cache_hit,
        },
    )

    if v_output.verdict != "SUPPORTED":
        reason = f"verifier_quarantine: {v_output.verdict} ({v_output.rationale})"
        evt = append_and_project(
            conn,
            case_id,
            EventType.GATE_VERDICT,
            caller_role,
            {
                "fact": {
                    "fact_id": fact_id,
                    "type": proposal.type,
                    "value": proposal.value,
                    "source": proposal.source,
                    "source_type": proposal.source_type,
                    "agent_id": proposal.agent_id or caller_role,
                    "self_confidence": proposal.self_confidence,
                    "evidence_ref": proposal.evidence_ref,
                    "entity_key": proposal.entity_key,
                    "derived_from": proposal.derived_from,
                },
                "verdict": GateVerdict.QUARANTINE,
                "reason": reason,
                "verifier_output": v_output.model_dump(),
                "own_trust": 0.0,
                "effective_trust": 0.0,
                "is_conclusion": False,
            },
        )
        return GateResult(
            verdict=GateVerdict.QUARANTINE,
            reason=reason,
            fact_id=fact_id,
            own_trust=0.0,
            effective_trust=0.0,
            event_id=evt.event_id,
        )

    # -------------------------------------------------------------
    # ADMIT: Passed all checks! (GATE-3, GATE-7)
    # -------------------------------------------------------------
    reason = "admitted: passed all validation checks and verifier supported"
    evt = append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        caller_role,
        {
            "fact": {
                "fact_id": fact_id,
                "type": proposal.type,
                "value": proposal.value,
                "source": proposal.source,
                "source_type": proposal.source_type,
                "agent_id": proposal.agent_id or caller_role,
                "self_confidence": proposal.self_confidence,
                "evidence_ref": proposal.evidence_ref,
                "entity_key": proposal.entity_key,
                "derived_from": proposal.derived_from,
            },
            "verdict": GateVerdict.ADMIT,
            "reason": reason,
            "verifier_output": v_output.model_dump(),
            "own_trust": own_trust,
            "effective_trust": effective_trust,
            "is_conclusion": is_conclusion,
        },
    )

    # If an existing fact was displaced by incoming winner, emit FACT_SUPERSEDED (GATE-6)
    if displaced_existing_fact_id:
        append_and_project(
            conn,
            case_id,
            EventType.FACT_SUPERSEDED,
            "conflict_engine",
            {
                "old_id": displaced_existing_fact_id,
                "new_id": fact_id,
                "rule": "incoming_won_conflict",
            },
        )

    return GateResult(
        verdict=GateVerdict.ADMIT,
        reason=reason,
        fact_id=fact_id,
        own_trust=own_trust,
        effective_trust=effective_trust,
        event_id=evt.event_id,
    )
