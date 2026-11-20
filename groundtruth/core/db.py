"""Database schema, initialization, and connection management for GroundTruth.

Enforces:
- Single datastore (SQLite) (INV-11)
- Append-only ledger triggers on events and access_log (INV-1)
- Schema strictly aligned with Architecture v2.1 Section 4.1
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_DDL = """
-- PROJECTION: cases table (INV-2, INV-3)
CREATE TABLE IF NOT EXISTS cases (
  case_id            TEXT PRIMARY KEY,
  domain_pack        TEXT NOT NULL,
  trigger            TEXT NOT NULL,          -- JSON
  state              TEXT NOT NULL CHECK (state IN ('OPEN','INVESTIGATING','CONCLUDED','CLOSED')),
  opened_at          TEXT NOT NULL,
  concluded_at       TEXT,
  conclusion_fact_id TEXT                    -- set by the reducer on an admitted conclusion
);

-- APPEND-ONLY LEDGER: events table (INV-1)
CREATE TABLE IF NOT EXISTS events (
  event_id           TEXT PRIMARY KEY,
  case_id            TEXT NOT NULL,          -- no FK to cases
  seq                INTEGER NOT NULL,       -- per-case, gapless, starts at 1
  event_type         TEXT NOT NULL,
  actor              TEXT NOT NULL,
  payload            TEXT NOT NULL,          -- canonical JSON
  prev_hash          TEXT NOT NULL,
  hash               TEXT NOT NULL,
  ts                 TEXT NOT NULL,
  UNIQUE (case_id, seq)
);

-- APPEND-ONLY AUDIT: access_log table (INV-1, SEC-5)
CREATE TABLE IF NOT EXISTS access_log (
  log_id             TEXT PRIMARY KEY,
  ts                 TEXT NOT NULL,
  caller             TEXT,                   -- first 8 chars of token hash or NULL
  target_case_id     TEXT,
  endpoint           TEXT NOT NULL,
  reason             TEXT NOT NULL
);

-- PROJECTION: facts table (INV-2, INV-3)
CREATE TABLE IF NOT EXISTS facts (
  fact_id            TEXT PRIMARY KEY,
  case_id            TEXT NOT NULL,
  type               TEXT NOT NULL,
  value              TEXT NOT NULL,          -- JSON
  source             TEXT NOT NULL,
  source_type        TEXT NOT NULL CHECK (
                       source_type IN ('tool_output','document','agent_inference','human_input')
                     ),
  agent_id           TEXT NOT NULL,
  created_at         TEXT NOT NULL,
  self_confidence    REAL NOT NULL CHECK (self_confidence BETWEEN 0.0 AND 1.0),
  own_trust          REAL NOT NULL,
  effective_trust    REAL NOT NULL,
  evidence_ref       TEXT,
  status             TEXT NOT NULL CHECK (
                       status IN ('ACTIVE','CONTESTED','QUARANTINED','RETRACTED','TAINTED')
                     ),
  verifier_state     TEXT NOT NULL DEFAULT 'NOT_SUPPORTED' CHECK (
                       verifier_state IN ('SUPPORTED','NOT_SUPPORTED','DOWNGRADED')
                     ),
  entity_key         TEXT,
  volatile           INTEGER NOT NULL DEFAULT 0,
  is_conclusion      INTEGER NOT NULL DEFAULT 0
);

-- PROJECTION: fact_edges table (INV-2, INV-3)
CREATE TABLE IF NOT EXISTS fact_edges (
  child_id           TEXT NOT NULL REFERENCES facts(fact_id),
  parent_id          TEXT NOT NULL REFERENCES facts(fact_id),
  PRIMARY KEY (child_id, parent_id)
);

-- PROJECTION: negative_checks table (INV-2, INV-3, NEG-1)
CREATE TABLE IF NOT EXISTS negative_checks (
  check_id           TEXT PRIMARY KEY,
  case_id            TEXT NOT NULL,
  fact_id            TEXT NOT NULL REFERENCES facts(fact_id),
  check_type         TEXT NOT NULL,
  scope              TEXT NOT NULL,          -- JSON array of entities checked (NEG-1)
  window_start       TEXT NOT NULL,          -- NEG-1: mandatory
  window_end         TEXT NOT NULL,          -- NEG-1: mandatory
  expires_at         TEXT                    -- NULL means does not expire
);

-- CONFIGURATION: contracts table seeded from domain pack
CREATE TABLE IF NOT EXISTS contracts (
  role               TEXT PRIMARY KEY,
  reads              TEXT NOT NULL,          -- JSON array of fact types or ["*"]
  writes             TEXT NOT NULL,          -- JSON array of fact types
  max_context_tokens INTEGER NOT NULL,
  min_trust_threshold REAL NOT NULL
);

-- CONFIGURATION: agent_tokens table (SEC-1, SEC-2)
CREATE TABLE IF NOT EXISTS agent_tokens (
  token_hash         TEXT PRIMARY KEY,
  agent_id           TEXT NOT NULL,
  role               TEXT NOT NULL REFERENCES contracts(role),
  case_id            TEXT NOT NULL
);

-- INDEXES for fast lookup and sequential scanning
CREATE INDEX IF NOT EXISTS idx_events_case_seq ON events(case_id, seq);
CREATE INDEX IF NOT EXISTS idx_facts_case_id ON facts(case_id);
CREATE INDEX IF NOT EXISTS idx_facts_entity_key ON facts(case_id, entity_key);
CREATE INDEX IF NOT EXISTS idx_fact_edges_parent ON fact_edges(parent_id);
CREATE INDEX IF NOT EXISTS idx_negative_checks_case ON negative_checks(case_id, check_type);
"""

TRIGGERS_DDL = """
-- INV-1: Triggers enforcing append-only guarantee on events
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN
  SELECT RAISE(ABORT, 'INV-1: events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN
  SELECT RAISE(ABORT, 'INV-1: events is append-only');
END;

-- INV-1: Triggers enforcing append-only guarantee on access_log
CREATE TRIGGER IF NOT EXISTS access_log_no_update BEFORE UPDATE ON access_log
BEGIN
  SELECT RAISE(ABORT, 'INV-1: access_log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS access_log_no_delete BEFORE DELETE ON access_log
BEGIN
  SELECT RAISE(ABORT, 'INV-1: access_log is append-only');
END;
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database tables, indexes, and append-only triggers."""
    with conn:
        conn.executescript(SCHEMA_DDL)
        conn.executescript(TRIGGERS_DDL)


def get_connection(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    """Create and configure a SQLite connection.

    Enforces WAL mode when file-backed and activates foreign keys.
    """
    path_str = str(db_path)
    conn = sqlite3.connect(path_str, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")

    # If file-backed, enable WAL mode and set busy timeout
    if path_str != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")

    return conn


@contextmanager
def get_db(db_path: str | Path = ":memory:") -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    conn = get_connection(db_path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()
