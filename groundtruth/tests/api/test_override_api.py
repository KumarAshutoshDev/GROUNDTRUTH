"""API integration tests for Human Administrative Override endpoint (Task 33, SEC-3).

Enforces:
- SEC-3: Reserved 'human' role token required. Agent tokens return 403 Forbidden.
- INV-9: Manual un-tainting (RESTORE_ACTIVE) returns tainted facts to ACTIVE.
- Auditability: Reason is strictly mandatory (422 if empty).
- FORCE_RETRACT and ADJUST_TRUST actions.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.api.propose import get_verifier_adapter
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict, SourceType
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project
from groundtruth.core.taint import propagate_taint


@pytest.fixture
def override_api_env() -> tuple[TestClient, sqlite3.Connection, str, dict[str, str]]:
    conn = get_connection(":memory:")
    init_db(conn)

    adapter = MockFixtureLLMAdapter()
    app = create_app(db_conn=conn)
    app.dependency_overrides[get_verifier_adapter] = lambda: adapter

    client = TestClient(app)

    resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"service": "auth-service"}},
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
    )
    assert resp.status_code == 200
    data = resp.json()
    case_id = data["case_id"]
    tokens = data["tokens"]

    return client, conn, case_id, tokens


def test_override_security_and_restore_flow(override_api_env: tuple) -> None:
    client, conn, case_id, tokens = override_api_env
    pack = load_pack(Path("groundtruth/packs/cicd"))

    agent_token = tokens["log_agent"]
    human_token = tokens["human"]

    # 1. Seed root premise and child inference
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_premise",
                "type": "log_anomaly",
                "value": {"error": "connection timeout"},
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
                "fact_id": "fact_child",
                "type": "commit_change",
                "value": {"sha": "1234abcd"},
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
                "derived_from": ["fact_premise"],
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.85,
            "effective_trust": 0.85,
        },
    )

    # 2. Taint fact_child
    propagate_taint(conn, case_id, "fact_premise", pack=pack)

    # 3. Agent token attempting override -> 403 Forbidden (SEC-3)
    resp_agent = client.post(
        f"/cases/{case_id}/override",
        json={
            "fact_id": "fact_child",
            "action": "RESTORE_ACTIVE",
            "reason": "Agent wants to un-taint its own inference",
        },
        headers={"Authorization": f"Bearer {agent_token}"},
    )
    assert resp_agent.status_code == 403
    assert "SEC-3" in resp_agent.json()["detail"]

    # 4. Human override with empty reason -> 422 Unprocessable Entity
    resp_empty_reason = client.post(
        f"/cases/{case_id}/override",
        json={
            "fact_id": "fact_child",
            "action": "RESTORE_ACTIVE",
            "reason": "   ",
        },
        headers={"Authorization": f"Bearer {human_token}"},
    )
    assert resp_empty_reason.status_code == 422

    # 5. Human override restoring fact_child to ACTIVE (INV-9)
    resp_human = client.post(
        f"/cases/{case_id}/override",
        json={
            "fact_id": "fact_child",
            "action": "RESTORE_ACTIVE",
            "reason": "Verified commit independently in staging environment",
            "own_trust": 0.95,
        },
        headers={"Authorization": f"Bearer {human_token}"},
    )
    assert resp_human.status_code == 200, resp_human.text
    data = resp_human.json()
    assert data["fact_id"] == "fact_child"
    assert data["status"] == "ACTIVE"
    assert data["own_trust"] == 0.95


def test_override_force_retract_and_adjust_trust(override_api_env: tuple) -> None:
    client, conn, case_id, tokens = override_api_env
    human_token = tokens["human"]

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_trust_test",
                "type": "log_anomaly",
                "value": {"error": "disk pressure"},
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "own_trust": 0.8,
            "effective_trust": 0.8,
        },
    )

    # ADJUST_TRUST
    adj_resp = client.post(
        f"/cases/{case_id}/override",
        json={
            "fact_id": "fact_trust_test",
            "action": "ADJUST_TRUST",
            "reason": "Calibrated based on sensor confidence",
            "own_trust": 0.92,
        },
        headers={"Authorization": f"Bearer {human_token}"},
    )
    assert adj_resp.status_code == 200
    assert adj_resp.json()["own_trust"] == 0.92

    # FORCE_RETRACT
    ret_resp = client.post(
        f"/cases/{case_id}/override",
        json={
            "fact_id": "fact_trust_test",
            "action": "FORCE_RETRACT",
            "reason": "Sensor reported false alarm",
        },
        headers={"Authorization": f"Bearer {human_token}"},
    )
    assert ret_resp.status_code == 200
    assert ret_resp.json()["status"] == "RETRACTED"
    assert ret_resp.json()["effective_trust"] == 0.0
