"""Data models for GroundTruth state, projections, and operations."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OpType(StrEnum):
    """Operation types emitted by pure reducer diff."""

    INSERT_CASE = "INSERT_CASE"
    UPDATE_CASE = "UPDATE_CASE"
    INSERT_FACT = "INSERT_FACT"
    UPDATE_FACT = "UPDATE_FACT"
    INSERT_EDGE = "INSERT_EDGE"
    INSERT_NEGATIVE = "INSERT_NEGATIVE"


@dataclass(frozen=True)
class Op:
    """A pure database projection operation."""

    op_type: OpType
    table: str
    data: dict[str, Any]


@dataclass
class CaseModel:
    """Projected state of an investigation case."""

    case_id: str
    domain_pack: str
    trigger: dict[str, Any]
    state: str
    opened_at: str
    concluded_at: str | None = None
    conclusion_fact_id: str | None = None


@dataclass
class FactModel:
    """Projected state of a fact."""

    fact_id: str
    case_id: str
    type: str
    value: dict[str, Any] | str
    source: str
    source_type: str
    agent_id: str
    created_at: str
    self_confidence: float
    own_trust: float
    effective_trust: float
    evidence_ref: str | None = None
    status: str = "ACTIVE"
    verifier_state: str = "SUPPORTED"
    entity_key: str | None = None
    volatile: int = 0
    is_conclusion: int = 0
    derived_from: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EdgeModel:
    """Projected dependency edge: child_id derives from parent_id."""

    child_id: str
    parent_id: str


@dataclass
class NegativeCheckModel:
    """Projected negative knowledge check record."""

    check_id: str
    case_id: str
    fact_id: str
    check_type: str
    scope: list[str]
    window_start: str
    window_end: str
    expires_at: str | None = None


@dataclass
class CaseState:
    """In-memory projection of a case's current state."""

    case_id: str
    case: CaseModel | None = None
    facts: dict[str, FactModel] = field(default_factory=dict)
    edges: list[EdgeModel] = field(default_factory=list)
    negative_checks: dict[str, NegativeCheckModel] = field(default_factory=dict)
