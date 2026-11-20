"""Deterministic Conflict Resolution Engine.

Enforces:
- CONF-1: Resolution order is fixed:
  1. Source authority
  2. Evidence specificity
  3. Recency (time-sensitive types only)
  4. Unresolved (both CONTESTED)
- CONF-2: Unresolved conflicts mark both facts CONTESTED and emit CONFLICT_RAISED.
- CONF-3: The LLM never adjudicates a conflict. Plain code only (INV-6).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from groundtruth.core.models import FactModel

SOURCE_AUTHORITY_RANKS = {
    "human_input": 4,
    "tool_output": 3,
    "document": 2,
    "agent_inference": 1,
}


class ConflictDecision(StrEnum):
    """Decision outcome of conflict resolution."""

    EXISTING_WINS = "EXISTING_WINS"
    INCOMING_WINS = "INCOMING_WINS"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class ConflictResult:
    """Result of evaluating a contradiction between two facts."""

    decision: ConflictDecision
    rule_applied: str
    reason: str


def is_specific_evidence(evidence_ref: str | None) -> bool:
    """Heuristic: line numbers or diff hunks are more specific than general file/URL references."""
    if not evidence_ref:
        return False
    ref = evidence_ref.lower()
    return any(marker in ref for marker in ("line", "hunk", ":", "#l", "row", "offset"))


def resolve_conflict(
    existing: FactModel,
    incoming: dict[str, Any],
    is_time_sensitive: bool = False,
) -> ConflictResult:
    """Evaluate contradiction between an admitted fact and an incoming proposal.

    Follows CONF-1 hierarchy in strict deterministic order.
    """
    # Rule 1: Source Authority
    existing_rank = SOURCE_AUTHORITY_RANKS.get(existing.source_type, 0)
    incoming_rank = SOURCE_AUTHORITY_RANKS.get(incoming.get("source_type", ""), 0)

    if existing_rank > incoming_rank:
        in_src = incoming.get("source_type")
        return ConflictResult(
            decision=ConflictDecision.EXISTING_WINS,
            rule_applied="source_authority",
            reason=f"Existing source authority ({existing.source_type}) beats incoming ({in_src})",
        )
    if incoming_rank > existing_rank:
        in_src = incoming.get("source_type")
        return ConflictResult(
            decision=ConflictDecision.INCOMING_WINS,
            rule_applied="source_authority",
            reason=f"Incoming source authority ({in_src}) beats existing ({existing.source_type})",
        )

    # Rule 2: Evidence Specificity
    existing_specific = is_specific_evidence(existing.evidence_ref)
    incoming_specific = is_specific_evidence(incoming.get("evidence_ref"))

    if existing_specific and not incoming_specific:
        return ConflictResult(
            decision=ConflictDecision.EXISTING_WINS,
            rule_applied="evidence_specificity",
            reason="Existing fact cites specific line/hunk evidence, incoming is general",
        )
    if incoming_specific and not existing_specific:
        return ConflictResult(
            decision=ConflictDecision.INCOMING_WINS,
            rule_applied="evidence_specificity",
            reason="Incoming fact cites specific line/hunk evidence, existing is general",
        )

    # Rule 3: Recency (time-sensitive types only)
    if is_time_sensitive:
        existing_ts = existing.created_at
        incoming_ts = incoming.get("created_at", "")
        if incoming_ts > existing_ts:
            return ConflictResult(
                decision=ConflictDecision.INCOMING_WINS,
                rule_applied="recency",
                reason=f"Incoming observation is more recent ({incoming_ts} > {existing_ts})",
            )
        if existing_ts > incoming_ts:
            return ConflictResult(
                decision=ConflictDecision.EXISTING_WINS,
                rule_applied="recency",
                reason=f"Existing observation is more recent ({existing_ts} > {incoming_ts})",
            )

    # Rule 4: Unresolved
    return ConflictResult(
        decision=ConflictDecision.UNRESOLVED,
        rule_applied="unresolved",
        reason="Equal authority, specificity, and non-recency; marked CONTESTED for human",
    )
