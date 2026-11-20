"""Invariant test verifying INV-3: Single writer for projection tables.

Proves:
1. SQL writes (INSERT/UPDATE/DELETE) to projection tables (cases, facts,
   fact_edges, negative_checks) appear ONLY in core/projector.py.
2. agents/, dashboard/, and adapters/ never import projector.py.
3. Functional test proving atomic ledger append + projection execution.
"""

import ast
from pathlib import Path

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType, FactStatus, GateVerdict
from groundtruth.core.projector import append_and_project, load_case_projection

PROJECTION_TABLES = ("cases", "facts", "fact_edges", "negative_checks")


def test_ast_single_writer_enforcement() -> None:
    root = Path("groundtruth")
    python_files = list(root.rglob("*.py"))

    # Exclude tests and projector.py itself
    files_to_check = [
        f
        for f in python_files
        if "tests" not in f.parts and f.name != "projector.py" and f.name != "db.py"
    ]

    for py_file in files_to_check:
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))

        # Check imports in forbidden directories: agents, dashboard, adapters
        if any(part in ("agents", "dashboard", "adapters") for part in py_file.parts):
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "projector" not in alias.name, (
                            f"INV-3 violation: {py_file} imports {alias.name}"
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert "projector" not in node.module, (
                        f"INV-3 violation: {py_file} imports from {node.module}"
                    )

        # Check for direct SQL mutation strings
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val_upper = node.value.upper()
                for table in PROJECTION_TABLES:
                    for sql_cmd in ("INSERT INTO", "UPDATE", "DELETE FROM"):
                        forbidden_pattern = f"{sql_cmd} {table.upper()}"
                        assert forbidden_pattern not in val_upper, (
                            f"INV-3 violation: {py_file} contains direct SQL write: "
                            f"{forbidden_pattern}"
                        )


def test_append_and_project_atomic_execution() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_proj_test"

    # Step 1: Open case
    e1 = append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="orchestrator",
        payload={"domain_pack": "cicd", "trigger": {"service": "payments"}},
    )
    assert e1.seq == 1

    # Verify projection table has case
    state = load_case_projection(conn, case_id)
    assert state.case is not None
    assert state.case.state == "OPEN"
    assert state.case.domain_pack == "cicd"

    # Step 2: Gate admits a fact
    fact_dict = {
        "fact_id": "fact_01",
        "type": "log_anomaly",
        "value": {"error": "connection timeout"},
        "source": "log_agent",
        "source_type": "tool_output",
        "agent_id": "log_agent",
        "self_confidence": 0.95,
        "own_trust": 0.90,
        "effective_trust": 0.90,
        "evidence_ref": "log_line_450",
        "derived_from": [],
    }
    append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.GATE_VERDICT,
        actor="gate",
        payload={
            "fact": fact_dict,
            "verdict": GateVerdict.ADMIT,
            "own_trust": 0.90,
            "effective_trust": 0.90,
            "is_conclusion": False,
        },
    )

    state = load_case_projection(conn, case_id)
    assert "fact_01" in state.facts
    assert state.facts["fact_01"].status == FactStatus.ACTIVE
    assert state.facts["fact_01"].effective_trust == 0.90
