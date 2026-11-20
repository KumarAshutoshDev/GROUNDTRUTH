"""Unit Test: RepoAgent.

Enforces:
- FR-5: Operates under contract 'repo_agent'.
- INV-5: Identity bound to case-scoped token.
- INV-7: Proposes inferences referencing valid parent facts in derived_from.
- CASE-1: Conclusion pointer in cases projection is set to the admitted cicd_root_cause.
"""

from fastapi.testclient import TestClient

from groundtruth.agents.log_agent import LogAgent
from groundtruth.agents.repo_agent import RepoAgent
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import GateVerdict
from groundtruth.core.projector import load_case_projection


def test_repo_agent_investigation_fixture_1() -> None:
    """Run LogAgent then RepoAgent on Fixture 1 and verify root cause inference."""
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
    tokens = data["tokens"]
    log_token = tokens["log_agent"]
    repo_token = tokens["repo_agent"]

    # 2. LogAgent investigates and admits log_anomaly
    log_agent = LogAgent(client=client, token=log_token, case_id=case_id)
    log_results = log_agent.investigate()
    assert len(log_results) >= 1
    assert log_results[0]["verdict"] == GateVerdict.ADMIT.value
    anomaly_fact_id = log_results[0]["fact_id"]

    # 3. RepoAgent investigates: reads log_anomaly, proposes commit_change, and proposes root cause
    repo_agent = RepoAgent(client=client, token=repo_token, case_id=case_id)
    repo_results = repo_agent.investigate()

    assert len(repo_results) >= 2
    commit_verdict = repo_results[0]
    assert commit_verdict["verdict"] == GateVerdict.ADMIT.value
    commit_fact_id = commit_verdict["fact_id"]

    cause_verdict = repo_results[1]
    assert cause_verdict["verdict"] == GateVerdict.ADMIT.value
    cause_fact_id = cause_verdict["fact_id"]

    # 4. Verify lineage in projection tables (INV-7)
    state = load_case_projection(conn, case_id)
    cause_fact = state.facts.get(cause_fact_id)
    assert cause_fact is not None
    assert cause_fact.type == "cicd_root_cause"
    assert cause_fact.status == "ACTIVE"
    assert anomaly_fact_id in cause_fact.derived_from
    assert commit_fact_id in cause_fact.derived_from

    # 5. Verify CASE-1: case conclusion pointer is set to this conclusion
    assert state.case is not None
    assert state.case.conclusion_fact_id == cause_fact_id
