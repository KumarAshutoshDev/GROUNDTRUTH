"""Pure Trust Algebra Engine.

Enforces:
- INV-8: Trust only goes down the chain.
  effective_trust = min(own_trust, min(parents' effective_trust)).
  No code may raise a child above its weakest parent.
- TRUST-1: own_trust(fact) = min(BASE[fact.source_type], fact.self_confidence).
  Capped at DOWNGRADE_CAP if verifier_state == DOWNGRADED.
  Decayed by 0.5 ** (age / half_life) if volatile.
- TRUST-2: Thresholds, decay half-lives, and budget limits come from pack config.
- TRUST-6: Tainted or retracted facts have own_trust = 0.0.
- INV-6: Deterministic governance; imports neither adapters/ nor provider SDKs.
"""

from datetime import UTC, datetime
from typing import Any

from groundtruth.core.enums import FactStatus, VerifierState
from groundtruth.core.models import FactModel
from groundtruth.core.pack import DomainPack


def parse_datetime(dt_val: Any) -> datetime:
    """Parse ISO 8601 string or datetime into UTC datetime."""
    if isinstance(dt_val, datetime):
        return dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=UTC)
    # Parse string
    dt_str = str(dt_val).replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_str)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def own_trust(fact: FactModel, pack: DomainPack, now: datetime) -> float:
    """Compute intrinsic trust of a fact without considering lineage (TRUST-1, TRUST-6)."""
    # TRUST-6: Tainted or retracted facts immediately collapse own_trust to 0.0
    if fact.status in (
        FactStatus.TAINTED.value,
        FactStatus.TAINTED,
        FactStatus.RETRACTED.value,
        FactStatus.RETRACTED,
    ):
        return 0.0

    # Base trust according to source_type capped by self_confidence (TRUST-1)
    base = pack.trust.BASE.get(fact.source_type, 0.50)
    t = min(base, fact.self_confidence)

    # Verifier downgrade cap (TRUST-1, TRUST-2)
    if fact.verifier_state in (
        VerifierState.DOWNGRADED.value,
        VerifierState.DOWNGRADED,
        "DOWNGRADED",
    ):
        t = min(t, pack.trust.DOWNGRADE_CAP)

    # Volatility and decay: decay = 0.5 ** (age_seconds / half_life_seconds)
    half_life = pack.trust.half_lives.get(fact.type)
    if half_life is not None and half_life > 0:
        try:
            created_dt = parse_datetime(fact.created_at)
            now_dt = parse_datetime(now)
            age_seconds = max(0.0, (now_dt - created_dt).total_seconds())
            decay_factor = 0.5 ** (age_seconds / half_life)
            t *= decay_factor
        except Exception:
            pass

    return max(0.0, min(1.0, round(t, 4)))


def effective_trust(
    fact_or_id: FactModel | str,
    facts: dict[str, FactModel],
    pack: DomainPack,
    now: datetime,
    visited: set[str] | None = None,
) -> float:
    """Compute transitivity-bounded effective trust for a fact (INV-8).

    effective_trust = min([own_trust(fact)] + [effective_trust(p) for p in fact.derived_from])
    """
    if visited is None:
        visited = set()

    fact: FactModel | None
    if isinstance(fact_or_id, str):
        fact = facts.get(fact_or_id)
        if fact is None:
            return 0.0
    else:
        fact = fact_or_id

    # Cycle detection
    if fact.fact_id in visited:
        return 0.0

    visited.add(fact.fact_id)

    # 1. Compute fact's own trust
    t_own = own_trust(fact, pack, now)

    # 2. If no parent dependencies, effective_trust == own_trust
    if not fact.derived_from:
        return t_own

    # 3. Transitive minimum over all parent dependencies (INV-8)
    parent_effective_trusts: list[float] = []
    for parent_id in fact.derived_from:
        parent_fact = facts.get(parent_id)
        if parent_fact is not None:
            p_trust = effective_trust(
                fact_or_id=parent_fact,
                facts=facts,
                pack=pack,
                now=now,
                visited=visited.copy(),
            )
            parent_effective_trusts.append(p_trust)
        else:
            # Missing parent collapses trust
            parent_effective_trusts.append(0.0)

    if not parent_effective_trusts:
        return t_own

    return max(0.0, min(1.0, round(min([t_own] + parent_effective_trusts), 4)))
