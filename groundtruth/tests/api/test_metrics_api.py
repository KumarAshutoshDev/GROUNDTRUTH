"""API integration tests for Metrics & Benchmark Accounting endpoint (Task 35).

Enforces:
- CLAIM-2: Measured numbers only.
- CLAIM-3: Sample size and baseline definition included.
- DASH-4: Side-by-side comparison with baseline run.
- Verification: Accurately compute redundant call counts from mock actions.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from groundtruth.api.routes import create_app
from groundtruth.core.budget import record_agent_action
from groundtruth.core.db import get_connection, init_db


@pytest.fixture
def metrics_api_env() -> tuple[TestClient, sqlite3.Connection, str]:
    conn = get_connection(":memory:")
    init_db(conn)

    app = create_app(db_conn=conn)
    client = TestClient(app)

    resp = client.post(
        "/cases",
        json={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1_auth_refactor"}},
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
    )
    assert resp.status_code == 200
    case_id = resp.json()["case_id"]

    return client, conn, case_id


def test_metrics_accurate_redundancy_and_accounting(metrics_api_env: tuple) -> None:
    client, conn, case_id = metrics_api_env

    # Action 1: unique tool call
    record_agent_action(
        conn=conn,
        case_id=case_id,
        actor="log_agent",
        tool="k8s_scanner",
        args_hash="hash_pod_1",
        result_hash="res_1",
        tokens_in=100,
        tokens_out=200,
    )

    # Action 2: redundant tool call (same tool and args_hash)
    record_agent_action(
        conn=conn,
        case_id=case_id,
        actor="log_agent",
        tool="k8s_scanner",
        args_hash="hash_pod_1",
        result_hash="res_1",
        tokens_in=100,
        tokens_out=200,
    )

    # Action 3: another unique tool call
    record_agent_action(
        conn=conn,
        case_id=case_id,
        actor="repo_agent",
        tool="git_diff",
        args_hash="hash_sha_1",
        result_hash="res_2",
        tokens_in=200,
        tokens_out=300,
    )

    # Action 4: verifier action (verifier tool calls are excluded from tool_calls count)
    record_agent_action(
        conn=conn,
        case_id=case_id,
        actor="verifier",
        tool="verifier",
        args_hash="hash_claim_1",
        result_hash="res_3",
        tokens_in=50,
        tokens_out=50,
    )

    # Query metrics endpoint via both paths
    for path in (f"/metrics/{case_id}", f"/cases/{case_id}/metrics"):
        resp = client.get(path)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["case_id"] == case_id

        gt = data["groundtruth"]
        # Exactly 3 non-verifier tool calls
        assert gt["tool_calls"] == 3
        # Exactly 1 duplicate tool call
        assert gt["duplicate_tool_calls"] == 1
        # Total tokens = 100+200 + 100+200 + 200+300 + 50+50 = 1200
        assert gt["total_tokens"] == 1200
        assert gt["tokens_in"] == 450
        assert gt["tokens_out"] == 750

        # Baseline comparison
        base = data["baseline"]
        assert base["tool_calls"] > 0
        assert base["duplicate_tool_calls"] > 0
        assert base["total_tokens"] > 0

        # Reduction percentages dynamically derived from measured baseline
        b_calls, g_calls = base["tool_calls"], gt["tool_calls"]
        expected_tool_pct = round(((b_calls - g_calls) / b_calls) * 100, 1)

        b_dups, g_dups = base["duplicate_tool_calls"], gt["duplicate_tool_calls"]
        expected_dup_pct = round(((b_dups - g_dups) / b_dups) * 100, 1)

        b_tok, g_tok = base["total_tokens"], gt["total_tokens"]
        expected_token_pct = round(((b_tok - g_tok) / b_tok) * 100, 1)

        assert data["tool_call_reduction_pct"] == expected_tool_pct
        assert data["redundant_call_reduction_pct"] == expected_dup_pct
        assert data["token_reduction_pct"] == expected_token_pct

        # Auditability metadata (CLAIM-3, DASH-4)
        assert data["sample_size"] in (5, 15)
        assert "FIX-5" in data["baseline_definition"]
