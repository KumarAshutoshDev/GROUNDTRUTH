"""Invariant Test: test_taint_cascade.

Enforces:
- INV-9: Taint is sticky. TAINTED facts return to ACTIVE only via HUMAN_OVERRIDE
  or a superseding fact.
- Architecture Section 7 (Taint Engine):
  Retracting a premise recursively taints all downstream inference descendants,
  collapses their effective trust to 0.0, and places tainted conclusions in rework_queue.
"""

from pathlib import Path

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.decision import evaluate_decision
from groundtruth.core.enums import (
    DecisionSignal,
    EventType,
    FactStatus,
    GateVerdict,
    SourceType,
)
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.taint import propagate_taint, retract_and_taint


def test_taint_cascade_downstream_inferences() -> None:
    """Retracting a premise taints all 3 downstream inferences and queues conclusion for rework."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_taint_cascade"

    # 1. Open case
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {"service": "payments"}},
    )

    # 2. Premise: log_anomaly (TOOL_OUTPUT)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_premise",
                "type": "log_anomaly",
                "value": {"error": "Database connection refused"},
                "source": "log_scanner",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.95,
            "effective_trust": 0.95,
        },
    )

    # 3. Downstream Inference 1: derived from premise
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_inf_1",
                "type": "pod_status",
                "value": {"pod_name": "db-pool", "status": "Failed"},
                "source": "log_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
                "derived_from": ["fact_premise"],
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.90,
            "effective_trust": 0.90,
        },
    )

    # 4. Downstream Inference 2: derived from Inference 1
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_inf_2",
                "type": "commit_change",
                "value": {"sha": "c0ffee1", "summary": "DB pool migration"},
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
                "derived_from": ["fact_inf_1"],
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.85,
            "effective_trust": 0.85,
        },
    )

    # 5. Downstream Inference 3: Conclusion derived from Inference 2
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_conc_root_cause",
                "type": "cicd_root_cause",
                "value": {
                    "root_cause": "Faulty DB pool config in commit c0ffee1",
                    "category": "CONFIG_ERROR",
                    "fix_recommendation": "Revert commit c0ffee1",
                },
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
                "derived_from": ["fact_inf_2"],
            },
            "verdict": GateVerdict.ADMIT.value,
            "is_conclusion": True,
            "own_trust": 0.85,
            "effective_trust": 0.85,
        },
    )

    # Verify initial active state before taint
    state_before = load_case_projection(conn, case_id)
    assert state_before.facts["fact_premise"].status == FactStatus.ACTIVE
    assert state_before.facts["fact_inf_1"].status == FactStatus.ACTIVE
    assert state_before.facts["fact_inf_2"].status == FactStatus.ACTIVE
    assert state_before.facts["fact_conc_root_cause"].status == FactStatus.ACTIVE

    # 6. Retract premise and execute taint cascade
    tainted = retract_and_taint(
        conn=conn,
        case_id=case_id,
        fact_id="fact_premise",
        actor="orchestrator",
        reason="falsified_premise",
        pack=pack,
    )

    # Exactly 3 downstream inferences must be tainted
    assert tainted == {"fact_inf_1", "fact_inf_2", "fact_conc_root_cause"}

    # Verify projected state after taint cascade
    state_after = load_case_projection(conn, case_id)
    assert state_after.facts["fact_premise"].status == FactStatus.RETRACTED
    assert state_after.facts["fact_inf_1"].status == FactStatus.TAINTED
    assert state_after.facts["fact_inf_2"].status == FactStatus.TAINTED
    assert state_after.facts["fact_conc_root_cause"].status == FactStatus.TAINTED

    # Effective trust collapsed to 0.0
    assert state_after.facts["fact_inf_1"].effective_trust == 0.0
    assert state_after.facts["fact_inf_2"].effective_trust == 0.0
    assert state_after.facts["fact_conc_root_cause"].effective_trust == 0.0

    # Decision engine must place tainted conclusion in rework_queue and return NEED_MORE
    decision = evaluate_decision(conn=conn, case_id=case_id, pack=pack)
    assert decision.signal == DecisionSignal.NEED_MORE.value
    assert "fact_conc_root_cause" in decision.rework_queue
    assert "conclusion_tainted_requires_rework" in decision.reasons


def test_taint_is_sticky_inv_9() -> None:
    """INV-9: Tainted status cannot be cleared by automated re-evaluation, only HUMAN_OVERRIDE."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_taint_sticky"

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {"service": "auth"}},
    )

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "f_root",
                "type": "log_anomaly",
                "value": {"error": "bad token"},
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.9,
            "effective_trust": 0.9,
        },
    )

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "f_child",
                "type": "commit_change",
                "value": {"sha": "deadbeef"},
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
                "derived_from": ["f_root"],
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.85,
            "effective_trust": 0.85,
        },
    )

    # Taint the child
    propagate_taint(conn=conn, case_id=case_id, root_fact_id="f_root", pack=pack)

    state = load_case_projection(conn, case_id)
    assert state.facts["f_child"].status == FactStatus.TAINTED

    # Manual un-tainting via HUMAN_OVERRIDE (RESTORE_ACTIVE)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.HUMAN_OVERRIDE,
        actor="human",
        payload={
            "fact_id": "f_child",
            "action": "RESTORE_ACTIVE",
            "reason": "Expert engineer verified commit hash independently",
        },
    )

    state_overridden = load_case_projection(conn, case_id)
    assert state_overridden.facts["f_child"].status == FactStatus.ACTIVE
