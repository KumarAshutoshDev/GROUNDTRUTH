"""Invariant Test: test_budget_exhausted.

Enforces:
- CASE-4: Usage derived exclusively from AGENT_ACTION events, never stored separately.
- Tool calls count events where actor != 'verifier'.
- Tokens count sum of tokens_in + tokens_out over all AGENT_ACTION events (including verifier).
- When a limit is reached, agent endpoints return BUDGET_EXHAUSTED (HTTP 429).
- INV-6: budget module does not import adapters or provider SDKs.
"""

import ast
import inspect
from pathlib import Path

from fastapi.testclient import TestClient

import groundtruth.core.budget as budget_module
from groundtruth.api.routes import create_app
from groundtruth.core.budget import calculate_budget_usage, record_agent_action
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.pack import load_pack


def test_budget_module_has_no_llm_imports() -> None:
    """Enforce INV-6: budget.py must never import adapters/ or provider SDKs."""
    source_file = inspect.getfile(budget_module)
    with open(source_file, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    forbidden_prefixes = ("groundtruth.adapters", "openai", "anthropic", "google.generativeai")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for forbidden in forbidden_prefixes:
                    assert not alias.name.startswith(forbidden), (
                        f"Forbidden import '{alias.name}' in budget.py"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for forbidden in forbidden_prefixes:
                    assert not node.module.startswith(forbidden), (
                        f"Forbidden from-import '{node.module}' in budget.py"
                    )


def test_budget_usage_calculation_from_ledger() -> None:
    """Enforce CASE-4: Usage is derived directly from AGENT_ACTION events."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "test-case-budget-1"

    # Initially zero usage
    usage = calculate_budget_usage(conn, case_id, pack)
    assert usage.tool_calls == 0
    assert usage.total_tokens == 0
    assert usage.is_exhausted is False

    # 1. Non-verifier action: counts as 1 tool call and consumes tokens
    record_agent_action(
        conn=conn,
        case_id=case_id,
        actor="log_agent",
        tool="kubectl_logs",
        args_hash="args_1",
        result_hash="res_1",
        tokens_in=500,
        tokens_out=200,
    )

    usage = calculate_budget_usage(conn, case_id, pack)
    assert usage.tool_calls == 1
    assert usage.tokens_in == 500
    assert usage.tokens_out == 200
    assert usage.total_tokens == 700
    assert usage.is_exhausted is False

    # 2. Verifier action: DOES NOT increment tool_calls, but DOES consume tokens (Architecture 4.6)
    record_agent_action(
        conn=conn,
        case_id=case_id,
        actor="verifier",
        tool="adversarial_verifier",
        args_hash="args_v1",
        result_hash="res_v1",
        tokens_in=300,
        tokens_out=100,
    )

    usage = calculate_budget_usage(conn, case_id, pack)
    assert usage.tool_calls == 1  # Still 1 because verifier is excluded from tool call count
    assert usage.tokens_in == 800
    assert usage.tokens_out == 300
    assert usage.total_tokens == 1100
    assert usage.is_exhausted is False


def test_tool_call_limit_exhaustion_returns_429() -> None:
    """Enforce CASE-4: Exceeding max_tool_calls triggers BUDGET_EXHAUSTED."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # Open case
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    assert res.status_code == 200
    data = res.json()
    case_id = data["case_id"]
    tokens = data["tokens"]
    log_agent_token = tokens["log_agent"]
    auth_header = {"Authorization": f"Bearer {log_agent_token}"}

    pack = load_pack(Path("groundtruth/packs/cicd"))
    max_tool_calls = pack.trust.budget.max_tool_calls  # 20 in cicd

    # Execute max_tool_calls actions
    for i in range(max_tool_calls):
        res = client.post(
            f"/cases/{case_id}/actions",
            headers=auth_header,
            json={
                "tool": "read_log",
                "args_hash": f"hash_{i}",
                "result_hash": f"res_{i}",
                "tokens_in": 10,
                "tokens_out": 10,
            },
        )
        assert res.status_code == 200

    # The 21st action MUST be rejected with HTTP 429 BUDGET_EXHAUSTED
    res_exceeded = client.post(
        f"/cases/{case_id}/actions",
        headers=auth_header,
        json={
            "tool": "read_log",
            "args_hash": "hash_extra",
            "result_hash": "res_extra",
            "tokens_in": 10,
            "tokens_out": 10,
        },
    )
    assert res_exceeded.status_code == 429
    assert "BUDGET_EXHAUSTED" in res_exceeded.json()["detail"]

    # Propose must also be rejected with HTTP 429 BUDGET_EXHAUSTED
    res_propose = client.post(
        f"/cases/{case_id}/propose",
        headers=auth_header,
        json={
            "type": "log_anomaly",
            "value": {"message": "CrashLoopBackOff"},
            "source": "log_agent",
            "source_type": "tool_output",
            "evidence_ref": "artifacts/logs/crash.log",
        },
    )
    assert res_propose.status_code == 429
    assert "BUDGET_EXHAUSTED" in res_propose.json()["detail"]


def test_token_limit_exhaustion_returns_429() -> None:
    """Enforce CASE-4: Exceeding max_tokens triggers BUDGET_EXHAUSTED."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # Open case
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    assert res.status_code == 200
    data = res.json()
    case_id = data["case_id"]
    tokens = data["tokens"]
    log_agent_token = tokens["log_agent"]
    auth_header = {"Authorization": f"Bearer {log_agent_token}"}

    pack = load_pack(Path("groundtruth/packs/cicd"))
    max_tokens = pack.trust.budget.max_tokens  # 100,000

    # 1. Record an action consuming all available tokens
    res = client.post(
        f"/cases/{case_id}/actions",
        headers=auth_header,
        json={
            "tool": "fetch_big_bundle",
            "args_hash": "hash_big",
            "result_hash": "res_big",
            "tokens_in": 50000,
            "tokens_out": 50000,
        },
    )
    assert res.status_code == 200
    assert res.json()["usage"]["total_tokens"] == max_tokens
    assert res.json()["usage"]["is_exhausted"] is True

    # 2. Subsequent action must be rejected with 429
    res_exceeded = client.post(
        f"/cases/{case_id}/actions",
        headers=auth_header,
        json={
            "tool": "read_log",
            "args_hash": "hash_after",
            "result_hash": "res_after",
            "tokens_in": 1,
            "tokens_out": 1,
        },
    )
    assert res_exceeded.status_code == 429
    assert "BUDGET_EXHAUSTED" in res_exceeded.json()["detail"]

    # 3. Propose must also be rejected with 429
    res_propose = client.post(
        f"/cases/{case_id}/propose",
        headers=auth_header,
        json={
            "type": "log_anomaly",
            "value": {"message": "CrashLoopBackOff"},
            "source": "log_agent",
            "source_type": "tool_output",
            "evidence_ref": "artifacts/logs/crash.log",
        },
    )
    assert res_propose.status_code == 429
    assert "BUDGET_EXHAUSTED" in res_propose.json()["detail"]
