"""Invariant test verifying INV-7: Provenance or rejection.

Proves:
1. An agent_inference with empty derived_from is REJECTED.
2. Inferences referencing non-existent or non-ACTIVE parents are REJECTED.
3. Inferences referencing parents below T_cite are REJECTED.
4. Derivation cycles are REJECTED.
5. Non-inference facts without evidence_ref are REJECTED.
"""

from pathlib import Path

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.gate import FactProposal, evaluate_proposal
from groundtruth.core.pack import load_pack, seed_contracts
from groundtruth.core.projector import append_and_project


def setup_gate_test() -> tuple:
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    seed_contracts(conn, pack)

    case_id = "case_provenance_test"
    append_and_project(
        conn,
        case_id,
        EventType.CASE_OPENED,
        "system",
        {"domain_pack": "cicd", "trigger": {}},
    )

    adapter = MockFixtureLLMAdapter()
    return conn, case_id, pack, adapter


def test_empty_derived_from_rejected() -> None:
    conn, case_id, pack, adapter = setup_gate_test()

    proposal = FactProposal(
        type="cicd_root_cause",
        value={"root_cause": "unsubstantiated guess"},
        source="repo_agent",
        source_type="agent_inference",
        derived_from=[],  # INV-7 violation
    )

    res = evaluate_proposal(conn, case_id, "repo_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "provenance_violation" in res.reason


def test_nonexistent_parent_rejected() -> None:
    conn, case_id, pack, adapter = setup_gate_test()

    proposal = FactProposal(
        type="cicd_root_cause",
        value={"root_cause": "bad parent pointer"},
        source="repo_agent",
        source_type="agent_inference",
        derived_from=["fact_does_not_exist"],
    )

    res = evaluate_proposal(conn, case_id, "repo_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "parent 'fact_does_not_exist' does not exist" in res.reason


def test_parent_below_t_cite_rejected() -> None:
    conn, case_id, pack, adapter = setup_gate_test()

    # Pre-insert a weak parent whose effective trust is 0.40 (below T_cite 0.50)
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_weak_parent",
                "type": "log_anomaly",
                "source": "log",
                "source_type": "tool_output",
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.40,
            "effective_trust": 0.40,
        },
    )

    proposal = FactProposal(
        type="cicd_root_cause",
        value={"root_cause": "built on weak foundation"},
        source="repo_agent",
        source_type="agent_inference",
        derived_from=["fact_weak_parent"],
    )

    res = evaluate_proposal(conn, case_id, "repo_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "below T_cite" in res.reason


def test_cycle_in_derivation_rejected() -> None:
    conn, case_id, pack, adapter = setup_gate_test()

    # Insert fact A derived from nothing
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_a",
                "type": "log_anomaly",
                "source": "log",
                "source_type": "tool_output",
                "derived_from": [],
                "evidence_ref": "log_1",
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
        },
    )

    # Insert fact B derived from fact A
    append_and_project(
        conn,
        case_id,
        EventType.GATE_VERDICT,
        "gate",
        {
            "fact": {
                "fact_id": "fact_b",
                "type": "commit_change",
                "source": "repo",
                "source_type": "tool_output",
                "derived_from": ["fact_a"],
                "evidence_ref": "diff_1",
            },
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
        },
    )

    # Now attempt to admit fact_a with derived_from = ["fact_b"] -> cycle A -> B -> A!
    proposal = FactProposal(
        fact_id="fact_a",
        type="cicd_root_cause",
        value={"root_cause": "circular reasoning"},
        source="repo_agent",
        source_type="agent_inference",
        derived_from=["fact_b"],
    )

    res = evaluate_proposal(conn, case_id, "repo_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "cycle detected" in res.reason


def test_missing_evidence_ref_on_tool_output_rejected() -> None:
    conn, case_id, pack, adapter = setup_gate_test()

    proposal = FactProposal(
        type="log_anomaly",
        value={"message": "Unproven error"},
        source="log_agent",
        source_type="tool_output",
        evidence_ref=None,  # Missing evidence_ref on tool_output
    )

    res = evaluate_proposal(conn, case_id, "log_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "evidence_violation" in res.reason
