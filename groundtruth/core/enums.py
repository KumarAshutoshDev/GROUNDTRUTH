"""Shared enums for GroundTruth.

Every fact status, source type, event type, gate verdict, case state,
and decision signal is defined here. No string literals elsewhere.
"""

from enum import StrEnum


class CaseState(StrEnum):
    """Case lifecycle states."""

    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    CONCLUDED = "CONCLUDED"
    CLOSED = "CLOSED"


class FactStatus(StrEnum):
    """Status of a fact in the shared context store."""

    ACTIVE = "ACTIVE"
    CONTESTED = "CONTESTED"
    QUARANTINED = "QUARANTINED"
    RETRACTED = "RETRACTED"
    TAINTED = "TAINTED"


class SourceType(StrEnum):
    """Source classification of a fact."""

    TOOL_OUTPUT = "tool_output"
    DOCUMENT = "document"
    AGENT_INFERENCE = "agent_inference"
    HUMAN_INPUT = "human_input"


class VerifierState(StrEnum):
    """Verification state returned by or recorded for the Verifier."""

    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    DOWNGRADED = "DOWNGRADED"


class GateVerdict(StrEnum):
    """Admission verdict emitted by the Write Gate."""

    ADMIT = "ADMIT"
    QUARANTINE = "QUARANTINE"
    REJECT = "REJECT"


class EventType(StrEnum):
    """Immutable ledger event types."""

    CASE_OPENED = "CASE_OPENED"
    CASE_STATE_CHANGED = "CASE_STATE_CHANGED"
    FACT_PROPOSED = "FACT_PROPOSED"
    GATE_VERDICT = "GATE_VERDICT"
    TRUST_RECOMPUTED = "TRUST_RECOMPUTED"
    FACT_DOWNGRADED = "FACT_DOWNGRADED"
    FACT_SUPERSEDED = "FACT_SUPERSEDED"
    FACT_TAINTED = "FACT_TAINTED"
    CONFLICT_RAISED = "CONFLICT_RAISED"
    AGENT_ACTION = "AGENT_ACTION"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    ACCESS_DENIED = "ACCESS_DENIED"


class DecisionSignal(StrEnum):
    """Autonomous routing signals emitted by /decision."""

    AUTO_FIX = "AUTO_FIX"
    ESCALATE = "ESCALATE"
    NEED_MORE = "NEED_MORE"
