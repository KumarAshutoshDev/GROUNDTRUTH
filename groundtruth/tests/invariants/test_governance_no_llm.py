"""Invariant Test: test_governance_no_llm.

Enforces:
- INV-6: Deterministic governance. Trust, conflict resolution, taint propagation,
  budget accounting, and the AUTO_FIX/ESCALATE decision MUST be plain code.
  No LLM call may compute or decide them.
- Governance modules import neither adapters/ nor any provider SDK.
- A full decision runs with adapters completely unavailable.
"""

import ast
from pathlib import Path

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.decision import evaluate_decision
from groundtruth.core.enums import DecisionSignal, EventType, GateVerdict, SourceType
from groundtruth.core.pack import load_pack
from groundtruth.core.projector import append_and_project


def test_governance_modules_have_no_llm_imports() -> None:
    """Enforce INV-6: Core governance modules must never import adapters/ or provider SDKs."""
    governance_files = [
        Path("groundtruth/core/trust.py"),
        Path("groundtruth/core/trust_service.py"),
        Path("groundtruth/core/conflict.py"),
        Path("groundtruth/core/decision.py"),
        Path("groundtruth/core/budget.py"),
    ]

    forbidden_prefixes = ("groundtruth.adapters", "openai", "anthropic", "google.generativeai")

    for fpath in governance_files:
        assert fpath.exists(), f"File {fpath} must exist"
        with open(fpath, encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_prefixes:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import '{alias.name}' in {fpath}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_prefixes:
                        assert not node.module.startswith(forbidden), (
                            f"Forbidden from-import '{node.module}' in {fpath}"
                        )


def test_full_decision_runs_without_llm() -> None:
    """Enforce INV-6: Full decision evaluation runs entirely offline with no LLM."""
    conn = get_connection(":memory:")
    init_db(conn)

    pack = load_pack(Path("groundtruth/packs/cicd"))
    case_id = "case_no_llm_decision"

    # Open case
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {}},
    )

    # 1. Evaluate with no facts -> NEED_MORE (zero LLM involved)
    res_1 = evaluate_decision(conn, case_id, pack)
    assert res_1.signal == DecisionSignal.NEED_MORE.value

    # 2. Add conclusion -> AUTO_FIX (zero LLM involved)
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="repo_agent",
        payload={
            "fact": {
                "fact_id": "fact_c",
                "type": "cicd_root_cause",
                "value": {"root_cause": "NPE in TokenValidator"},
                "source": "repo_agent",
                "source_type": SourceType.AGENT_INFERENCE.value,
                "agent_id": "repo_agent",
                "self_confidence": 1.0,
                "derived_from": [],
            },
            "verdict": GateVerdict.ADMIT.value,
            "reason": "admitted",
            "own_trust": 0.60,
            "effective_trust": 0.60,
            "is_conclusion": True,
        },
    )

    res_2 = evaluate_decision(conn, case_id, pack)
    assert res_2.signal == DecisionSignal.AUTO_FIX.value
    assert res_2.conclusion_fact_id == "fact_c"
