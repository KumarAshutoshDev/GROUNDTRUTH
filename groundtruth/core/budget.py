"""Budget Accounting Engine.

Enforces:
- CASE-4: Budget limits come from the pack (trust.yaml).
  Usage is derived exclusively from AGENT_ACTION events in the ledger, never stored separately.
  Tool calls are the count of events where actor != 'verifier'.
  Tokens are the sum of tokens_in + tokens_out over all AGENT_ACTION events.
  When a limit is reached, agent endpoints return BUDGET_EXHAUSTED.
- INV-6: Deterministic governance; imports neither adapters/ nor provider SDKs.
"""

import json
import sqlite3
from typing import Any

from pydantic import BaseModel, Field

from groundtruth.core.enums import EventType
from groundtruth.core.ledger import Event
from groundtruth.core.pack import DomainPack
from groundtruth.core.projector import append_and_project


class BudgetUsage(BaseModel):
    """Derived resource usage for a case."""

    tool_calls: int = Field(ge=0, description="Tool calls made by non-verifier actors")
    tokens_in: int = Field(ge=0, description="Sum of input tokens across all actions")
    tokens_out: int = Field(ge=0, description="Sum of output tokens across all actions")
    total_tokens: int = Field(ge=0, description="tokens_in + tokens_out")
    max_tool_calls: int = Field(gt=0, description="Limit configured by domain pack")
    max_tokens: int = Field(gt=0, description="Limit configured by domain pack")
    tool_calls_remaining: int = Field(ge=0, description="Remaining tool calls before exhaustion")
    tokens_remaining: int = Field(ge=0, description="Remaining tokens before exhaustion")
    is_exhausted: bool = Field(description="True if tool calls or tokens meet or exceed limits")
    exhaustion_reason: str | None = Field(
        default=None, description="Explanation if budget is exhausted"
    )


class BudgetExhaustedError(Exception):
    """Raised when an operation is attempted on an exhausted case budget."""

    pass


def calculate_budget_usage(
    conn: sqlite3.Connection,
    case_id: str,
    pack: DomainPack,
) -> BudgetUsage:
    """Derive resource usage from AGENT_ACTION events in the ledger (CASE-4)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT actor, payload FROM events WHERE case_id = ? AND event_type = ? ORDER BY seq ASC",
        (case_id, EventType.AGENT_ACTION.value),
    )
    rows = cursor.fetchall()

    tool_calls = 0
    tokens_in = 0
    tokens_out = 0

    for row in rows:
        actor = row["actor"]
        try:
            payload: dict[str, Any] = json.loads(row["payload"])
        except Exception:
            payload = {}

        # Tool calls count events whose actor is not verifier (Architecture 4.6)
        if actor != "verifier" and payload.get("actor") != "verifier":
            tool_calls += 1

        tokens_in += int(payload.get("tokens_in", 0))
        tokens_out += int(payload.get("tokens_out", 0))

    total_tokens = tokens_in + tokens_out
    max_tool_calls = pack.trust.budget.max_tool_calls
    max_tokens = pack.trust.budget.max_tokens

    tool_calls_remaining = max(0, max_tool_calls - tool_calls)
    tokens_remaining = max(0, max_tokens - total_tokens)

    reasons: list[str] = []
    if tool_calls >= max_tool_calls:
        reasons.append(f"tool_call_limit_reached ({tool_calls}/{max_tool_calls})")
    if total_tokens >= max_tokens:
        reasons.append(f"token_limit_reached ({total_tokens}/{max_tokens})")

    is_exhausted = len(reasons) > 0
    exhaustion_reason = "; ".join(reasons) if is_exhausted else None

    return BudgetUsage(
        tool_calls=tool_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_tokens=total_tokens,
        max_tool_calls=max_tool_calls,
        max_tokens=max_tokens,
        tool_calls_remaining=tool_calls_remaining,
        tokens_remaining=tokens_remaining,
        is_exhausted=is_exhausted,
        exhaustion_reason=exhaustion_reason,
    )


def record_agent_action(
    conn: sqlite3.Connection,
    case_id: str,
    actor: str,
    tool: str,
    args_hash: str,
    result_hash: str,
    tokens_in: int,
    tokens_out: int,
    cache_hit: bool = False,
) -> Event:
    """Record an AGENT_ACTION event in the ledger through the single write path (INV-3)."""
    payload = {
        "actor": actor,
        "tool": tool,
        "args_hash": args_hash,
        "result_hash": result_hash,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_hit": cache_hit,
    }
    return append_and_project(
        conn=conn,
        case_id=case_id,
        event_type=EventType.AGENT_ACTION,
        actor=actor,
        payload=payload,
    )
