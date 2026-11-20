"""Topological Trust Recomputation and Decay Ticks Service.

Enforces:
- TRUST-4: Recompute in topological order. Emit TRUST_RECOMPUTED for each change,
  with either cause_event (status or ancestor change) or as_of (decay tick).
- TRUST-6: Tainted/retracted facts have own trust 0. Decay uses injected now,
  recorded as TRUST_RECOMPUTED so replay never recomputes it.
- TRUST-8: Decay ticks run before /decision, /read, /graph, and /state.
  They never run for /state?at=N or on a CLOSED case.
  A tick emits TRUST_RECOMPUTED only when a value changes by at least decay_epsilon
  or crosses T_cite or T_auto.
- FIX-6: Supports injected fixture clocks.
- INV-6: Plain code; imports no LLM adapters or provider SDKs.
"""

import sqlite3
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path

from groundtruth.core.enums import EventType
from groundtruth.core.ledger import Event
from groundtruth.core.models import FactModel
from groundtruth.core.pack import DomainPack, load_pack
from groundtruth.core.projector import append_and_project, load_case_projection
from groundtruth.core.trust import effective_trust, own_trust
from groundtruth.core.utils import Clock, SystemClock


def topological_sort_facts(facts: dict[str, FactModel]) -> list[FactModel]:
    """Sort facts in topological order (parents precede children in DAG) (TRUST-4)."""
    in_degree: dict[str, int] = dict.fromkeys(facts, 0)
    children_adj: dict[str, list[str]] = defaultdict(list)

    for fid, f in facts.items():
        for pid in f.derived_from:
            if pid in facts:
                children_adj[pid].append(fid)
                in_degree[fid] += 1

    # Queue of nodes with zero in-degree (root ancestors)
    queue: deque[str] = deque([fid for fid, deg in in_degree.items() if deg == 0])
    ordered: list[FactModel] = []

    while queue:
        curr_id = queue.popleft()
        if curr_id in facts:
            ordered.append(facts[curr_id])
        for child_id in children_adj[curr_id]:
            in_degree[child_id] -= 1
            if in_degree[child_id] == 0:
                queue.append(child_id)

    # If any nodes remain unvisited due to unexpected cycles, append them
    visited_ids = {f.fact_id for f in ordered}
    for fid, f in facts.items():
        if fid not in visited_ids:
            ordered.append(f)

    return ordered


def recompute_trust(
    conn: sqlite3.Connection,
    case_id: str,
    pack: DomainPack,
    now: datetime | None = None,
    cause_event_id: str | None = None,
    clock: Clock | None = None,
) -> list[Event]:
    """Recompute trust values across DAG in topological order (TRUST-4)."""
    state = load_case_projection(conn, case_id)
    if not state.case or state.case.state == "CLOSED":
        return []

    active_now = now or (clock.now() if clock else SystemClock().now())
    if active_now.tzinfo is None:
        active_now = active_now.replace(tzinfo=UTC)

    ordered_facts = topological_sort_facts(state.facts)
    emitted_events: list[Event] = []

    for fact in ordered_facts:
        new_own = own_trust(fact, pack, active_now)
        new_eff = effective_trust(fact, state.facts, pack, active_now)

        # Emit if either own_trust or effective_trust changed
        if abs(new_own - fact.own_trust) > 1e-4 or abs(new_eff - fact.effective_trust) > 1e-4:
            evt = append_and_project(
                conn=conn,
                case_id=case_id,
                event_type=EventType.TRUST_RECOMPUTED,
                actor="system",
                payload={
                    "fact_id": fact.fact_id,
                    "old_effective_trust": fact.effective_trust,
                    "new_effective_trust": new_eff,
                    "old_own_trust": fact.own_trust,
                    "new_own_trust": new_own,
                    "cause_event": cause_event_id,
                },
                ts=active_now,
            )
            emitted_events.append(evt)

            # Update in-memory snapshot for downstream topological sorting
            fact.own_trust = new_own
            fact.effective_trust = new_eff

    return emitted_events


def apply_decay_tick(
    conn: sqlite3.Connection,
    case_id: str,
    pack: DomainPack | None = None,
    now: datetime | None = None,
    clock: Clock | None = None,
) -> list[Event]:
    """Apply time-based decay tick to volatile facts and emit TRUST_RECOMPUTED (TRUST-8)."""
    state = load_case_projection(conn, case_id)
    # TRUST-8 & CASE-3: Ticks never run on a CLOSED case
    if not state.case or state.case.state == "CLOSED":
        return []

    pack_config = pack
    if pack_config is None:
        pack_dir = Path("groundtruth/packs") / state.case.domain_pack
        pack_config = load_pack(pack_dir)

    active_now = now or (clock.now() if clock else SystemClock().now())
    if active_now.tzinfo is None:
        active_now = active_now.replace(tzinfo=UTC)

    ordered_facts = topological_sort_facts(state.facts)
    emitted_events: list[Event] = []

    for fact in ordered_facts:
        new_own = own_trust(fact, pack_config, active_now)
        new_eff = effective_trust(fact, state.facts, pack_config, active_now)

        delta_eff = abs(new_eff - fact.effective_trust)
        delta_own = abs(new_own - fact.own_trust)

        # Check threshold crossings (TRUST-8)
        t_cite = pack_config.trust.T_cite
        t_auto = pack_config.trust.T_auto
        crossed_cite = (fact.effective_trust >= t_cite > new_eff) or (
            fact.effective_trust < t_cite <= new_eff
        )
        crossed_auto = (fact.effective_trust >= t_auto > new_eff) or (
            fact.effective_trust < t_auto <= new_eff
        )

        should_emit = (
            delta_eff >= pack_config.trust.decay_epsilon
            or delta_own >= pack_config.trust.decay_epsilon
            or crossed_cite
            or crossed_auto
        )

        if should_emit:
            evt = append_and_project(
                conn=conn,
                case_id=case_id,
                event_type=EventType.TRUST_RECOMPUTED,
                actor="system",
                payload={
                    "fact_id": fact.fact_id,
                    "old_effective_trust": fact.effective_trust,
                    "new_effective_trust": new_eff,
                    "old_own_trust": fact.own_trust,
                    "new_own_trust": new_own,
                    "as_of": active_now.isoformat(),
                },
                ts=active_now,
            )
            emitted_events.append(evt)

            # Update in-memory for child propagation in topological order
            fact.own_trust = new_own
            fact.effective_trust = new_eff

    return emitted_events
