"""Unit tests verifying deterministic conflict resolution order (CONF-1, CONF-2)."""

from groundtruth.core.conflict import ConflictDecision, resolve_conflict
from groundtruth.core.models import FactModel


def make_fact(source_type: str, evidence_ref: str | None, created_at: str) -> FactModel:
    return FactModel(
        fact_id="fact_1",
        case_id="case_1",
        type="test_type",
        value={"status": "fail"},
        source="test",
        source_type=source_type,
        agent_id="test_agent",
        created_at=created_at,
        self_confidence=0.9,
        own_trust=0.9,
        effective_trust=0.9,
        evidence_ref=evidence_ref,
        status="ACTIVE",
        verifier_state="SUPPORTED",
    )


def test_rule_1_source_authority() -> None:
    existing = make_fact("tool_output", "logs.txt", "2026-11-19T10:00:00Z")
    incoming = {
        "source_type": "agent_inference",
        "evidence_ref": "logs.txt",
        "created_at": "2026-11-19T10:05:00Z",
    }

    res = resolve_conflict(existing, incoming)
    assert res.decision == ConflictDecision.EXISTING_WINS
    assert res.rule_applied == "source_authority"

    # Reverse: incoming has higher authority
    incoming_human = {"source_type": "human_input", "evidence_ref": "logs.txt"}
    res2 = resolve_conflict(existing, incoming_human)
    assert res2.decision == ConflictDecision.INCOMING_WINS
    assert res2.rule_applied == "source_authority"


def test_rule_2_evidence_specificity() -> None:
    # Same authority (tool_output), differing specificity
    existing = make_fact("tool_output", "logs/build.log", "2026-11-19T10:00:00Z")
    incoming = {
        "source_type": "tool_output",
        "evidence_ref": "logs/build.log:452",  # Specific line
        "created_at": "2026-11-19T10:00:00Z",
    }

    res = resolve_conflict(existing, incoming)
    assert res.decision == ConflictDecision.INCOMING_WINS
    assert res.rule_applied == "evidence_specificity"


def test_rule_3_recency_for_time_sensitive_types() -> None:
    existing = make_fact("tool_output", "status", "2026-11-19T10:00:00Z")
    incoming = {
        "source_type": "tool_output",
        "evidence_ref": "status",
        "created_at": "2026-11-19T10:05:00Z",  # More recent
    }

    # Not time sensitive -> Unresolved
    res_not_time = resolve_conflict(existing, incoming, is_time_sensitive=False)
    assert res_not_time.decision == ConflictDecision.UNRESOLVED

    # Time sensitive -> Incoming wins by recency
    res_time = resolve_conflict(existing, incoming, is_time_sensitive=True)
    assert res_time.decision == ConflictDecision.INCOMING_WINS
    assert res_time.rule_applied == "recency"


def test_rule_4_unresolved() -> None:
    existing = make_fact("document", "spec.pdf", "2026-11-19T10:00:00Z")
    incoming = {
        "source_type": "document",
        "evidence_ref": "spec.pdf",
        "created_at": "2026-11-19T10:00:00Z",
    }

    res = resolve_conflict(existing, incoming, is_time_sensitive=False)
    assert res.decision == ConflictDecision.UNRESOLVED
    assert res.rule_applied == "unresolved"
