"""Invariant Test: test_conclusion_pointer.

Enforces:
- CASE-1: The conclusion pointer is set only by the reducer, on an ADMIT
  GATE_VERDICT whose is_conclusion is true.
  QUARANTINED facts never become the conclusion.
- INV-2: Replay identical. Replaying ledger events 1..N reproduces the exact same
  conclusion pointer.
- Architecture Section 13: Orchestrator loop coordinates agents and transitions to CONCLUDED.
"""

from fastapi.testclient import TestClient

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.agents.orchestrator import Orchestrator
from groundtruth.api.propose import get_verifier_adapter
from groundtruth.api.routes import create_app
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import GateVerdict, SourceType
from groundtruth.core.projector import load_case_projection
from groundtruth.core.replay import replay_case


def test_quarantined_conclusion_never_sets_pointer() -> None:
    """Enforce CASE-1: QUARANTINED conclusion fact never sets cases.conclusion_fact_id."""
    conn = get_connection(":memory:")
    init_db(conn)

    refuted_json = (
        '{"verdict": "REFUTED", "rationale": "Claim contradicted by evidence", '
        '"evidence_quotes": []}'
    )
    failing_adapter = MockFixtureLLMAdapter({"unverified guess": refuted_json})

    app = create_app(conn)
    app.dependency_overrides[get_verifier_adapter] = lambda: failing_adapter
    client = TestClient(app)

    # 1. Open case
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"service": "checkout"}},
    )
    data = res.json()
    case_id = data["case_id"]
    repo_token = data["tokens"]["repo_agent"]
    auth_header = {"Authorization": f"Bearer {repo_token}"}

    # Seed an active parent fact so provenance check passes (INV-7)
    from groundtruth.core.projector import append_and_project

    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type="GATE_VERDICT",
        actor="log_agent",
        payload={
            "fact": {
                "fact_id": "fact_parent_1",
                "type": "log_anomaly",
                "value": {"error": "test failure"},
                "source": "log_agent",
                "source_type": SourceType.TOOL_OUTPUT.value,
                "agent_id": "log_agent",
                "self_confidence": 1.0,
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    # Propose conclusion type fact (cicd_root_cause) with valid parent
    res_prop = client.post(
        f"/cases/{case_id}/propose",
        headers=auth_header,
        json={
            "type": "cicd_root_cause",
            "value": {
                "root_cause": "unverified guess",
                "category": "code_defect",
                "fix_recommendation": "do nothing",
            },
            "source": "repo_agent",
            "source_type": SourceType.AGENT_INFERENCE.value,
            "derived_from": ["fact_parent_1"],
            "evidence_ref": "evidence string",
        },
    )
    assert res_prop.status_code == 200
    prop_data = res_prop.json()
    assert prop_data["verdict"] == GateVerdict.QUARANTINE.value

    # Verify CASE-1: conclusion_fact_id MUST be None
    state = load_case_projection(conn, case_id)
    assert state.case is not None
    assert state.case.conclusion_fact_id is None


def test_admitted_conclusion_sets_pointer_and_replays_identically() -> None:
    """Enforce CASE-1 & INV-2: ADMIT sets conclusion pointer and ledger replay reproduces it."""
    conn = get_connection(":memory:")
    init_db(conn)
    app = create_app(conn)
    client = TestClient(app)

    # 1. Open case with Fixture 1
    res = client.post(
        "/cases",
        headers={"X-Bootstrap-Key": "gt-dev-bootstrap-secret-2026"},
        json={"domain_pack": "cicd", "trigger": {"fixture_id": "fixture_1_auth_refactor"}},
    )
    data = res.json()
    case_id = data["case_id"]
    tokens = data["tokens"]

    # 2. Run Orchestrator loop
    orchestrator = Orchestrator(client=client, tokens=tokens, case_id=case_id)
    final_decision = orchestrator.run()

    assert final_decision["signal"] == "AUTO_FIX"
    conclusion_id = final_decision["conclusion_fact_id"]
    assert conclusion_id is not None

    # 3. Verify projection state
    state = load_case_projection(conn, case_id)
    assert state.case is not None
    assert state.case.state == "CONCLUDED"
    assert state.case.conclusion_fact_id == conclusion_id

    # 4. Verify INV-2: Pure replay reproduces identical conclusion pointer
    replayed = replay_case(conn, case_id)
    assert replayed.case is not None
    assert replayed.case.conclusion_fact_id == conclusion_id
    assert replayed.case.state == "CONCLUDED"
    assert replayed.case.concluded_at == state.case.concluded_at
