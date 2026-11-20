"""Invariant Test: test_decision_rule.

Enforces:
- Section 3.5 Decision Rule Truth Table:
  1. ESCALATE if budget is exhausted or any fact is CONTESTED.
  2. NEED_MORE if no conclusion, rework queue non-empty, or missing required checks.
  3. With conclusion: ESCALATE if conclusion not ACTIVE, ancestor CONTESTED/TAINTED,
     or trust < T_auto. Otherwise AUTO_FIX.
- INV-6: Deterministic governance without LLM adjudication.
"""

from pathlib import Path

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.decision import evaluate_decision
from groundtruth.core.enums import DecisionSignal, EventType, GateVerdict, SourceType
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project


def test_decision_truth_table_branches() -> None:
    """Walk through every branch of the Section 3.5 decision truth table."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_decision_tt"

    # 1. Open case
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1_auth_refactor"}},
    )

    # Branch A: No conclusion asserted -> NEED_MORE
    res_a = evaluate_decision(conn, case_id, pack)
    assert res_a.signal == DecisionSignal.NEED_MORE.value
    assert "cicd_root_cause" in res_a.missing_checks
    assert "log_anomaly" in res_a.missing_checks

    # Seed log_anomaly and commit_change
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_log_1",
                "type": "log_anomaly",
                "value": {"error": "test fail"},
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_commit_1",
                "type": "commit_change",
                "value": {"sha": "abc"},
                "source": "repo_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    # Seed negative_check (required by fixture_1 in checks.yaml)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_neg_1",
                "type": "negative_check",
                "value": {
                    "check_type": "oom_pod_crash",
                    "scope": ["pod-1"],
                    "window_start": "2026-11-19T09:00:00Z",
                    "window_end": "2026-11-19T10:00:00Z",
                },
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    # Still NEED_MORE because conclusion has not been asserted
    res_b = evaluate_decision(conn, case_id, pack)
    assert res_b.signal == DecisionSignal.NEED_MORE.value
    assert res_b.missing_checks == ["cicd_root_cause"]

    # Now assert conclusion cicd_root_cause (trust = 0.60 >= T_auto 0.60)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_cause_1",
                "type": "cicd_root_cause",
                "value": {"root_cause": "NPE in auth"},
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
                "derived_from": ["fact_log_1", "fact_commit_1"],
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.60,
            "effective_trust": 0.60,
            "is_conclusion": True,
        },
    )

    # Branch B: All checks satisfied and trust >= T_auto -> AUTO_FIX!
    res_c = evaluate_decision(conn, case_id, pack)
    assert res_c.signal == DecisionSignal.AUTO_FIX.value
    assert res_c.conclusion_fact_id == "fact_cause_1"

    # Branch C: Any fact in case is CONTESTED -> ESCALATE (CONF-2)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CONFLICT_RAISED,
        actor="system",
        payload={"fact_ids": ["fact_commit_1"], "rule": "unresolved"},
    )
    res_d = evaluate_decision(conn, case_id, pack)
    assert res_d.signal == DecisionSignal.ESCALATE.value
    assert any("CONTESTED" in r or "contested" in r for r in res_d.reasons)


def test_decision_budget_exhausted_escalates() -> None:
    """Enforce CASE-4: When case budget is exhausted, decision returns ESCALATE."""
    conn = get_connection(":memory:")
    init_db(conn)
    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_dec_budget"

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {}},
    )

    # Exhaust budget via AGENT_ACTION events
    max_tool_calls = pack.trust.budget.max_tool_calls
    for i in range(max_tool_calls):
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.AGENT_ACTION,
            actor="log_agent",
            payload={
                "actor": "log_agent",
                "tool": "scan",
                "args_hash": f"a_{i}",
                "result_hash": f"r_{i}",
                "tokens_in": 10,
                "tokens_out": 10,
            },
        )

    res = evaluate_decision(conn, case_id, pack)
    assert res.signal == DecisionSignal.ESCALATE.value
    assert any("BUDGET_EXHAUSTED" in r for r in res.reasons)


def test_decision_low_trust_conclusion_escalates() -> None:
    """Enforce rules 3.5 & TRUST-7: Conclusion below T_auto escalates."""
    conn = get_connection(":memory:")
    init_db(conn)
    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_dec_low_trust"

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {}},
    )

    # Assert conclusion with effective trust 0.40 (< T_auto 0.60)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_cause_weak",
                "type": "cicd_root_cause",
                "value": {"root_cause": "guess"},
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 0.40,
                "derived_from": [],
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.40,
            "effective_trust": 0.40,
            "is_conclusion": True,
        },
    )

    res = evaluate_decision(conn, case_id, pack)
    assert res.signal == DecisionSignal.ESCALATE.value
    assert any("trust_insufficient" in r for r in res.reasons)
