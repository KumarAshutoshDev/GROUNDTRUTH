"""Invariant Test: test_negative_scope.

Enforces:
- NEG-1: Mandatory check_type, scope, and time window on negative facts.
- NEG-2: Strict suppression conditions (exact subset scope, covering window,
  unexpired, ACTIVE >= T_cite).
- NEG-3: Explicit failure condition return (never "probably covered").
"""

from datetime import UTC, datetime
from pathlib import Path

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict, SourceType
from groundtruth.core.gate import FactProposal, evaluate_proposal
from groundtruth.core.negative import (
    NegativeCheckSpec,
    check_negative,
    is_scope_covered,
    is_window_covered,
)
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project


def test_negative_check_schema_rejection_missing_window() -> None:
    """NEG-1: Negative fact proposals missing window or scope are rejected at the gate."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    adapter = MockFixtureLLMAdapter()
    case_id = "case_neg_schema"

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1"}},
    )

    # Missing window_end
    bad_proposal = FactProposal(
        type="negative_check",
        value={
            "check_type": "oom_killed",
            "scope": ["pod-1"],
            "window_start": "2026-11-19T10:00:00Z",
        },
        source="log_agent",
        source_type=SourceType.TOOL_OUTPUT,
    )
    res = evaluate_proposal(conn, case_id, "log_agent", bad_proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "schema_violation" in res.reason
    assert "NEG-1" in res.reason

    # Missing scope
    bad_proposal_2 = FactProposal(
        type="negative_check",
        value={
            "check_type": "oom_killed",
            "window_start": "2026-11-19T10:00:00Z",
            "window_end": "2026-11-19T11:00:00Z",
        },
        source="log_agent",
        source_type=SourceType.TOOL_OUTPUT,
    )
    res_2 = evaluate_proposal(conn, case_id, "log_agent", bad_proposal_2, pack, adapter)
    assert res_2.verdict == GateVerdict.REJECT
    assert "schema_violation" in res_2.reason


def test_negative_scope_and_window_helpers() -> None:
    """Unit validation of pure scope and window coverage functions."""
    assert is_scope_covered(["p1", "p2"], ["p1", "p2", "p3"])
    assert not is_scope_covered(["p1", "p4"], ["p1", "p2", "p3"])

    # Recorded: 10:00 to 11:00
    # Requested inside: 10:15 to 10:45 -> covered
    assert is_window_covered(
        req_start="2026-11-19T10:15:00Z",
        req_end="2026-11-19T10:45:00Z",
        rec_start="2026-11-19T10:00:00Z",
        rec_end="2026-11-19T11:00:00Z",
    )
    # Requested earlier than recorded start -> not covered
    assert not is_window_covered(
        req_start="2026-11-19T09:59:00Z",
        req_end="2026-11-19T10:45:00Z",
        rec_start="2026-11-19T10:00:00Z",
        rec_end="2026-11-19T11:00:00Z",
    )
    # Requested later than recorded end -> not covered
    assert not is_window_covered(
        req_start="2026-11-19T10:15:00Z",
        req_end="2026-11-19T11:01:00Z",
        rec_start="2026-11-19T10:00:00Z",
        rec_end="2026-11-19T11:00:00Z",
    )


def test_negative_knowledge_evaluation_scenarios() -> None:
    """NEG-2 & NEG-3: Strict suppression rules and explicit failure conditions."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_neg_eval"

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1"}},
    )

    pods_12 = [f"worker-pod-{i}" for i in range(1, 13)]

    # Record negative check for 12 pods from 10:00 to 11:00
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_neg_oom",
                "type": "negative_check",
                "value": {
                    "check_type": "oom_killed",
                    "scope": pods_12,
                    "window_start": "2026-11-19T10:00:00Z",
                    "window_end": "2026-11-19T11:00:00Z",
                    "expires_at": "2026-11-19T12:00:00Z",
                },
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

    now_10_30 = datetime(2026, 11, 19, 10, 30, 0, tzinfo=UTC)

    # 1. Exact or subset scope inside window -> COVERED
    q_covered = NegativeCheckSpec(
        check_type="oom_killed",
        scope=["worker-pod-1", "worker-pod-2"],
        window_start="2026-11-19T10:10:00Z",
        window_end="2026-11-19T10:40:00Z",
    )
    res_covered = check_negative(conn, case_id, q_covered, pack, now=now_10_30)
    assert res_covered.verdict == "COVERED"
    assert res_covered.reason == "COVERED"
    assert res_covered.matching_fact_id == "fact_neg_oom"

    # 2. Scope mismatch: query 13 pods (includes 13th unverified pod) -> NOT_COVERED:scope_mismatch
    q_wider_scope = NegativeCheckSpec(
        check_type="oom_killed",
        scope=pods_12 + ["worker-pod-13"],
        window_start="2026-11-19T10:10:00Z",
        window_end="2026-11-19T10:40:00Z",
    )
    res_scope_mismatch = check_negative(conn, case_id, q_wider_scope, pack, now=now_10_30)
    assert res_scope_mismatch.verdict == "NOT_COVERED"
    assert res_scope_mismatch.reason == "scope_mismatch"
    assert res_scope_mismatch.status == "NOT_COVERED:scope_mismatch"

    # 3. Window mismatch: query later window extending past recorded window_end
    q_later_window = NegativeCheckSpec(
        check_type="oom_killed",
        scope=["worker-pod-1"],
        window_start="2026-11-19T10:30:00Z",
        window_end="2026-11-19T11:15:00Z",
    )
    res_window_mismatch = check_negative(conn, case_id, q_later_window, pack, now=now_10_30)
    assert res_window_mismatch.verdict == "NOT_COVERED"
    assert res_window_mismatch.reason == "window_mismatch"
    assert res_window_mismatch.status == "NOT_COVERED:window_mismatch"

    # 4. Check expired: query at 12:30 (past expires_at 12:00)
    now_12_30 = datetime(2026, 11, 19, 12, 30, 0, tzinfo=UTC)
    res_expired = check_negative(conn, case_id, q_covered, pack, now=now_12_30)
    assert res_expired.verdict == "NOT_COVERED"
    assert res_expired.reason == "check_expired"

    # 5. Type mismatch
    q_other_type = NegativeCheckSpec(
        check_type="segfault",
        scope=["worker-pod-1"],
        window_start="2026-11-19T10:10:00Z",
        window_end="2026-11-19T10:40:00Z",
    )
    res_other = check_negative(conn, case_id, q_other_type, pack, now=now_10_30)
    assert res_other.verdict == "NOT_COVERED"
    assert res_other.reason == "no_matching_check"

    # 6. Trust below threshold (< T_cite = 0.6)
    conn.execute("UPDATE facts SET effective_trust = 0.4 WHERE fact_id = 'fact_neg_oom'")
    res_low_trust = check_negative(conn, case_id, q_covered, pack, now=now_10_30)
    assert res_low_trust.verdict == "NOT_COVERED"
    assert res_low_trust.reason == "trust_below_threshold"

    # 7. Backing fact inactive (TAINTED)
    conn.execute(
        "UPDATE facts SET effective_trust = 0.9, status = 'TAINTED' WHERE fact_id = 'fact_neg_oom'"
    )
    res_tainted = check_negative(conn, case_id, q_covered, pack, now=now_10_30)
    assert res_tainted.verdict == "NOT_COVERED"
    assert res_tainted.reason == "backing_fact_inactive"
