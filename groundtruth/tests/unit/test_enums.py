"""Unit tests verifying shared enums."""

from groundtruth.core.enums import (
    CaseState,
    DecisionSignal,
    EventType,
    FactStatus,
    GateVerdict,
    SourceType,
    VerifierState,
)


def test_case_states() -> None:
    expected = {"OPEN", "INVESTIGATING", "CONCLUDED", "CLOSED"}
    assert set(CaseState) == expected


def test_fact_statuses() -> None:
    expected = {"ACTIVE", "CONTESTED", "QUARANTINED", "RETRACTED", "TAINTED"}
    assert set(FactStatus) == expected


def test_source_types() -> None:
    expected = {"tool_output", "document", "agent_inference", "human_input"}
    assert set(SourceType) == expected


def test_verifier_states() -> None:
    expected = {"SUPPORTED", "NOT_SUPPORTED", "DOWNGRADED"}
    assert set(VerifierState) == expected


def test_gate_verdicts() -> None:
    expected = {"ADMIT", "QUARANTINE", "REJECT"}
    assert set(GateVerdict) == expected


def test_event_types() -> None:
    expected = {
        "CASE_OPENED",
        "CASE_STATE_CHANGED",
        "FACT_PROPOSED",
        "GATE_VERDICT",
        "TRUST_RECOMPUTED",
        "FACT_DOWNGRADED",
        "FACT_SUPERSEDED",
        "FACT_TAINTED",
        "CONFLICT_RAISED",
        "AGENT_ACTION",
        "HUMAN_OVERRIDE",
        "ACCESS_DENIED",
    }
    assert set(EventType) == expected


def test_decision_signals() -> None:
    expected = {"AUTO_FIX", "ESCALATE", "NEED_MORE"}
    assert set(DecisionSignal) == expected
