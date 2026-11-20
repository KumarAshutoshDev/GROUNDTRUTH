"""Pure reducer engine for GroundTruth.

Rules Enforced:
- INV-2: State is derived (diff and apply are pure mathematical functions).
- CASE-1: Conclusion pointer set only on ADMIT with is_conclusion=True.
- Purity: Zero I/O, no DB calls, no clock, no randomness, no network.
"""

import json
from copy import deepcopy
from typing import Any

from groundtruth.core.enums import EventType, FactStatus, GateVerdict, VerifierState
from groundtruth.core.ledger import Event
from groundtruth.core.models import (
    CaseModel,
    CaseState,
    EdgeModel,
    FactModel,
    NegativeCheckModel,
    Op,
    OpType,
)


def diff(state: CaseState, event: Event) -> list[Op]:
    """Derive projection operations from current state and an incoming event.

    Pure function: no I/O, no side effects.
    """
    ops: list[Op] = []
    etype = event.event_type
    payload = event.payload

    if etype == EventType.CASE_OPENED:
        ops.append(
            Op(
                op_type=OpType.INSERT_CASE,
                table="cases",
                data={
                    "case_id": event.case_id,
                    "domain_pack": payload.get("domain_pack", ""),
                    "trigger": payload.get("trigger", {}),
                    "state": "OPEN",
                    "opened_at": event.ts,
                    "concluded_at": None,
                    "conclusion_fact_id": None,
                },
            )
        )

    elif etype == EventType.CASE_STATE_CHANGED:
        to_state = payload.get("to")
        update_data: dict[str, Any] = {"case_id": event.case_id, "state": to_state}
        if to_state == "CONCLUDED":
            update_data["concluded_at"] = event.ts
        ops.append(Op(op_type=OpType.UPDATE_CASE, table="cases", data=update_data))

    elif etype == EventType.GATE_VERDICT:
        verdict = payload.get("verdict")
        fact_dict = payload.get("fact", {})
        fact_id = fact_dict.get("fact_id", "")

        if verdict == GateVerdict.REJECT:
            # REJECT inserts nothing into projection tables (INV-3, GATE-1)
            return []

        is_admit = verdict == GateVerdict.ADMIT
        status = FactStatus.ACTIVE if is_admit else FactStatus.QUARANTINED
        v_state = VerifierState.SUPPORTED if is_admit else VerifierState.NOT_SUPPORTED

        is_conclusion = bool(payload.get("is_conclusion", False)) if is_admit else False

        fact_data = {
            "fact_id": fact_id,
            "case_id": event.case_id,
            "type": fact_dict.get("type", ""),
            "value": fact_dict.get("value", {}),
            "source": fact_dict.get("source", ""),
            "source_type": fact_dict.get("source_type", ""),
            "agent_id": fact_dict.get("agent_id", event.actor),
            "created_at": fact_dict.get("created_at", event.ts),
            "self_confidence": float(fact_dict.get("self_confidence", 1.0)),
            "own_trust": float(payload.get("own_trust", fact_dict.get("own_trust", 0.0))),
            "effective_trust": float(
                payload.get("effective_trust", fact_dict.get("effective_trust", 0.0))
            ),
            "evidence_ref": fact_dict.get("evidence_ref"),
            "status": status,
            "verifier_state": v_state,
            "entity_key": fact_dict.get("entity_key"),
            "volatile": int(fact_dict.get("volatile", 0)),
            "is_conclusion": int(is_conclusion),
            "derived_from": fact_dict.get("derived_from", []),
        }

        ops.append(Op(op_type=OpType.INSERT_FACT, table="facts", data=fact_data))

        # Insert dependency edges
        for parent_id in fact_dict.get("derived_from", []):
            ops.append(
                Op(
                    op_type=OpType.INSERT_EDGE,
                    table="fact_edges",
                    data={"child_id": fact_id, "parent_id": parent_id},
                )
            )

        # Negative check insertion
        if fact_dict.get("type") == "negative_check":
            val = fact_dict.get("value", {})
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    val = {}
            ops.append(
                Op(
                    op_type=OpType.INSERT_NEGATIVE,
                    table="negative_checks",
                    data={
                        "check_id": f"neg_{fact_id}",
                        "case_id": event.case_id,
                        "fact_id": fact_id,
                        "check_type": val.get("check_type", ""),
                        "scope": val.get("scope", []),
                        "window_start": val.get("window_start", ""),
                        "window_end": val.get("window_end", ""),
                        "expires_at": val.get("expires_at"),
                    },
                )
            )

        # CASE-1: ADMIT with is_conclusion=True sets cases.conclusion_fact_id
        if is_admit and is_conclusion:
            ops.append(
                Op(
                    op_type=OpType.UPDATE_CASE,
                    table="cases",
                    data={"case_id": event.case_id, "conclusion_fact_id": fact_id},
                )
            )

    elif etype == EventType.TRUST_RECOMPUTED:
        fact_id = payload.get("fact_id", "")
        update_data = {"fact_id": fact_id}
        if "new_effective_trust" in payload:
            update_data["effective_trust"] = float(payload["new_effective_trust"])
        elif "effective_trust" in payload:
            update_data["effective_trust"] = float(payload["effective_trust"])

        if "new_own_trust" in payload:
            update_data["own_trust"] = float(payload["new_own_trust"])
        elif "own_trust" in payload:
            update_data["own_trust"] = float(payload["own_trust"])

        ops.append(Op(op_type=OpType.UPDATE_FACT, table="facts", data=update_data))

    elif etype == EventType.FACT_DOWNGRADED:
        fact_id = payload.get("fact_id", "")
        update_data = {
            "fact_id": fact_id,
            "verifier_state": VerifierState.DOWNGRADED,
        }
        if payload.get("retract"):
            update_data["status"] = FactStatus.RETRACTED
            update_data["own_trust"] = 0.0
            update_data["effective_trust"] = 0.0
        ops.append(Op(op_type=OpType.UPDATE_FACT, table="facts", data=update_data))

    elif etype == EventType.CONFLICT_RAISED:
        for fid in payload.get("fact_ids", []):
            ops.append(
                Op(
                    op_type=OpType.UPDATE_FACT,
                    table="facts",
                    data={"fact_id": fid, "status": FactStatus.CONTESTED},
                )
            )

    elif etype == EventType.FACT_SUPERSEDED:
        old_id = payload.get("old_id", "")
        ops.append(
            Op(
                op_type=OpType.UPDATE_FACT,
                table="facts",
                data={
                    "fact_id": old_id,
                    "status": FactStatus.RETRACTED,
                    "own_trust": 0.0,
                    "effective_trust": 0.0,
                },
            )
        )

    elif etype == EventType.FACT_TAINTED:
        fact_id = payload.get("fact_id", "")
        ops.append(
            Op(
                op_type=OpType.UPDATE_FACT,
                table="facts",
                data={
                    "fact_id": fact_id,
                    "status": FactStatus.TAINTED,
                    "own_trust": 0.0,
                    "effective_trust": 0.0,
                },
            )
        )

    elif etype == EventType.HUMAN_OVERRIDE:
        fact_id = payload.get("fact_id", "")
        action = payload.get("action", "")
        update_data = {"fact_id": fact_id}

        if action == "RESTORE_ACTIVE":
            update_data["status"] = FactStatus.ACTIVE
            update_data["source_type"] = "human_input"
            if "own_trust" in payload:
                val_trust = float(payload["own_trust"])
                update_data["own_trust"] = val_trust
                update_data["self_confidence"] = val_trust
        elif action == "FORCE_RETRACT":
            update_data["status"] = FactStatus.RETRACTED
            update_data["own_trust"] = 0.0
            update_data["effective_trust"] = 0.0
        elif action == "ADJUST_TRUST":
            update_data["source_type"] = "human_input"
            if "own_trust" in payload:
                val_trust = float(payload["own_trust"])
                update_data["own_trust"] = val_trust
                update_data["self_confidence"] = val_trust
            if "effective_trust" in payload:
                update_data["effective_trust"] = float(payload["effective_trust"])

        if "status" in payload:
            update_data["status"] = payload["status"]

        ops.append(Op(op_type=OpType.UPDATE_FACT, table="facts", data=update_data))

    # EventType.FACT_PROPOSED, AGENT_ACTION, ACCESS_DENIED emit zero ops
    return ops


def apply(state: CaseState, event: Event) -> CaseState:
    """Fold operations derived from an event onto in-memory case state.

    Pure function: returns a new updated CaseState instance.
    """
    new_state = deepcopy(state)
    ops = diff(new_state, event)

    for op in ops:
        if op.op_type == OpType.INSERT_CASE:
            d = op.data
            new_state.case = CaseModel(
                case_id=d["case_id"],
                domain_pack=d["domain_pack"],
                trigger=d["trigger"],
                state=d["state"],
                opened_at=d["opened_at"],
                concluded_at=d["concluded_at"],
                conclusion_fact_id=d["conclusion_fact_id"],
            )

        elif op.op_type == OpType.UPDATE_CASE:
            if new_state.case is not None:
                d = op.data
                if "state" in d:
                    new_state.case.state = d["state"]
                if "concluded_at" in d:
                    new_state.case.concluded_at = d["concluded_at"]
                if "conclusion_fact_id" in d:
                    new_state.case.conclusion_fact_id = d["conclusion_fact_id"]

        elif op.op_type == OpType.INSERT_FACT:
            d = op.data
            fid = d["fact_id"]
            new_state.facts[fid] = FactModel(
                fact_id=fid,
                case_id=d["case_id"],
                type=d["type"],
                value=d["value"],
                source=d["source"],
                source_type=d["source_type"],
                agent_id=d["agent_id"],
                created_at=d["created_at"],
                self_confidence=d["self_confidence"],
                own_trust=d["own_trust"],
                effective_trust=d["effective_trust"],
                evidence_ref=d["evidence_ref"],
                status=d["status"],
                verifier_state=d["verifier_state"],
                entity_key=d.get("entity_key"),
                volatile=d.get("volatile", 0),
                is_conclusion=d.get("is_conclusion", 0),
                derived_from=d.get("derived_from", []),
            )

        elif op.op_type == OpType.UPDATE_FACT:
            d = op.data
            fid = d["fact_id"]
            if fid in new_state.facts:
                fact = new_state.facts[fid]
                if "status" in d:
                    fact.status = d["status"]
                if "verifier_state" in d:
                    fact.verifier_state = d["verifier_state"]
                if "own_trust" in d:
                    fact.own_trust = d["own_trust"]
                if "effective_trust" in d:
                    fact.effective_trust = d["effective_trust"]
                if "source_type" in d:
                    fact.source_type = d["source_type"]
                if "self_confidence" in d:
                    fact.self_confidence = d["self_confidence"]

        elif op.op_type == OpType.INSERT_EDGE:
            d = op.data
            edge = EdgeModel(child_id=d["child_id"], parent_id=d["parent_id"])
            if edge not in new_state.edges:
                new_state.edges.append(edge)

        elif op.op_type == OpType.INSERT_NEGATIVE:
            d = op.data
            cid = d["check_id"]
            new_state.negative_checks[cid] = NegativeCheckModel(
                check_id=cid,
                case_id=d["case_id"],
                fact_id=d["fact_id"],
                check_type=d["check_type"],
                scope=d["scope"],
                window_start=d["window_start"],
                window_end=d["window_end"],
                expires_at=d.get("expires_at"),
            )

    return new_state
