"""Core negative knowledge engine (NEG-1, NEG-2, NEG-3).

Enforces strict scope, time window, and trust-based suppression of re-checks.
Never answers "probably covered": explicit match or explicit failure reason.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from groundtruth.core.enums import FactStatus
from groundtruth.core.pack import DomainPack


@dataclass(frozen=True)
class NegativeCheckSpec:
    """Specification of a negative check query."""

    check_type: str
    scope: list[str]
    window_start: str
    window_end: str
    expires_at: str | None = None


@dataclass(frozen=True)
class NegativeCoverageResult:
    """Outcome of evaluating negative knowledge coverage against recorded checks."""

    verdict: str  # "COVERED" | "NOT_COVERED"
    reason: str  # "COVERED" or failure reason (NEG-3)
    matching_fact_id: str | None = None
    matching_check_id: str | None = None

    @property
    def status(self) -> str:
        """Formatted status string, e.g. COVERED or NOT_COVERED:scope_mismatch."""
        if self.verdict == "COVERED":
            return "COVERED"
        return f"{self.verdict}:{self.reason}"


def parse_iso_ts(ts: str | datetime) -> datetime:
    """Parse string or datetime to timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts
    cleaned = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def is_scope_covered(requested_scope: list[str], recorded_scope: list[str]) -> bool:
    """Check if requested scope is a subset of recorded scope (NEG-2)."""
    return set(requested_scope).issubset(set(recorded_scope))


def is_window_covered(
    req_start: str | datetime,
    req_end: str | datetime,
    rec_start: str | datetime,
    rec_end: str | datetime,
) -> bool:
    """Check if recorded window covers requested window (NEG-2).

    Recorded window covers requested if recorded starts before or at requested start,
    and recorded ends after or at requested end.
    """
    req_s = parse_iso_ts(req_start)
    req_e = parse_iso_ts(req_end)
    rec_s = parse_iso_ts(rec_start)
    rec_e = parse_iso_ts(rec_end)
    return rec_s <= req_s and req_e <= rec_e


def is_expired(expires_at: str | datetime | None, now: datetime) -> bool:
    """Check if recorded check has passed expires_at (NEG-2)."""
    if not expires_at:
        return False
    exp_dt = parse_iso_ts(expires_at)
    return now >= exp_dt


def check_negative(
    conn: sqlite3.Connection,
    case_id: str,
    query: NegativeCheckSpec | dict[str, Any],
    pack: DomainPack,
    now: datetime | None = None,
) -> NegativeCoverageResult:
    """Query negative knowledge to determine if a check can be suppressed (NEG-2).

    Suppression applies ONLY if:
    1. check_type matches.
    2. requested scope is a subset of recorded scope.
    3. recorded window covers requested window, and now < expires_at.
    4. backing fact is ACTIVE with effective_trust >= pack.trust.T_cite.

    Returns COVERED or NOT_COVERED with the exact failing condition string (NEG-3).
    """
    if isinstance(query, dict):
        q_spec = NegativeCheckSpec(
            check_type=query.get("check_type", ""),
            scope=query.get("scope", []),
            window_start=query.get("window_start", ""),
            window_end=query.get("window_end", ""),
            expires_at=query.get("expires_at"),
        )
    else:
        q_spec = query

    # NEG-1: mandatory window
    if not q_spec.window_start or not q_spec.window_end:
        return NegativeCoverageResult(
            verdict="NOT_COVERED",
            reason="missing_window",
        )

    current_time = now or datetime.now(UTC)

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT nc.check_id, nc.case_id, nc.fact_id, nc.check_type, nc.scope,
               nc.window_start, nc.window_end, nc.expires_at,
               f.status, f.effective_trust
        FROM negative_checks nc
        JOIN facts f ON nc.fact_id = f.fact_id
        WHERE nc.case_id = ? AND nc.check_type = ?
        ORDER BY nc.check_id ASC
        """,
        (case_id, q_spec.check_type),
    )
    rows = cursor.fetchall()

    if not rows:
        return NegativeCoverageResult(
            verdict="NOT_COVERED",
            reason="no_matching_check",
        )

    best_failure_reason = "unmatched"

    for row in rows:
        # 1. Backing fact status must be ACTIVE
        fact_status = row["status"]
        if fact_status not in (FactStatus.ACTIVE.value, FactStatus.ACTIVE, "ACTIVE"):
            best_failure_reason = "backing_fact_inactive"
            continue

        # 2. Backing fact trust must be >= T_cite
        eff_trust = float(row["effective_trust"])
        if eff_trust < pack.trust.T_cite:
            best_failure_reason = "trust_below_threshold"
            continue

        # 3. Check expiry
        if is_expired(row["expires_at"], current_time):
            best_failure_reason = "check_expired"
            continue

        # 4. Scope coverage: requested scope must be subset of recorded scope
        raw_scope = row["scope"]
        rec_scope: list[str] = (
            json.loads(raw_scope) if isinstance(raw_scope, str) else list(raw_scope)
        )
        if not is_scope_covered(q_spec.scope, rec_scope):
            best_failure_reason = "scope_mismatch"
            continue

        # 5. Window coverage: recorded window must cover requested window
        if not is_window_covered(
            q_spec.window_start,
            q_spec.window_end,
            row["window_start"],
            row["window_end"],
        ):
            best_failure_reason = "window_mismatch"
            continue

        # All conditions satisfied!
        return NegativeCoverageResult(
            verdict="COVERED",
            reason="COVERED",
            matching_fact_id=row["fact_id"],
            matching_check_id=row["check_id"],
        )

    return NegativeCoverageResult(
        verdict="NOT_COVERED",
        reason=best_failure_reason,
    )
