"""Invariant test verifying SEC-5: Access denied attempts are logged correctly."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from groundtruth.api.auth import issue_case_tokens, resolve_caller
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType
from groundtruth.core.pack import load_pack, seed_contracts
from groundtruth.core.projector import append_and_project


def test_cross_case_access_denied_logged_to_token_case() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    seed_contracts(conn, pack)

    # Create Case A and Case B
    case_a = "case_alpha"
    case_b = "case_beta"
    append_and_project(
        conn, case_a, EventType.CASE_OPENED, "system", {"domain_pack": "cicd", "trigger": {}}
    )
    append_and_project(
        conn, case_b, EventType.CASE_OPENED, "system", {"domain_pack": "cicd", "trigger": {}}
    )

    tokens_a = issue_case_tokens(conn, case_a, pack)
    token_a = tokens_a["log_agent"]

    # Use Token A against Case B
    with pytest.raises(HTTPException) as exc_info:
        resolve_caller(
            conn=conn,
            target_case_id=case_b,
            endpoint_path="/cases/case_beta/read",
            authorization=f"Bearer {token_a}",
        )
    assert exc_info.value.status_code == 403

    # SEC-5: Verify ACCESS_DENIED event was appended to Case A's ledger
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT event_type, payload FROM events
        WHERE case_id = ? AND event_type = 'ACCESS_DENIED'
        """,
        (case_a,),
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    import json

    payload = json.loads(rows[0]["payload"])
    assert payload["attempted_case_id"] == case_b
    assert payload["reason"] == "cross_case_access_denied"


def test_unknown_token_logged_to_access_log() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_known"
    append_and_project(
        conn, case_id, EventType.CASE_OPENED, "system", {"domain_pack": "cicd", "trigger": {}}
    )

    # Use invalid token
    with pytest.raises(HTTPException) as exc_info:
        resolve_caller(
            conn=conn,
            target_case_id=case_id,
            endpoint_path=f"/cases/{case_id}/read",
            authorization="Bearer invalid_token_12345",
        )
    assert exc_info.value.status_code == 401

    # SEC-5: Unknown token must land in access_log table
    cursor = conn.cursor()
    cursor.execute("SELECT endpoint, reason FROM access_log WHERE target_case_id = ?", (case_id,))
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["endpoint"] == f"/cases/{case_id}/read"
    assert rows[0]["reason"] == "unknown_token"


def test_closed_case_token_expired_logged_to_access_log() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    seed_contracts(conn, pack)

    case_id = "case_closed_test"
    append_and_project(
        conn, case_id, EventType.CASE_OPENED, "system", {"domain_pack": "cicd", "trigger": {}}
    )
    tokens = issue_case_tokens(conn, case_id, pack)
    token = tokens["log_agent"]

    # Transition case to CLOSED
    append_and_project(
        conn,
        case_id,
        EventType.CASE_STATE_CHANGED,
        "orchestrator",
        {"from": "OPEN", "to": "CLOSED"},
    )

    # Use token on closed case
    with pytest.raises(HTTPException) as exc_info:
        resolve_caller(
            conn=conn,
            target_case_id=case_id,
            endpoint_path=f"/cases/{case_id}/read",
            authorization=f"Bearer {token}",
        )
    assert exc_info.value.status_code == 403

    # SEC-5: Closed case attempt lands in access_log
    cursor = conn.cursor()
    cursor.execute(
        "SELECT reason FROM access_log WHERE target_case_id = ?",
        (case_id,),
    )
    rows = cursor.fetchall()
    assert len(rows) >= 1
    assert any("closed" in row["reason"] for row in rows)
