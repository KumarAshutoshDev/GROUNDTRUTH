"""API integration tests for negative knowledge query and record endpoints (Task 31).

Enforces:
- POST /cases/{id}/negative: records negative check through Write Gate (INV-3, F6).
- POST /cases/{id}/negative/query: verifies scope and window coverage (NEG-1..3).
- Verification: record negative OOM check for 12 pods; query for 12 pods returns COVERED,
  query for 13th pod returns NOT_COVERED:scope_mismatch.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.api.negative import get_verifier_adapter
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db


@pytest.fixture
def negative_api_env() -> tuple[TestClient, sqlite3.Connection, str, dict[str, str]]:
    conn = get_connection(":memory:")
    init_db(conn)

    adapter = MockFixtureLLMAdapter()
    app = create_app(db_conn=conn)
    app.dependency_overrides[get_verifier_adapter] = lambda: adapter

    client = TestClient(app)

    # Open case
    resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"service": "worker-pool"}},
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
    )
    assert resp.status_code == 200
    data = resp.json()
    case_id = data["case_id"]
    tokens = data["tokens"]

    return client, conn, case_id, tokens


def test_negative_record_and_query_flow(negative_api_env: tuple) -> None:
    client, _, case_id, tokens = negative_api_env
    log_token = tokens["log_agent"]
    headers = {"Authorization": f"Bearer {log_token}"}

    pods_12 = [f"worker-pod-{i}" for i in range(1, 13)]

    # 1. Record negative OOM check for 12 pods
    record_payload = {
        "check_type": "oom_killed",
        "scope": pods_12,
        "window_start": "2026-11-19T10:00:00Z",
        "window_end": "2026-11-19T11:00:00Z",
        "evidence_ref": "k8s_events:log_scanner_run_99",
        "self_confidence": 1.0,
    }
    rec_resp = client.post(
        f"/cases/{case_id}/negative",
        json=record_payload,
        headers=headers,
    )
    assert rec_resp.status_code == 200, rec_resp.text
    rec_data = rec_resp.json()
    assert rec_data["verdict"] == "ADMIT"
    assert rec_data["fact_id"] != ""

    # 2. Query for 12 pods (or subset) -> COVERED
    query_12 = {
        "check_type": "oom_killed",
        "scope": pods_12,
        "window_start": "2026-11-19T10:15:00Z",
        "window_end": "2026-11-19T10:45:00Z",
    }
    q12_resp = client.post(
        f"/cases/{case_id}/negative/query",
        json=query_12,
        headers=headers,
    )
    assert q12_resp.status_code == 200
    q12_data = q12_resp.json()
    assert q12_data["verdict"] == "COVERED"
    assert q12_data["reason"] == "COVERED"
    assert q12_data["matching_fact_id"] == rec_data["fact_id"]

    # 3. Query for 13th pod -> NOT_COVERED:scope_mismatch
    query_13 = {
        "check_type": "oom_killed",
        "scope": pods_12 + ["worker-pod-13"],
        "window_start": "2026-11-19T10:15:00Z",
        "window_end": "2026-11-19T10:45:00Z",
    }
    q13_resp = client.post(
        f"/cases/{case_id}/negative/query",
        json=query_13,
        headers=headers,
    )
    assert q13_resp.status_code == 200
    q13_data = q13_resp.json()
    assert q13_data["verdict"] == "NOT_COVERED"
    assert q13_data["reason"] == "scope_mismatch"
    assert q13_data["status"] == "NOT_COVERED:scope_mismatch"


def test_negative_api_window_mismatch(negative_api_env: tuple) -> None:
    client, _, case_id, tokens = negative_api_env
    log_token = tokens["log_agent"]
    headers = {"Authorization": f"Bearer {log_token}"}

    # Record check
    rec_resp = client.post(
        f"/cases/{case_id}/negative",
        json={
            "check_type": "oom_killed",
            "scope": ["worker-pod-1"],
            "window_start": "2026-11-19T10:00:00Z",
            "window_end": "2026-11-19T11:00:00Z",
            "evidence_ref": "k8s_events:log_scan",
        },
        headers=headers,
    )
    assert rec_resp.status_code == 200, rec_resp.text
    assert rec_resp.json()["verdict"] == "ADMIT", rec_resp.json()

    # Query with later window
    q_later = {
        "check_type": "oom_killed",
        "scope": ["worker-pod-1"],
        "window_start": "2026-11-19T10:30:00Z",
        "window_end": "2026-11-19T11:30:00Z",
    }
    resp = client.post(
        f"/cases/{case_id}/negative/query",
        json=q_later,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "NOT_COVERED"
    assert data["reason"] == "window_mismatch"
    assert data["status"] == "NOT_COVERED:window_mismatch"
