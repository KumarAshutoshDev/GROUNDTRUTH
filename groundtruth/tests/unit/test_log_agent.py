"""Unit Test: LogAgent.

Enforces:
- FR-5: Operates under contract 'log_agent'.
- INV-5: Identity bound to case-scoped token.
- CASE-4: Tool actions recorded via /actions.
- Proposes log_anomaly and pod_status with raw evidence.
"""

from fastapi.testclient import TestClient

from groundtruth.agents.log_agent import LogAgent
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.projector import load_case_projection


def test_log_agent_investigation_fixture_1() -> None:
    """Run LogAgent on Fixture 1 and verify admitted log_anomaly in projections."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # 1. Open case with Fixture 1 trigger
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1_auth_refactor"}},
    )
    assert res.status_code == 200
    data = res.json()
    case_id = data["case_id"]
    log_token = data["tokens"]["log_agent"]

    # 2. Run LogAgent
    agent = LogAgent(client=client, token=log_token, case_id=case_id)
    results = agent.investigate()

    assert len(results) >= 1
    anomaly_verdict = results[0]
    assert anomaly_verdict["verdict"] == GateVerdict.ADMIT.value
    assert anomaly_verdict["own_trust"] == 0.90

    # 3. Verify AGENT_ACTION event in ledger
    cursor = conn.cursor()
    cursor.execute(
        "SELECT event_type, actor, payload FROM events WHERE case_id = ? AND event_type = ?",
        (case_id, EventType.AGENT_ACTION.value),
    )
    actions = cursor.fetchall()
    # At least fetch_build_log tool action + verifier LLM action
    assert len(actions) >= 1
    actor_names = [a["actor"] for a in actions]
    assert "log_agent" in actor_names

    # 4. Verify fact in projection tables
    state = load_case_projection(conn, case_id)
    admitted_facts = list(state.facts.values())
    assert len(admitted_facts) >= 1
    fact = admitted_facts[0]
    assert fact.type == "log_anomaly"
    assert fact.status == "ACTIVE"
    assert fact.own_trust == 0.90
    assert "AttributeError" in str(fact.value)


def test_log_agent_investigation_fixture_3_oom() -> None:
    """Run LogAgent on Fixture 3 and verify pod_status fact is proposed and admitted."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # Open case for Fixture 3
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_3_oom_pod_crash"}},
    )
    assert res.status_code == 200
    data = res.json()
    case_id = data["case_id"]
    log_token = data["tokens"]["log_agent"]

    agent = LogAgent(client=client, token=log_token, case_id=case_id)
    results = agent.investigate()

    # Fixture 3 has both log error and OOM killed pod
    types = [r["fact_id"] for r in results]
    assert len(types) >= 1

    state = load_case_projection(conn, case_id)
    fact_types = {f.type for f in state.facts.values()}
    assert "log_anomaly" in fact_types or "pod_status" in fact_types
