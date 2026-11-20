"""Read-side context projection and token packing engine.

Enforces:
- FR-5: Role-scoped, budgeted context projection.
- INV-10: Isolation. A role MUST NOT read fact types outside its contract.
- TRUST-3: Only facts with status == ACTIVE and effective_trust >= min_trust_threshold.
- Architecture Section 10:
  1. Filter: type IN contract.reads, status == ACTIVE, effective_trust >= min_trust_threshold.
  2. Score: recency * effective_trust (with goal relevance).
  3. Rank & Pack: pack within max_context_tokens.
  4. Omit with pointers: remaining facts become lightweight pointer stubs {fact_id, summary}.
  5. Mandatory inclusions: active negative checks and contested conflict warnings.
- INV-6: Deterministic governance; imports neither adapters/ nor provider SDKs.
"""

import sqlite3
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, Field

from groundtruth.core.enums import FactStatus
from groundtruth.core.models import FactModel
from groundtruth.core.pack import DomainPack
from groundtruth.core.projector import load_case_projection
from groundtruth.core.utils import canonical_json


class ContextFactStub(BaseModel):
    """Lightweight reference stub for an omitted fact (Architecture Section 10)."""

    fact_id: str
    type: str
    summary: str


class ContextProjection(BaseModel):
    """Role-scoped context projected for an agent."""

    case_id: str
    role: str
    goal: str
    facts: list[dict[str, Any]]
    omitted_facts: list[ContextFactStub] = Field(default_factory=list)
    negative_checks: list[dict[str, Any]] = Field(default_factory=list)
    conflict_warnings: list[dict[str, Any]] = Field(default_factory=list)
    total_tokens_estimate: int = Field(ge=0)


def estimate_tokens(data: Any) -> int:
    """Deterministic token estimate based on canonical JSON payload (approx 4 chars/token)."""
    serialized = canonical_json(data) if isinstance(data, dict | list) else str(data)
    return max(1, len(serialized) // 4)


def project_context(
    conn: sqlite3.Connection,
    role: str,
    case_id: str,
    goal: str = "",
    pack: DomainPack | None = None,
    fact_type_filter: str | None = None,
) -> ContextProjection:
    """Project role-scoped, budgeted context from case state (Architecture Section 10)."""
    if pack is None:
        raise ValueError("pack is required for context projection")

    contract = pack.contracts.get(role)
    if contract is None:
        raise PermissionError(f"Role '{role}' has no contract defined in pack")

    # Contract read boundary check (INV-10)
    is_wildcard = "*" in contract.reads
    if not is_wildcard:
        if not contract.reads:
            raise PermissionError(f"Role '{role}' contract has empty reads (reads: [])")
        if fact_type_filter and fact_type_filter not in contract.reads:
            raise PermissionError(
                f"Role '{role}' cannot read fact type '{fact_type_filter}' outside contract"
            )

    state = load_case_projection(conn, case_id)

    # 1. Filter: type IN contract.reads, status == ACTIVE, effective_trust >= min_trust_threshold
    eligible_facts: list[FactModel] = []
    for fact in state.facts.values():
        if not is_wildcard and fact.type not in contract.reads:
            continue
        if fact_type_filter and fact.type != fact_type_filter:
            continue
        if fact.status != FactStatus.ACTIVE.value and fact.status != FactStatus.ACTIVE:
            continue
        if fact.effective_trust < contract.min_trust_threshold:
            continue
        eligible_facts.append(fact)

    # 2. Score: effective_trust * recency_weight * goal_relevance
    scored: list[tuple[float, FactModel]] = []
    goal_tokens = {w.lower() for w in goal.split() if len(w) > 2}

    for idx, fact in enumerate(eligible_facts):
        # Recency: higher index in ordered facts gets higher recency weight [0.7, 1.0]
        recency_weight = 0.7 + 0.3 * ((idx + 1) / max(1, len(eligible_facts)))
        score = fact.effective_trust * recency_weight

        # Goal relevance heuristic
        if goal_tokens:
            val_text = canonical_json(fact.value).lower()
            overlap = sum(1 for kw in goal_tokens if kw in val_text or kw in fact.type.lower())
            if overlap > 0:
                score *= 1.0 + min(1.0, 0.25 * overlap)

        scored.append((score, fact))

    # Rank descending by salience
    scored.sort(key=lambda x: x[0], reverse=True)

    # 3. Pack facts into max_context_tokens
    max_tokens = contract.max_context_tokens
    packed_facts: list[dict[str, Any]] = []
    omitted_facts: list[ContextFactStub] = []
    consumed_tokens = 0

    for _score, fact in scored:
        fact_dict = asdict(fact)
        fact_tokens = estimate_tokens(fact_dict)

        if max_tokens == 0 or (consumed_tokens + fact_tokens <= max_tokens):
            packed_facts.append(fact_dict)
            consumed_tokens += fact_tokens
        else:
            # 4. Omit with lightweight pointer stub
            val_str = canonical_json(fact.value)
            summary = val_str[:120] + "..." if len(val_str) > 120 else val_str
            omitted_facts.append(
                ContextFactStub(
                    fact_id=fact.fact_id,
                    type=fact.type,
                    summary=summary,
                )
            )

    # 5. Mandatory inclusions (active negative checks and contested conflict warnings)
    neg_checks: list[dict[str, Any]] = [asdict(nc) for nc in state.negative_checks.values()]

    conflict_warnings: list[dict[str, Any]] = [
        asdict(f)
        for f in state.facts.values()
        if f.status == FactStatus.CONTESTED.value or f.status == FactStatus.CONTESTED
    ]

    return ContextProjection(
        case_id=case_id,
        role=role,
        goal=goal,
        facts=packed_facts,
        omitted_facts=omitted_facts,
        negative_checks=neg_checks,
        conflict_warnings=conflict_warnings,
        total_tokens_estimate=consumed_tokens,
    )
