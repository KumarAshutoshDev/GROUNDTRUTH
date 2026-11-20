"""Unit tests verifying Write Gate pipeline execution and verdict logging."""

import json
from pathlib import Path

from groundtruth.adapters.llm import MockFixtureLLMAdapter
from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, GateVerdict
from groundtruth.core.gate import FactProposal, evaluate_proposal
from groundtruth.core.pack import load_pack, seed_contracts
from groundtruth.core.projector import append_and_project


def setup_gate() -> tuple:
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    seed_contracts(conn, pack)

    case_id = "case_gate_unit"
    append_and_project(
        conn,
        case_id,
        EventType.CASE_OPENED,
        "system",
        {"domain_pack": "cicd", "trigger": {}},
    )

    adapter = MockFixtureLLMAdapter()
    return conn, case_id, pack, adapter


def test_gate_admit_valid_fact() -> None:
    conn, case_id, pack, adapter = setup_gate()

    proposal = FactProposal(
        type="log_anomaly",
        value={"message": "ConnectionRefusedError: port 5432"},
        source="log_agent",
        source_type="tool_output",
        evidence_ref="log_line_99",
    )

    res = evaluate_proposal(conn, case_id, "log_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.ADMIT
    assert res.own_trust == 0.90
    assert res.effective_trust == 0.90
    assert "admitted" in res.reason


def test_gate_reject_out_of_contract() -> None:
    conn, case_id, pack, adapter = setup_gate()

    # log_agent contract does not permit writing 'cicd_root_cause'
    proposal = FactProposal(
        type="cicd_root_cause",
        value={"cause": "spoofed conclusion"},
        source="log_agent",
        source_type="agent_inference",
        derived_from=["any"],
    )

    res = evaluate_proposal(conn, case_id, "log_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.REJECT
    assert "contract_violation" in res.reason


def test_gate_quarantine_verifier_refuted() -> None:
    conn, case_id, pack, adapter = setup_gate()

    adapter.set_response(
        "invented",
        json.dumps(
            {
                "verdict": "REFUTED",
                "rationale": "Evidence does not show OOM killer in action.",
                "evidence_quotes": [],
            }
        ),
    )

    proposal = FactProposal(
        type="log_anomaly",
        value={"message": "invented OOM claim"},
        source="log_agent",
        source_type="tool_output",
        evidence_ref="build_log.txt",
    )

    res = evaluate_proposal(conn, case_id, "log_agent", proposal, pack, adapter)
    assert res.verdict == GateVerdict.QUARANTINE
    assert "verifier_quarantine" in res.reason
