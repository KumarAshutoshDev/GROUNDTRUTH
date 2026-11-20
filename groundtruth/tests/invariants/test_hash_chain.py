"""Invariant test verifying cryptographic hash chain integrity and tamper detection."""

import pytest

from groundtruth.core.db import get_connection, init_db
from groundtruth.core.enums import EventType
from groundtruth.core.ledger import LedgerIntegrityError, append_event, verify_case_ledger


def test_hash_chain_valid_sequence() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_test_chain"

    # Append 3 valid events
    e1 = append_event(
        conn,
        case_id=case_id,
        event_type=EventType.CASE_OPENED,
        actor="system",
        payload={"domain_pack": "cicd", "trigger": {"commit": "abc"}},
    )
    e2 = append_event(
        conn,
        case_id=case_id,
        event_type=EventType.CASE_STATE_CHANGED,
        actor="orchestrator",
        payload={"from": "OPEN", "to": "INVESTIGATING"},
    )
    e3 = append_event(
        conn,
        case_id=case_id,
        event_type=EventType.AGENT_ACTION,
        actor="log_agent",
        payload={"tool": "scan_logs", "tokens_in": 100, "tokens_out": 50},
    )

    assert e1.seq == 1
    assert e2.seq == 2
    assert e3.seq == 3
    assert e2.prev_hash == e1.hash
    assert e3.prev_hash == e2.hash

    # Verification must succeed
    assert verify_case_ledger(conn, case_id) is True


def test_hash_chain_tamper_detection() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_test_tamper"
    append_event(conn, case_id, EventType.CASE_OPENED, "system", {"v": 1})
    append_event(conn, case_id, EventType.FACT_PROPOSED, "agent", {"v": 2})

    # Drop trigger temporarily only in this test to simulate raw datastore corruption/tampering
    conn.execute("DROP TRIGGER events_no_update")

    # Corrupt the payload of event 1
    conn.execute(
        """
        UPDATE events
        SET payload = '{"v": 999}'
        WHERE case_id = ? AND seq = 1
        """,
        (case_id,),
    )
    conn.commit()

    # Verification MUST detect tampering and raise LedgerIntegrityError
    with pytest.raises(LedgerIntegrityError, match="Tampering detected at seq 1"):
        verify_case_ledger(conn, case_id)


def test_hash_chain_gap_detection() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    case_id = "case_test_gap"
    append_event(conn, case_id, EventType.CASE_OPENED, "system", {"v": 1})
    append_event(conn, case_id, EventType.FACT_PROPOSED, "agent", {"v": 2})
    append_event(conn, case_id, EventType.AGENT_ACTION, "agent", {"v": 3})

    # Drop trigger to delete seq 2
    conn.execute("DROP TRIGGER events_no_delete")
    conn.execute("DELETE FROM events WHERE case_id = ? AND seq = 2", (case_id,))
    conn.commit()

    with pytest.raises(LedgerIntegrityError, match="Gap in sequence"):
        verify_case_ledger(conn, case_id)
