import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent.parent / "nova.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS shipments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id    TEXT    NOT NULL UNIQUE,
            doc_paths   TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fields (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id       TEXT    NOT NULL,
            field_name     TEXT    NOT NULL,
            value          TEXT,
            confidence     REAL,
            source_snippet TEXT,
            source_page    INTEGER
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id        TEXT    NOT NULL,
            action          TEXT    NOT NULL,
            reasoning       TEXT,
            amendment_email TEXT,
            created_at      TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id     TEXT    NOT NULL,
            event_type   TEXT    NOT NULL,
            payload_json TEXT,
            created_at   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id    TEXT    NOT NULL UNIQUE,
            step        TEXT    NOT NULL,
            state_json  TEXT    NOT NULL,
            cost_usd    REAL    NOT NULL DEFAULT 0.0,
            created_at  TEXT    NOT NULL
        );

        -- Part 2: cross-document consistency results
        CREATE TABLE IF NOT EXISTS cross_doc_checks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id     TEXT    NOT NULL,
            field        TEXT    NOT NULL,
            status       TEXT    NOT NULL,
            values_json  TEXT    NOT NULL,
            reason       TEXT,
            created_at   TEXT    NOT NULL
        );
        """)

        # Migrate: add columns that may not exist in older DBs
        _add_column_if_missing(conn, "shipments", "customer", "TEXT")
        _add_column_if_missing(conn, "fields", "doc_type", "TEXT DEFAULT 'UNKNOWN'")


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, col_def: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
    except sqlite3.OperationalError:
        pass  # column already exists


def save_checkpoint(trace_id: str, step: str, state_json: str, cost_usd: float) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO checkpoints (trace_id, step, state_json, cost_usd, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                step=excluded.step,
                state_json=excluded.state_json,
                cost_usd=excluded.cost_usd,
                created_at=excluded.created_at
        """, (trace_id, step, state_json, cost_usd, now))


def load_checkpoint(trace_id: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM checkpoints WHERE trace_id = ?", (trace_id,)
        ).fetchone()
    if row is None:
        return None
    return dict(row)


# ── Part 1: single-doc persist ────────────────────────────────────────────────

def persist_results(trace_id: str, doc_paths: list[str], extracted, validation, decision) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO shipments (trace_id, doc_paths, status, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                status=excluded.status,
                created_at=excluded.created_at
        """, (trace_id, json.dumps(doc_paths), decision.action if decision else "pending", now))

        if extracted:
            for fname in extracted.field_names():
                fv = extracted.get_field(fname)
                conn.execute("""
                    INSERT INTO fields (trace_id, field_name, value, confidence, source_snippet, source_page)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (trace_id, fname, fv.value, fv.confidence, fv.source_snippet, fv.source_page))

        if decision:
            conn.execute("""
                INSERT INTO decisions (trace_id, action, reasoning, amendment_email, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (trace_id, decision.action, decision.reasoning, decision.amendment_email, now))

        conn.execute("""
            INSERT INTO audit_log (trace_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (trace_id, "pipeline_complete", json.dumps({"action": decision.action if decision else None}), now))


# ── Part 2: multi-doc CG persist ──────────────────────────────────────────────

def persist_cg_results(ps) -> None:
    """
    Persist CG pipeline results:
    - One shipments row (with customer column)
    - One fields row per field per doc (with doc_type column)
    - Cross-doc verdicts in cross_doc_checks
    - Decision row
    """
    from nova.domain.models import PipelineState
    now = datetime.utcnow().isoformat()

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO shipments (trace_id, doc_paths, status, customer, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(trace_id) DO UPDATE SET
                status=excluded.status,
                customer=excluded.customer,
                created_at=excluded.created_at
        """, (
            ps.trace_id,
            json.dumps(ps.raw_doc_paths),
            ps.decision.action if ps.decision else "pending_cg_review",
            ps.customer,
            now,
        ))

        # Per-doc fields with doc_type
        for doc in ps.extracted_docs:
            for fname in doc.field_names():
                fv = doc.get_field(fname)
                conn.execute("""
                    INSERT INTO fields
                        (trace_id, field_name, value, confidence, source_snippet, source_page, doc_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    ps.trace_id, fname, fv.value, fv.confidence,
                    fv.source_snippet, fv.source_page, doc.doc_type,
                ))

        # Cross-doc verdicts
        if ps.cross_doc:
            for verdict in ps.cross_doc.verdicts:
                conn.execute("""
                    INSERT INTO cross_doc_checks
                        (trace_id, field, status, values_json, reason, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    ps.trace_id, verdict.field, verdict.status,
                    json.dumps(verdict.values_by_doc), verdict.reason, now,
                ))

        # Decision (store amendment_email OR approval_email)
        if ps.decision:
            email_col = ps.decision.amendment_email or ps.decision.approval_email
            conn.execute("""
                INSERT INTO decisions (trace_id, action, reasoning, amendment_email, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (ps.trace_id, ps.decision.action, ps.decision.reasoning, email_col, now))

        conn.execute("""
            INSERT INTO audit_log (trace_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            ps.trace_id, "cg_pipeline_complete",
            json.dumps({"action": ps.decision.action if ps.decision else None, "customer": ps.customer}),
            now,
        ))


def log_event(trace_id: str, event_type: str, payload: dict) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO audit_log (trace_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
        """, (trace_id, event_type, json.dumps(payload), now))
