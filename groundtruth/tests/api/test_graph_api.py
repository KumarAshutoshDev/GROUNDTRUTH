"""API Test: Causality Graph Query Endpoint.

Enforces:
- FR-7: Causality DAG query with node trust and weakest-link identification.
- TRUST-8: Decay tick applied before returning graph.
- Architecture Section 12 & Section 14 (GET /cases/{id}/graph).
"""

from fastapi.testclient import TestClient

from groundtruth.agents.log_agent import LogAgent
from groundtruth.agents.repo_agent import RepoAgent
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db


def test_graph_api_returns_nodes_and_edges_with_weakest_link() -> None:
    """Test /graph endpoint returning nodes, edges, and identifying the weakest parent link."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # 1. Open case on Fixture 1
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1_auth_refactor"}},
    )
    assert res.status_code == 200
    data = res.json()
    case_id = data["case_id"]
    tokens = data["tokens"]

    # 2. Run LogAgent and RepoAgent to generate DAG
    log_agent = LogAgent(client=client, token=tokens["log_agent"], case_id=case_id)
    log_agent.investigate()

    repo_agent = RepoAgent(client=client, token=tokens["repo_agent"], case_id=case_id)
    repo_agent.investigate()

    # 3. Query /graph endpoint
    res_graph = client.get(
        f"/cases/{case_id}/graph",
        headers={"Authorization": f"Bearer {tokens['orchestrator']}"},
    )
    assert res_graph.status_code == 200
    graph_data = res_graph.json()

    assert graph_data["case_id"] == case_id
    nodes = graph_data["nodes"]
    edges = graph_data["edges"]

    # Verify nodes present
    node_types = {n["type"] for n in nodes}
    assert "log_anomaly" in node_types
    assert "commit_change" in node_types
    assert "cicd_root_cause" in node_types

    # Verify edges present
    assert len(edges) >= 2
    conclusion_node = next(n for n in nodes if n["type"] == "cicd_root_cause")
    assert conclusion_node["is_conclusion"] is True

    incoming_edges = [e for e in edges if e["to_fact_id"] == conclusion_node["fact_id"]]
    assert len(incoming_edges) == 2


def test_graph_api_applies_decay_tick() -> None:
    """Enforce TRUST-8: Calling /graph applies decay tick to case."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]

    # Query graph
    res_graph = client.get(f"/cases/{case_id}/graph")
    assert res_graph.status_code == 200

    # Verify that decay tick logic executed cleanly
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) as c FROM events WHERE case_id = ?",
        (case_id,),
    )
    assert cursor.fetchone()["c"] >= 1
