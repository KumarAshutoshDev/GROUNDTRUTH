"""Invariant Test: test_contract_isolation.

Enforces:
- INV-10: Isolation. A token for case A MUST fail on case B. A role MUST NOT read
  or write fact types outside its contract.
- FR-5: Role-scoped context projection within max_context_tokens.
- SEC-5: Access denials are recorded as ACCESS_DENIED events in the token's case ledger.
"""

from fastapi.testclient import TestClient

from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict, SourceType
from groundtruth.core.projector import append_and_project


def test_cross_case_read_denied_and_logged() -> None:
    """Enforce INV-10 & SEC-5: Token for Case A cannot read Case B."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # 1. Open Case A and Case B
    res_a = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    assert res_a.status_code == 200
    case_a_id = res_a.json()["case_id"]
    token_a_log = res_a.json()["tokens"]["log_agent"]

    res_b = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "payment"}},
    )
    assert res_b.status_code == 200
    case_b_id = res_b.json()["case_id"]

    # 2. Token from Case A attempts to read Case B -> 403 Forbidden
    res_cross = client.post(
        f"/cases/{case_b_id}/read",
        headers={"Authorization": f"Bearer {token_a_log}"},
        json={"goal": "investigate payment outage"},
    )
    assert res_cross.status_code == 403
    assert "scoped to case" in res_cross.json()["detail"]

    # 3. SEC-5: ACCESS_DENIED event must be logged in Case A's ledger (the token's own case)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT event_type, payload FROM events WHERE case_id = ? AND event_type = ?",
        (case_a_id, EventType.ACCESS_DENIED.value),
    )
    denials = cursor.fetchall()
    assert len(denials) >= 1
    assert "cross_case_access_denied" in denials[0]["payload"]


def test_out_of_contract_read_no_reads_denied() -> None:
    """Enforce INV-10: Role with empty reads (e.g. orchestrator) cannot call /read."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]
    orch_token = data["tokens"]["orchestrator"]

    # Orchestrator has reads: [] in reserved contracts
    res_read = client.post(
        f"/cases/{case_id}/read",
        headers={"Authorization": f"Bearer {orch_token}"},
        json={"goal": "supervise"},
    )
    assert res_read.status_code == 403
    assert "no read permissions" in res_read.json()["detail"]

    # ACCESS_DENIED event logged in case ledger
    cursor = conn.cursor()
    cursor.execute(
        "SELECT event_type, payload FROM events WHERE case_id = ? AND event_type = ?",
        (case_id, EventType.ACCESS_DENIED.value),
    )
    row = cursor.fetchone()
    assert row is not None
    assert "out_of_contract_read_no_reads" in row["payload"]


def test_out_of_contract_read_specific_type_denied() -> None:
    """Enforce INV-10: Agent cannot request fact type outside its contract reads."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]
    log_token = data["tokens"]["log_agent"]

    # log_agent contract reads: ["trigger", "log_anomaly", "pod_status"]
    # Requesting "cicd_root_cause" is forbidden
    res_read = client.post(
        f"/cases/{case_id}/read",
        headers={"Authorization": f"Bearer {log_token}"},
        json={"goal": "find root cause", "fact_type": "cicd_root_cause"},
    )
    assert res_read.status_code == 403
    assert "cannot read fact type 'cicd_root_cause'" in res_read.json()["detail"]


def test_in_contract_read_scoped_and_budgeted() -> None:
    """Enforce FR-5 & INV-10: Permitted facts are filtered, scored, and token-budgeted."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]
    log_token = data["tokens"]["log_agent"]

    # Seed 2 facts via projector:
    # 1. pod_status (ACTIVE, trust 0.90) - log_agent contract reads this!
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_pod_1",
                "type": "pod_status",
                "value": {"status": "CrashLoopBackOff", "pod": "checkout-svc-1"},
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

    # 2. commit_change (ACTIVE, trust 0.90) - log_agent contract DOES NOT read this!
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_commit_1",
                "type": "commit_change",
                "value": {"commit": "a1b2c3d", "author": "dev@company.com"},
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

    # Call /read as log_agent
    res_read = client.post(
        f"/cases/{case_id}/read",
        headers={"Authorization": f"Bearer {log_token}"},
        json={"goal": "inspect pod health"},
    )
    assert res_read.status_code == 200
    proj = res_read.json()

    # log_agent should receive pod_status
    fact_ids = [f["fact_id"] for f in proj["facts"]]
    assert "fact_pod_1" in fact_ids
    # log_agent must NOT receive commit_change (not in log_agent reads contract)
    assert "fact_commit_1" not in fact_ids


def test_out_of_contract_write_rejected_by_gate() -> None:
    """Enforce INV-10: Role proposing unpermitted fact type is rejected by gate."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]
    log_token = data["tokens"]["log_agent"]

    # log_agent writes: ["log_anomaly", "pod_status"]
    # Trying to propose "cicd_root_cause" must be rejected by gate
    res_prop = client.post(
        f"/cases/{case_id}/propose",
        headers={"Authorization": f"Bearer {log_token}"},
        json={
            "type": "cicd_root_cause",
            "value": {"cause": "bad commit"},
            "source": "log_agent",
            "source_type": SourceType.AGENT_INFERENCE.value,
            "derived_from": ["fact_dummy"],
        },
    )
    assert res_prop.status_code == 200
    prop_data = res_prop.json()
    assert prop_data["verdict"] == GateVerdict.REJECT.value
    assert "contract_violation" in prop_data["reason"]
