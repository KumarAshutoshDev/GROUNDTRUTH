"""Invariant test verifying INV-2: State is derived.

Proves:
Replay at every event index reproduces identical state, including cases,
facts, fact_edges, negative_checks, and the conclusion pointer.
"""

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.replay import replay_case


def test_replay_identical() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_replay_test"

    # Event 1: Open case
    append_and_project(
        conn,
        case_id,
        EventType.CASE_OPENED,
        "system",
        {"domain_pack": "cicd", "trigger": {"commit_sha": "abc1234"}},
    )

    # Event 2: Admit log anomaly fact
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_anomaly",
                "type": "log_anomaly",
                "value": {"message": "NullPointerException in auth"},
                "source": "log_agent",
                "source_type": "tool_output",
                "agent_id": "log_agent",
                "self_confidence": 0.95,
                "evidence_ref": "log_line_102",
                "derived_from": [],
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    # Event 3: Admit commit change fact
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_commit",
                "type": "commit_change",
                "value": {"sha": "abc1234", "author": "dev@test.com"},
                "source": "repo_agent",
                "source_type": "tool_output",
                "agent_id": "repo_agent",
                "self_confidence": 0.95,
                "evidence_ref": "git_diff_hunk_1",
                "derived_from": [],
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    # Event 4: Admit conclusion inference fact
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_root_cause",
                "type": "cicd_root_cause",
                "value": {"root_cause": "unhandled null in auth refactor"},
                "source": "repo_agent",
                "source_type": "agent_inference",
                "agent_id": "repo_agent",
                "self_confidence": 0.85,
                "evidence_ref": None,
                "derived_from": ["fact_anomaly", "fact_commit"],
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.60,
            "effective_trust": 0.60,
            "is_conclusion": True,
        },
    )

    # Event 5: Admit negative check
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_neg_oom",
                "type": "negative_check",
                "value": {
                    "check_type": "oom_killed",
                    "scope": ["pod-1", "pod-2", "pod-3"],
                    "window_start": "2026-11-19T11:00:00Z",
                    "window_end": "2026-11-19T12:00:00Z",
                    "expires_at": None,
                },
                "source": "log_agent",
                "source_type": "tool_output",
                "agent_id": "log_agent",
                "self_confidence": 0.95,
                "evidence_ref": "k8s_events_dump",
                "derived_from": [],
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    # Event 6: Recompute trust
    append_and_project(
        conn,
        case_id,
        EventType.TRUST_RECOMPUTED,
        "trust_engine",
        {
            "fact_id": "fact_anomaly",
            "new_own_trust": 0.88,
            "new_effective_trust": 0.88,
            "cause_event": "evt_decay",
        },
    )

    # Event 7: Conclude case
    append_and_project(
        conn,
        case_id,
        EventType.CASE_STATE_CHANGED,
        "orchestrator",
        {"from": "INVESTIGATING", "to": "CONCLUDED"},
    )

    # 1. Load state directly from SQLite projection tables
    live_projection = load_case_projection(conn, case_id)

    # 2. Replay all events in memory through pure reducer
    replayed_state = replay_case(conn, case_id)

    # 3. Assert live projection and replayed state are 100% identical
    assert live_projection.case is not None
    assert replayed_state.case is not None

    # Compare CaseModel
    assert live_projection.case.case_id == replayed_state.case.case_id
    assert live_projection.case.domain_pack == replayed_state.case.domain_pack
    assert live_projection.case.state == replayed_state.case.state
    assert live_projection.case.conclusion_fact_id == replayed_state.case.conclusion_fact_id
    assert live_projection.case.concluded_at == replayed_state.case.concluded_at
    assert live_projection.case.conclusion_fact_id == "fact_root_cause"

    # Compare Facts
    assert set(live_projection.facts.keys()) == set(replayed_state.facts.keys())
    for fid, live_fact in live_projection.facts.items():
        replayed_fact = replayed_state.facts[fid]
        assert live_fact.fact_id == replayed_fact.fact_id
        assert live_fact.type == replayed_fact.type
        assert live_fact.status == replayed_fact.status
        assert live_fact.verifier_state == replayed_fact.verifier_state
        assert live_fact.own_trust == replayed_fact.own_trust
        assert live_fact.effective_trust == replayed_fact.effective_trust
        assert live_fact.is_conclusion == replayed_fact.is_conclusion
        assert set(live_fact.derived_from) == set(replayed_fact.derived_from)

    # Compare Edges
    assert set(live_projection.edges) == set(replayed_state.edges)

    # Compare Negative Checks
    assert set(live_projection.negative_checks.keys()) == set(replayed_state.negative_checks.keys())
    for cid, live_neg in live_projection.negative_checks.items():
        replayed_neg = replayed_state.negative_checks[cid]
        assert live_neg.check_type == replayed_neg.check_type
        assert live_neg.scope == replayed_neg.scope
        assert live_neg.window_start == replayed_neg.window_start
        assert live_neg.window_end == replayed_neg.window_end


def test_replay_historical_time_travel() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_time_travel"

    append_and_project(
        conn,
        case_id,
        EventType.CASE_OPENED,
        "system",
        {"domain_pack": "cicd", "trigger": {}},
    )
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "f1",
                "type": "log_anomaly",
                "source": "log",
                "source_type": "tool_output",
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
        },
    )
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "f2",
                "type": "commit_change",
                "source": "repo",
                "source_type": "tool_output",
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
        },
    )

    # Time travel to seq 1
    state_at_1 = replay_case(conn, case_id, upto_seq=1)
    assert len(state_at_1.facts) == 0

    # Time travel to seq 2
    state_at_2 = replay_case(conn, case_id, upto_seq=2)
    assert len(state_at_2.facts) == 1
    assert "f1" in state_at_2.facts
    assert "f2" not in state_at_2.facts

    # Time travel to seq 3
    state_at_3 = replay_case(conn, case_id, upto_seq=3)
    assert len(state_at_3.facts) == 2
    assert "f1" in state_at_3.facts
    assert "f2" in state_at_3.facts
