"""Invariant test verifying INV-1: Append-only ledger.

Tests that no UPDATE or DELETE on events or access_log is permitted,
enforced by database triggers.
"""

import sqlite3

import pytest

from groundtruth.core.db import get_connection, init_db


def test_events_no_update() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    # Insert a valid event
    conn.execute(
        """
        INSERT INTO events (
            event_id, case_id, seq, event_type, actor, payload, prev_hash, hash, ts
        ) VALUES (
            'evt_1', 'case_1', 1, 'CASE_OPENED', 'orchestrator', '{}', '0000', '1111',
            '2026-11-19T12:00:00Z'
        )
        """
    )
    conn.commit()

    # Attempting to UPDATE events MUST fail with SQLite trigger abort
    with pytest.raises(sqlite3.IntegrityError, match="INV-1: events is append-only"):
        conn.execute("UPDATE events SET payload = '{\"tampered\": true}' WHERE event_id = 'evt_1'")


def test_events_no_delete() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    # Insert a valid event
    conn.execute(
        """
        INSERT INTO events (
            event_id, case_id, seq, event_type, actor, payload, prev_hash, hash, ts
        ) VALUES (
            'evt_1', 'case_1', 1, 'CASE_OPENED', 'orchestrator', '{}', '0000', '1111',
            '2026-11-19T12:00:00Z'
        )
        """
    )
    conn.commit()

    # Attempting to DELETE from events MUST fail with SQLite trigger abort
    with pytest.raises(sqlite3.IntegrityError, match="INV-1: events is append-only"):
        conn.execute("DELETE FROM events WHERE event_id = 'evt_1'")


def test_access_log_no_update() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    # Insert a valid access log entry
    conn.execute(
        """
        INSERT INTO access_log (log_id, ts, caller, target_case_id, endpoint, reason)
        VALUES ('log_1', '2026-11-19T12:00:00Z', 'token123', 'case_1', '/read', 'unauthorized')
        """
    )
    conn.commit()

    # Attempting to UPDATE access_log MUST fail with SQLite trigger abort
    with pytest.raises(sqlite3.IntegrityError, match="INV-1: access_log is append-only"):
        conn.execute("UPDATE access_log SET reason = 'cleared' WHERE log_id = 'log_1'")


def test_access_log_no_delete() -> None:
    conn = get_connection(":memory:")
    init_db(conn)

    # Insert a valid access log entry
    conn.execute(
        """
        INSERT INTO access_log (log_id, ts, caller, target_case_id, endpoint, reason)
        VALUES ('log_1', '2026-11-19T12:00:00Z', 'token123', 'case_1', '/read', 'unauthorized')
        """
    )
    conn.commit()

    # Attempting to DELETE from access_log MUST fail with SQLite trigger abort
    with pytest.raises(sqlite3.IntegrityError, match="INV-1: access_log is append-only"):
        conn.execute("DELETE FROM access_log WHERE log_id = 'log_1'")
