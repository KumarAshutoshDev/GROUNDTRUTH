"""Unit tests verifying the pure reducer diff and apply operations."""

from groundtruth.core.enums import EventType, FactStatus, GateVerdict, VerifierState
from groundtruth.core.ledger import Event
from groundtruth.core.models import CaseState, OpType
from groundtruth.core.reducer import apply, diff


def make_event(
    seq: int,
    event_type: str,
    payload: dict,
    case_id: str = "case_100",
    actor: str = "test_agent",
) -> Event:
    return Event(
        event_id=f"evt_{seq}",
        case_id=case_id,
        seq=seq,
        event_type=event_type,
        actor=actor,
        payload=payload,
        prev_hash="0" * 64,
        hash="1" * 64,
        ts="2026-11-19T12:00:00Z",
    )


def test_case_opened() -> None:
    state = CaseState(case_id="case_100")
    e = make_event(1, EventType.CASE_OPENED, {"domain_pack": "cicd", "trigger": {"run": 42}})

    ops = diff(state, e)
    assert len(ops) == 1
    assert ops[0].op_type == OpType.INSERT_CASE
    assert ops[0].data["state"] == "OPEN"

    new_state = apply(state, e)
    assert new_state.case is not None
    assert new_state.case.state == "OPEN"
    assert new_state.case.domain_pack == "cicd"


def test_case_state_changed_concluded() -> None:
    state = CaseState(case_id="case_100")
    e1 = make_event(1, EventType.CASE_OPENED, {"domain_pack": "cicd", "trigger": {}})
    s1 = apply(state, e1)

    e2 = make_event(2, EventType.CASE_STATE_CHANGED, {"from": "OPEN", "to": "CONCLUDED"})
    s2 = apply(s1, e2)

    assert s2.case is not None
    assert s2.case.state == "CONCLUDED"
    assert s2.case.concluded_at == "2026-11-19T12:00:00Z"


def test_gate_verdict_admit_and_conclusion() -> None:
    state = CaseState(case_id="case_100")
    e1 = make_event(1, EventType.CASE_OPENED, {"domain_pack": "cicd", "trigger": {}})
    s1 = apply(state, e1)

    # Propose fact with conclusion
    fact_payload = {
        "fact": {
            "fact_id": "fact_root",
            "type": "cicd_root_cause",
            "value": {"cause": "bad_dep"},
            "source": "inference",
            "source_type": "agent_inference",
            "derived_from": ["fact_anomaly_1"],
        },
        "verdict": GateVerdict.ADMIT,
        "own_trust": 0.60,
        "effective_trust": 0.60,
        "is_conclusion": True,
    }
    e_verdict = make_event(2, EventType.GATE_VERDICT, fact_payload)

    ops = diff(s1, e_verdict)
    # Expected: INSERT_FACT, INSERT_EDGE, UPDATE_CASE (conclusion pointer)
    op_types = [op.op_type for op in ops]
    assert OpType.INSERT_FACT in op_types
    assert OpType.INSERT_EDGE in op_types
    assert OpType.UPDATE_CASE in op_types

    s2 = apply(s1, e_verdict)
    assert "fact_root" in s2.facts
    fact = s2.facts["fact_root"]
    assert fact.status == FactStatus.ACTIVE
    assert fact.verifier_state == VerifierState.SUPPORTED
    assert fact.effective_trust == 0.60
    assert len(s2.edges) == 1
    assert s2.edges[0].child_id == "fact_root"
    assert s2.edges[0].parent_id == "fact_anomaly_1"

    # CASE-1: verify conclusion pointer set on case
    assert s2.case is not None
    assert s2.case.conclusion_fact_id == "fact_root"


def test_gate_verdict_quarantine_never_sets_conclusion() -> None:
    state = CaseState(case_id="case_100")
    e1 = make_event(1, EventType.CASE_OPENED, {"domain_pack": "cicd", "trigger": {}})
    s1 = apply(state, e1)

    fact_payload = {
        "fact": {
            "fact_id": "fact_quar",
            "type": "cicd_root_cause",
            "value": {"cause": "unverified"},
            "source": "inference",
            "source_type": "agent_inference",
            "derived_from": [],
        },
        "verdict": GateVerdict.QUARANTINE,
        "own_trust": 0.0,
        "effective_trust": 0.0,
        "is_conclusion": True,  # proposed as conclusion, but quarantined
    }
    e_verdict = make_event(2, EventType.GATE_VERDICT, fact_payload)

    s2 = apply(s1, e_verdict)
    assert "fact_quar" in s2.facts
    assert s2.facts["fact_quar"].status == FactStatus.QUARANTINED
    assert s2.facts["fact_quar"].verifier_state == VerifierState.NOT_SUPPORTED
    # CASE-1: Quarantined fact MUST NOT set conclusion_fact_id
    assert s2.case is not None
    assert s2.case.conclusion_fact_id is None


def test_gate_verdict_reject_emits_zero_ops() -> None:
    state = CaseState(case_id="case_100")
    fact_payload = {
        "fact": {"fact_id": "fact_bad"},
        "verdict": GateVerdict.REJECT,
        "reason": "malformed_schema",
    }
    e_verdict = make_event(1, EventType.GATE_VERDICT, fact_payload)

    ops = diff(state, e_verdict)
    assert ops == []

    s1 = apply(state, e_verdict)
    assert len(s1.facts) == 0


def test_trust_recomputed() -> None:
    state = CaseState(case_id="case_100")
    fact_payload = {
        "fact": {"fact_id": "f1", "type": "pod_status", "source_type": "tool_output"},
        "verdict": GateVerdict.ADMIT,
        "own_trust": 0.90,
        "effective_trust": 0.90,
    }
    s1 = apply(state, make_event(1, EventType.GATE_VERDICT, fact_payload))

    recompute_event = make_event(
        2,
        EventType.TRUST_RECOMPUTED,
        {"fact_id": "f1", "new_own_trust": 0.85, "new_effective_trust": 0.85},
    )
    s2 = apply(s1, recompute_event)
    assert s2.facts["f1"].own_trust == 0.85
    assert s2.facts["f1"].effective_trust == 0.85


def test_taint_and_override() -> None:
    state = CaseState(case_id="case_100")
    fact_payload = {
        "fact": {"fact_id": "f1", "type": "commit_change", "source_type": "tool_output"},
        "verdict": GateVerdict.ADMIT,
        "own_trust": 0.90,
        "effective_trust": 0.90,
    }
    s1 = apply(state, make_event(1, EventType.GATE_VERDICT, fact_payload))

    # Taint fact
    taint_event = make_event(
        2, EventType.FACT_TAINTED, {"fact_id": "f1", "root_cause_fact_id": "f0"}
    )
    s2 = apply(s1, taint_event)
    assert s2.facts["f1"].status == FactStatus.TAINTED
    assert s2.facts["f1"].own_trust == 0.0

    # Human override restores active
    override_event = make_event(
        3,
        EventType.HUMAN_OVERRIDE,
        {"fact_id": "f1", "action": "RESTORE_ACTIVE", "reason": "verified by human"},
    )
    s3 = apply(s2, override_event)
    assert s3.facts["f1"].status == FactStatus.ACTIVE
