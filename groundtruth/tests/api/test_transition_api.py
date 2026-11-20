"""API and Invariant Test: Case State Transitions & Lifecycle.

Enforces:
- CASE-2: Transitions emit CASE_STATE_CHANGED. concluded_at set when CONCLUDED.
- CASE-3: Ledger frozen when CLOSED. Attempts go to access_log.
- SEC-2: Tokens stop working when case is CLOSED.
- SEC-7: Only orchestrator or human may call /transition.
"""

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import CaseState, EventType
from groundtruth.core.projector import append_and_project


def test_transition_role_authorization() -> None:
    """Enforce SEC-7: Only orchestrator or human may call /transition."""
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
    tokens = data["tokens"]

    # log_agent token calling /transition -> 403 Forbidden
    res_log = client.post(
        f"/cases/{case_id}/transition",
        headers={"Authorization": f"Bearer {tokens['log_agent']}"},
        json={"to": "INVESTIGATING"},
    )
    assert res_log.status_code == 403
    assert "not permitted to call /transition" in res_log.json()["detail"]


def test_invalid_state_transitions_rejected() -> None:
    """Enforce CASE-2: Illegal transitions return 400 Bad Request."""
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
    auth_header = {"Authorization": f"Bearer {orch_token}"}

    # Case is OPEN: jumping straight to CONCLUDED or CLOSED is invalid
    res_bad1 = client.post(
        f"/cases/{case_id}/transition",
        headers=auth_header,
        json={"to": "CONCLUDED"},
    )
    assert res_bad1.status_code == 400
    assert "Invalid state transition" in res_bad1.json()["detail"]

    res_bad2 = client.post(
        f"/cases/{case_id}/transition",
        headers=auth_header,
        json={"to": "CLOSED"},
    )
    assert res_bad2.status_code == 400
    assert "Invalid state transition" in res_bad2.json()["detail"]


def test_lifecycle_walk_open_to_closed_and_freezing() -> None:
    """Walk case through OPEN -> INVESTIGATING -> CONCLUDED -> CLOSED (CASE-2, CASE-3, SEC-2)."""
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
    log_token = data["tokens"]["log_agent"]
    auth_orch = {"Authorization": f"Bearer {orch_token}"}
    auth_log = {"Authorization": f"Bearer {log_token}"}

    # 1. Transition OPEN -> INVESTIGATING
    res_inv = client.post(
        f"/cases/{case_id}/transition",
        headers=auth_orch,
        json={"to": "INVESTIGATING"},
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["state"] == CaseState.INVESTIGATING.value
    assert res_inv.json()["concluded_at"] is None

    # 2. Transition INVESTIGATING -> CONCLUDED
    res_con = client.post(
        f"/cases/{case_id}/transition",
        headers=auth_orch,
        json={"to": "CONCLUDED"},
    )
    assert res_con.status_code == 200
    assert res_con.json()["state"] == CaseState.CONCLUDED.value
    assert res_con.json()["concluded_at"] is not None

    # 3. Transition CONCLUDED -> CLOSED
    res_cls = client.post(
        f"/cases/{case_id}/transition",
        headers=auth_orch,
        json={"to": "CLOSED"},
    )
    assert res_cls.status_code == 200
    assert res_cls.json()["state"] == CaseState.CLOSED.value

    # 4. SEC-2: Attempting API calls with the case token now fails with 403 (token expired)
    res_after = client.post(
        f"/cases/{case_id}/actions",
        headers=auth_log,
        json={
            "tool": "check_status",
            "args_hash": "h1",
            "result_hash": "r1",
        },
    )
    assert res_after.status_code == 403
    assert "CLOSED" in res_after.json()["detail"]

    # 5. SEC-5: The denied attempt must be logged in access_log table
    cursor = conn.cursor()
    cursor.execute(
        "SELECT caller, endpoint, reason FROM access_log WHERE target_case_id = ?",
        (case_id,),
    )
    access_rows = cursor.fetchall()
    assert len(access_rows) >= 1
    assert any(r["reason"] in ("token_case_closed", "target_case_closed") for r in access_rows)

    # 6. CASE-3: Direct append_and_project on closed case is frozen and raises PermissionError
    with pytest.raises(PermissionError) as exc_info:
        append_and_project(
            conn=conn,
            case_id=case_id,
            event_type=EventType.AGENT_ACTION,
            actor="orchestrator",
            payload={"action": "test"},
        )
    assert "is CLOSED; ledger is frozen" in str(exc_info.value)
