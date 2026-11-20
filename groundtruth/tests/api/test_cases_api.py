"""API integration tests for case lifecycle and time-travel inspection."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.projector import append_and_project


@pytest.fixture
def client_and_db() -> tuple[TestClient, sqlite3.Connection]:
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(db_conn=conn)
    return TestClient(app), conn


BOOTSTRAP_HEADERS = {"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"}


def test_create_and_get_case(client_and_db: tuple[TestClient, sqlite3.Connection]) -> None:
    client, _ = client_and_db
    # 1. Open a new case
    resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"pipeline_id": "pl-12345"}},
        headers=BOOTSTRAP_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["case_id"].startswith("case_")
    assert data["domain_pack"] == "cicd"
    assert data["state"] == "OPEN"
    assert data["conclusion_fact_id"] is None
    assert "tokens" in data
    assert "log_agent" in data["tokens"]
    assert "orchestrator" in data["tokens"]
    assert "human" in data["tokens"]

    case_id = data["case_id"]

    # 2. Get case summary
    get_resp = client.get(f"/cases/{case_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["case_id"] == case_id
    assert get_resp.json()["state"] == "OPEN"

    # 3. List cases (GET /cases)
    list_resp = client.get("/cases")
    assert list_resp.status_code == 200
    cases_list = list_resp.json()
    assert isinstance(cases_list, list)
    assert len(cases_list) >= 1
    assert any(c["case_id"] == case_id for c in cases_list)


def test_get_events_and_state_replay(
    client_and_db: tuple[TestClient, sqlite3.Connection],
) -> None:
    client, conn = client_and_db
    # Open case
    open_resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"run": 1}},
        headers=BOOTSTRAP_HEADERS,
    )
    case_id = open_resp.json()["case_id"]

    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "f_1",
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
                "fact_id": "f_2",
                "type": "commit_change",
                "source": "repo",
                "source_type": "tool_output",
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
        },
    )

    # 1. Query events up to seq 2
    events_resp = client.get(f"/cases/{case_id}/events?upto=2")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert len(events) == 2
    assert events[0]["seq"] == 1
    assert events[1]["seq"] == 2

    # 2. Query state at seq 1 (only case opened, 0 facts)
    state_at_1 = client.get(f"/cases/{case_id}/state?at=1").json()
    assert len(state_at_1["facts"]) == 0

    # 3. Query state at seq 2 (1 fact)
    state_at_2 = client.get(f"/cases/{case_id}/state?at=2").json()
    assert len(state_at_2["facts"]) == 1
    assert "f_1" in state_at_2["facts"]
    assert "f_2" not in state_at_2["facts"]

    # 4. Query current live state
    live_state = client.get(f"/cases/{case_id}/state").json()
    assert len(live_state["facts"]) == 2
    assert "f_1" in live_state["facts"]
    assert "f_2" in live_state["facts"]


def test_case_not_found(client_and_db: tuple[TestClient, sqlite3.Connection]) -> None:
    client, _ = client_and_db
    resp = client.get("/cases/case_nonexistent")
    assert resp.status_code == 404
