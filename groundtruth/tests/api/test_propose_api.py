"""API integration tests for /propose and /reverify endpoints."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.api.propose import get_verifier_adapter
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db


@pytest.fixture
def api_test_env() -> tuple[
    TestClient, sqlite3.Connection, str, dict[str, str], MockFixtureLLMAdapter
]:
    conn = get_connection(":memory:")
    init_db(conn)

    adapter = MockFixtureLLMAdapter()
    app = create_app(db_conn=conn)
    app.dependency_overrides[get_verifier_adapter] = lambda: adapter

    client = TestClient(app)

    # Open case
    resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"service": "auth"}},
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
    )
    assert resp.status_code == 200
    data = resp.json()
    case_id = data["case_id"]
    tokens = data["tokens"]

    return client, conn, case_id, tokens, adapter


def test_propose_valid_fact_admitted(api_test_env: tuple) -> None:
    client, _, case_id, tokens, _ = api_test_env
    log_token = tokens["log_agent"]

    proposal = {
        "type": "log_anomaly",
        "value": {"message": "NullPointerException in validator"},
        "source": "log_scanner",
        "source_type": "tool_output",
        "self_confidence": 0.95,
        "evidence_ref": "log_line_88",
    }

    resp = client.post(
        f"/cases/{case_id}/propose",
        json=proposal,
        headers={"Authorization": f"Bearer {log_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["verdict"] == "ADMIT"
    assert data["own_trust"] == 0.90
    assert data["effective_trust"] == 0.90
    assert data["fact_id"].startswith("fact_")


def test_propose_ungrounded_inference_rejected(api_test_env: tuple) -> None:
    client, _, case_id, tokens, _ = api_test_env
    repo_token = tokens["repo_agent"]

    # Inference without derived_from must be REJECTED (INV-7)
    proposal = {
        "type": "cicd_root_cause",
        "value": {"root_cause": "unsubstantiated guess"},
        "source": "repo_agent",
        "source_type": "agent_inference",
        "self_confidence": 0.8,
        "derived_from": [],
    }

    resp = client.post(
        f"/cases/{case_id}/propose",
        json=proposal,
        headers={"Authorization": f"Bearer {repo_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "REJECT"
    assert "provenance_violation" in data["reason"]


def test_propose_contract_violation_rejected(api_test_env: tuple) -> None:
    client, _, case_id, tokens, _ = api_test_env
    log_token = tokens["log_agent"]

    # log_agent cannot write 'cicd_root_cause'
    proposal = {
        "type": "cicd_root_cause",
        "value": {"root_cause": "unauthorized conclusion"},
        "source": "log_agent",
        "source_type": "agent_inference",
        "derived_from": ["any"],
    }

    resp = client.post(
        f"/cases/{case_id}/propose",
        json=proposal,
        headers={"Authorization": f"Bearer {log_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "REJECT"
    assert "contract_violation" in data["reason"]


def test_reverify_endpoint_overturn_and_role_restriction(api_test_env: tuple) -> None:
    client, _, case_id, tokens, adapter = api_test_env
    log_token = tokens["log_agent"]
    orch_token = tokens["orchestrator"]

    # 1. Admit a fact
    proposal = {
        "type": "log_anomaly",
        "value": {"message": "Memory leak detected"},
        "source": "log_scanner",
        "source_type": "tool_output",
        "evidence_ref": "log_line_105",
    }
    p_resp = client.post(
        f"/cases/{case_id}/propose",
        json=proposal,
        headers={"Authorization": f"Bearer {log_token}"},
    )
    fact_id = p_resp.json()["fact_id"]

    # 2. Agent token attempting reverify must be rejected 403 (SEC-7, REVERIFY-1)
    agent_rev = client.post(
        f"/cases/{case_id}/reverify",
        json={"fact_id": fact_id},
        headers={"Authorization": f"Bearer {log_token}"},
    )
    assert agent_rev.status_code == 403

    # 3. Configure mock adapter to overturn claim
    adapter.set_response(
        "Memory leak",
        json.dumps(
            {
                "verdict": "REFUTED",
                "rationale": "Log line 105 was actually normal GC collection cycle.",
                "evidence_quotes": [],
            }
        ),
    )

    # 4. Orchestrator calls reverify
    rev_resp = client.post(
        f"/cases/{case_id}/reverify",
        json={"fact_id": fact_id, "retract": True},
        headers={"Authorization": f"Bearer {orch_token}"},
    )
    assert rev_resp.status_code == 200, rev_resp.text
    rev_data = rev_resp.json()
    assert rev_data["overturned"] is True
    assert rev_data["status"] == "RETRACTED"
    assert rev_data["verifier_state"] == "DOWNGRADED"
