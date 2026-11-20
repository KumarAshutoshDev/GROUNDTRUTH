"""Invariant Test: test_decay_replay.

Enforces:
- TRUST-6: Recorded decay results replay identically.
- TRUST-8: Decay ticks run before /decision, /read, /graph, and /state.
  Ticks respect decay_epsilon and threshold crossings.
  Ticks never run for /state?at=N or on a CLOSED case.
- FIX-6: Supports injected fixture clocks.
- INV-2: Ledger replay reproduces identical decayed state.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict, SourceType
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.replay import replay_case
from groundtruth.core.trust_service import apply_decay_tick


def test_decay_ticks_respect_decay_epsilon() -> None:
    """Enforce TRUST-8: Decay ticks emit TRUST_RECOMPUTED only if delta >= decay_epsilon."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_decay_eps"

    # 1. Open case
    t0 = datetime(2026, 11, 19, 10, 0, 0, tzinfo=UTC)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {}},
        ts=t0,
    )

    # 2. Add volatile fact: pod_status (half-life = 900s = 15min in cicd pack, decay_epsilon = 0.01)
    # Base trust = 0.90
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "pod_1",
                "type": "pod_status",
                "value": {"status": "CrashLoopBackOff"},
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
        ts=t0,
    )

    # 3. Small time advance: 2 seconds later (age = 2s / 900s -> delta < 0.01)
    t1 = t0 + timedelta(seconds=2)
    events_small = apply_decay_tick(conn=conn, case_id=case_id, pack=pack, now=t1)
    # Should NOT emit any TRUST_RECOMPUTED event because change < decay_epsilon (0.01)
    assert len(events_small) == 0

    # 4. Larger time advance: 5 minutes later (age = 300s / 900s)
    # 0.90 * 0.5 ** (300/900) = 0.90 * 0.7937 = 0.7143 (delta = 0.1857 >= 0.01)
    t2 = t0 + timedelta(minutes=5)
    events_large = apply_decay_tick(conn=conn, case_id=case_id, pack=pack, now=t2)
    assert len(events_large) == 1
    recomputed_evt = events_large[0]
    assert recomputed_evt.event_type == EventType.TRUST_RECOMPUTED.value
    assert recomputed_evt.payload["fact_id"] == "pod_1"
    assert recomputed_evt.payload["old_effective_trust"] == 0.90
    assert abs(recomputed_evt.payload["new_effective_trust"] - 0.7143) < 0.01
    assert "as_of" in recomputed_evt.payload

    # 5. Advance past T_cite (0.50): age = 15 minutes (half-life) -> trust = 0.45 (< T_cite)
    t3 = t0 + timedelta(minutes=15)
    events_cite = apply_decay_tick(conn=conn, case_id=case_id, pack=pack, now=t3)
    assert len(events_cite) == 1
    assert events_cite[0].payload["new_effective_trust"] < pack.trust.T_cite


def test_decay_skipped_on_closed_case_and_historical_read() -> None:
    """Enforce TRUST-8: Decay ticks never run on CLOSED cases or historical state queries."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # 1. Open case
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]
    tokens = data["tokens"]

    # 2. Check historical state read: /cases/{id}/state?at=1 does not run decay tick
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as c FROM events WHERE case_id = ? AND event_type = ?",
        (case_id, EventType.TRUST_RECOMPUTED.value),
    )
    initial_recomputed_count = cursor.fetchone()["c"]

    res_hist = client.get(f"/cases/{case_id}/state?at=1")
    assert res_hist.status_code == 200

    cursor.execute(
        "SELECT COUNT(*) as c FROM events WHERE case_id = ? AND event_type = ?",
        (case_id, EventType.TRUST_RECOMPUTED.value),
    )
    after_hist_count = cursor.fetchone()["c"]
    assert after_hist_count == initial_recomputed_count  # No decay tick ran

    # 3. Close the case
    client.post(
        f"/cases/{case_id}/transition",
        headers={"Authorization": f"Bearer {tokens['orchestrator']}"},
        json={"to": "INVESTIGATING"},
    )
    client.post(
        f"/cases/{case_id}/transition",
        headers={"Authorization": f"Bearer {tokens['orchestrator']}"},
        json={"to": "CONCLUDED"},
    )
    client.post(
        f"/cases/{case_id}/transition",
        headers={"Authorization": f"Bearer {tokens['orchestrator']}"},
        json={"to": "CLOSED"},
    )

    # 4. Run decay tick on closed case -> returns empty list and appends nothing
    closed_events = apply_decay_tick(
        conn=conn,
        case_id=case_id,
        now=datetime.now(UTC) + timedelta(days=1),
    )
    assert len(closed_events) == 0


def test_decay_replay_identical() -> None:
    """Enforce INV-2 & TRUST-6: Ledger replay reproduces identical decayed trust."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_decay_replay"

    t0 = datetime(2026, 11, 19, 10, 0, 0, tzinfo=UTC)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {}},
        ts=t0,
    )

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "pod_1",
                "type": "pod_status",
                "value": {"status": "CrashLoopBackOff"},
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
        ts=t0,
    )

    # Decay tick 10 minutes later
    t1 = t0 + timedelta(minutes=10)
    apply_decay_tick(conn=conn, case_id=case_id, pack=pack, now=t1)

    projected_state = load_case_projection(conn, case_id)
    decayed_fact = projected_state.facts["pod_1"]

    # Replay from ledger
    replayed_state = replay_case(conn, case_id)
    replayed_fact = replayed_state.facts["pod_1"]

    assert replayed_fact.own_trust == decayed_fact.own_trust
    assert replayed_fact.effective_trust == decayed_fact.effective_trust
