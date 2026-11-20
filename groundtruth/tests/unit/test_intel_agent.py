"""Unit Test: IntelAgent.

Enforces:
- FR-5: Operates under contract 'intel_agent'.
- INV-5: Identity bound to case-scoped token.
- CASE-4: Tool actions recorded via /actions.
- Proposes intel_match facts with advisory evidence.
"""

from fastapi.testclient import TestClient

from groundtruth.agents.intel_agent import IntelAgent
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.projector import load_case_projection


def test_intel_agent_investigation_fixture_2() -> None:
    """Run IntelAgent on Fixture 2 and verify admitted intel_match in projections."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # 1. Open case with Fixture 2 trigger
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_2_dep_version_mismatch"}},
    )
    assert res.status_code == 200
    data = res.json()
    case_id = data["case_id"]
    intel_token = data["tokens"]["intel_agent"]

    # 2. Run IntelAgent
    agent = IntelAgent(client=client, token=intel_token, case_id=case_id)
    results = agent.investigate()

    assert len(results) >= 1
    match_verdict = results[0]
    assert match_verdict["verdict"] == GateVerdict.ADMIT.value
    assert match_verdict["own_trust"] == 0.70  # Document base trust

    # 3. Verify AGENT_ACTION event in ledger
    cursor = conn.cursor()
    cursor.execute(
        "SELECT event_type, actor, payload FROM events WHERE case_id = ? AND event_type = ?",
        (case_id, EventType.AGENT_ACTION.value),
    )
    actions = cursor.fetchall()
    assert len(actions) >= 1
    actors = [a["actor"] for a in actions]
    assert "intel_agent" in actors

    # 4. Verify fact in projection tables
    state = load_case_projection(conn, case_id)
    admitted_facts = list(state.facts.values())
    assert len(admitted_facts) >= 1
    fact = admitted_facts[0]
    assert fact.type == "intel_match"
    assert fact.status == "ACTIVE"
    assert fact.own_trust == 0.70
    assert "urllib3" in str(fact.value)
