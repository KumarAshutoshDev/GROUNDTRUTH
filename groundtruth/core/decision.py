"""Deterministic Governance Decision Engine.

Enforces:
- Section 3.5 Decision Rule (truth table):
  1. ESCALATE if budget is exhausted or any fact is CONTESTED (CONF-2).
  2. NEED_MORE if no conclusion, rework queue non-empty, or missing required checks.
  3. With conclusion: ESCALATE if conclusion not ACTIVE, any ancestor CONTESTED or TAINTED,
     or effective trust < T_auto. Otherwise AUTO_FIX.
- INV-6: Deterministic governance; plain code with zero LLM calls or imports.
- CASE-4: Returns ESCALATE when budget is exhausted.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from groundtruth.core.budget import calculate_budget_usage
from groundtruth.core.enums import DecisionSignal, FactStatus
from groundtruth.core.models import FactModel
from groundtruth.core.pack import DomainPack
from groundtruth.core.projector import load_case_projection
from groundtruth.core.trust_service import apply_decay_tick


class DecisionResult(BaseModel):
    """Deterministic governance signal output."""

    signal: str = Field(description="AUTO_FIX, ESCALATE, or NEED_MORE")
    reasons: list[str] = Field(default_factory=list, description="Explanations for the signal")
    missing_checks: list[str] = Field(
        default_factory=list, description="Fact types or checks required before concluding"
    )
    rework_queue: list[str] = Field(
        default_factory=list, description="Tainted conclusions requiring re-investigation"
    )
    conclusion_fact_id: str | None = Field(
        default=None, description="Pointer to current admitted conclusion"
    )


def get_all_ancestors(fact_id: str, facts: dict[str, FactModel]) -> list[FactModel]:
    """Traverse DAG upwards to collect all transitive ancestors of a fact."""
    ancestors: list[FactModel] = []
    visited: set[str] = {fact_id}
    queue: list[str] = list(facts[fact_id].derived_from) if fact_id in facts else []

    while queue:
        curr_id = queue.pop(0)
        if curr_id in visited:
            continue
        visited.add(curr_id)
        if curr_id in facts:
            ancestors.append(facts[curr_id])
            queue.extend(facts[curr_id].derived_from)

    return ancestors


def load_checks_yaml(pack_dir: Path) -> dict[str, Any]:
    """Load checks.yaml from pack directory if it exists."""
    checks_file = pack_dir / "checks.yaml"
    if checks_file.exists():
        with open(checks_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    return {}


def evaluate_decision(
    conn: sqlite3.Connection,
    case_id: str,
    pack: DomainPack,
    now: datetime | None = None,
    checks_config: dict[str, Any] | None = None,
) -> DecisionResult:
    """Evaluate deterministic governance rule for a case (INV-6, rules Section 3.5)."""
    # 0. Apply decay tick using injected clock (TRUST-8)
    apply_decay_tick(conn=conn, case_id=case_id, pack=pack, now=now)

    state = load_case_projection(conn, case_id)
    if not state.case:
        return DecisionResult(
            signal=DecisionSignal.ESCALATE.value,
            reasons=["case_not_found"],
            conclusion_fact_id=None,
        )

    # 1. ESCALATE check: Budget exhausted or any fact is CONTESTED (CONF-2, CASE-4)
    usage = calculate_budget_usage(conn, case_id, pack)
    if usage.is_exhausted:
        return DecisionResult(
            signal=DecisionSignal.ESCALATE.value,
            reasons=[f"BUDGET_EXHAUSTED: {usage.exhaustion_reason}"],
            conclusion_fact_id=state.case.conclusion_fact_id,
        )

    contested_facts = [
        fid
        for fid, f in state.facts.items()
        if f.status in (FactStatus.CONTESTED.value, FactStatus.CONTESTED, "CONTESTED")
    ]
    if contested_facts:
        return DecisionResult(
            signal=DecisionSignal.ESCALATE.value,
            reasons=[f"facts_contested: {contested_facts}"],
            conclusion_fact_id=state.case.conclusion_fact_id,
        )

    conclusion_id = state.case.conclusion_fact_id

    # Rework queue: conclusion fact when its status is TAINTED (Section 3.5)
    rework_queue: list[str] = []
    if conclusion_id and conclusion_id in state.facts:
        conc_fact = state.facts[conclusion_id]
        if conc_fact.status in (FactStatus.TAINTED.value, FactStatus.TAINTED, "TAINTED"):
            rework_queue.append(conclusion_id)

    # Resolve required checks from checks.yaml if applicable
    cfg = checks_config
    if cfg is None:
        cfg = load_checks_yaml(pack.path)

    required_checks: list[str] = []
    trigger_fixture = state.case.trigger.get("fixture_id", "")
    for fkey, fval in cfg.items():
        if isinstance(fval, dict) and (fkey == trigger_fixture or fkey in trigger_fixture):
            required_checks = fval.get("required_checks", [])
            break

    # Determine missing checks
    missing_checks: list[str] = []
    active_types = {
        f.type
        for f in state.facts.values()
        if f.status in (FactStatus.ACTIVE.value, FactStatus.ACTIVE, "ACTIVE")
    }

    for req_chk in required_checks:
        if req_chk == "negative_check":
            if not state.negative_checks:
                missing_checks.append("negative_check")
        elif req_chk not in active_types:
            missing_checks.append(req_chk)

    # 2. NEED_MORE check: No conclusion, rework queue non-empty, or missing required checks
    has_valid_conclusion = conclusion_id is not None and conclusion_id in state.facts

    if not has_valid_conclusion or rework_queue or missing_checks:
        # When no valid conclusion exists, missing_checks also lists conclusion_type
        if not has_valid_conclusion and pack.conclusion_type not in missing_checks:
            missing_checks.append(pack.conclusion_type)

        reasons = []
        if not has_valid_conclusion:
            reasons.append("no_conclusion_asserted")
        if rework_queue:
            reasons.append("conclusion_tainted_requires_rework")
        if missing_checks:
            reasons.append(f"missing_required_checks: {missing_checks}")

        return DecisionResult(
            signal=DecisionSignal.NEED_MORE.value,
            reasons=reasons,
            missing_checks=missing_checks,
            rework_queue=rework_queue,
            conclusion_fact_id=conclusion_id if not rework_queue else None,
        )

    # 3. With conclusion present:
    assert conclusion_id is not None
    conclusion = state.facts[conclusion_id]

    # ESCALATE if conclusion is not ACTIVE
    if conclusion.status not in (FactStatus.ACTIVE.value, FactStatus.ACTIVE, "ACTIVE"):
        return DecisionResult(
            signal=DecisionSignal.ESCALATE.value,
            reasons=[f"conclusion_not_active: status={conclusion.status}"],
            conclusion_fact_id=conclusion_id,
        )

    # ESCALATE if any ancestor is CONTESTED or TAINTED
    ancestors = get_all_ancestors(conclusion_id, state.facts)
    for anc in ancestors:
        if anc.status in (
            FactStatus.CONTESTED.value,
            FactStatus.CONTESTED,
            "CONTESTED",
            FactStatus.TAINTED.value,
            FactStatus.TAINTED,
            "TAINTED",
        ):
            return DecisionResult(
                signal=DecisionSignal.ESCALATE.value,
                reasons=[f"ancestor_{anc.fact_id}_invalid: status={anc.status}"],
                conclusion_fact_id=conclusion_id,
            )

    # ESCALATE if conclusion effective_trust < T_auto (TRUST-7)
    if conclusion.effective_trust < pack.trust.T_auto:
        t_val = conclusion.effective_trust
        t_auto = pack.trust.T_auto
        return DecisionResult(
            signal=DecisionSignal.ESCALATE.value,
            reasons=[f"conclusion_trust_insufficient: {t_val:.4f} < {t_auto}"],
            conclusion_fact_id=conclusion_id,
        )

    # Otherwise: AUTO_FIX
    return DecisionResult(
        signal=DecisionSignal.AUTO_FIX.value,
        reasons=["all_checks_satisfied_trust_above_threshold"],
        conclusion_fact_id=conclusion_id,
    )
