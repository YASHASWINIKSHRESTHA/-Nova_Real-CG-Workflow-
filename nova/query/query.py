"""
NL query: natural language → GPT-4o-mini function-calling → safe read-only SQL → grounded answer.
Rejects any non-SELECT SQL.
"""
import json
import re
import sqlite3

from nova.infrastructure import database as db
from nova.infrastructure.llm import call_text

_SCHEMA_DESCRIPTION = """
SQLite database schema:

- shipments(id, trace_id TEXT, doc_paths TEXT, status TEXT, customer TEXT, created_at TEXT)
  status values: 'auto_approve', 'flag_for_review', 'draft_amendment', 'pending', 'pending_cg_review'
  customer: name of the supplier / consignee (e.g. 'Acme Logistics')
  doc_paths: JSON array of file paths for all attachments in the shipment

- fields(id, trace_id TEXT, field_name TEXT, value TEXT, confidence REAL,
         source_snippet TEXT, source_page INTEGER, doc_type TEXT)
  field_name values: consignee_name, hs_code, port_of_loading, port_of_discharge,
                     incoterms, description_of_goods, gross_weight, invoice_number
  doc_type: BOL, INVOICE, PACKING_LIST, OTHER
  confidence: 0.0–1.0; >= 0.85 is high confidence

- decisions(id, trace_id TEXT, action TEXT, reasoning TEXT, amendment_email TEXT, created_at TEXT)
  action values: 'auto_approve', 'flag_for_review', 'draft_amendment'
  amendment_email: pre-drafted email text (may contain approval email for auto_approve shipments)

- audit_log(id, trace_id TEXT, event_type TEXT, payload_json TEXT, created_at TEXT)
  event_type values: email_received, extracted_all, validated_all, cross_validated,
                     routed_shipment, persisted_shipment, pending_cg_review,
                     reply_sent, pipeline_complete, cg_pipeline_complete

- cross_doc_checks(id, trace_id TEXT, field TEXT, status TEXT, values_json TEXT, reason TEXT, created_at TEXT)
  status values: 'consistent', 'inconsistent', 'insufficient_data'
  field values: consignee_name, hs_code, invoice_number
  values_json: JSON object mapping doc_type → extracted value

All dates are ISO 8601 strings (e.g., '2026-06-13T09:00:00').
Join shipments → decisions on trace_id; join shipments → cross_doc_checks on trace_id.
"""

_SQL_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "run_query",
            "description": "Execute a read-only SELECT SQL query against the shipments database",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A valid SQLite SELECT statement. Must start with SELECT.",
                    },
                    "explanation": {
                        "type": "string",
                        "description": "One sentence explaining what this query does",
                    },
                },
                "required": ["sql", "explanation"],
            },
        },
    }
]


def _is_safe_select(sql: str) -> bool:
    """Only allow SELECT statements; block any destructive or write SQL."""
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return False
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "ATTACH", "PRAGMA"]
    for kw in forbidden:
        if re.search(r"\b" + kw + r"\b", stripped):
            return False
    return True


def _execute_query(sql: str) -> list[dict]:
    conn = db.get_conn()
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def ask(question: str) -> dict:
    """
    Ask a natural language question about shipments.
    Returns {"question": ..., "sql": ..., "rows": [...], "answer": ...}.
    """
    system = (
        "You are a logistics data analyst. Given a natural language question about shipment data, "
        "generate a safe, read-only SQLite SELECT query to answer it.\n\n"
        f"{_SCHEMA_DESCRIPTION}"
    )

    raw, cost1 = call_text(
        f"Question: {question}",
        system=system,
        tools=_SQL_TOOL,
        tool_choice={"type": "function", "function": {"name": "run_query"}},
    )

    try:
        args = json.loads(raw)
        sql = args.get("sql", "")
        explanation = args.get("explanation", "")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {
            "question": question,
            "sql": None,
            "rows": [],
            "answer": "Could not generate a valid SQL query for this question.",
            "cost_usd": cost1,
        }

    if not _is_safe_select(sql):
        return {
            "question": question,
            "sql": sql,
            "rows": [],
            "answer": f"Query rejected: only read-only SELECT statements are allowed. Generated: {sql}",
            "cost_usd": cost1,
        }

    try:
        rows = _execute_query(sql)
    except sqlite3.Error as e:
        return {
            "question": question,
            "sql": sql,
            "rows": [],
            "answer": f"SQL error: {e}",
            "cost_usd": cost1,
        }

    rows_text = json.dumps(rows[:20], indent=2) if rows else "[]"
    answer_prompt = (
        f"Question: {question}\n\n"
        f"SQL query: {sql}\n\n"
        f"Results ({len(rows)} rows):\n{rows_text}\n\n"
        "Write a concise, grounded answer citing the actual values from the results. "
        "If the results are empty, say so clearly."
    )
    answer_text, cost2 = call_text(answer_prompt)

    return {
        "question": question,
        "sql": sql,
        "explanation": explanation,
        "rows": rows,
        "answer": answer_text.strip(),
        "cost_usd": cost1 + cost2,
    }


if __name__ == "__main__":
    import sys
    db.init_db()
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "How many shipments are in the database?"
    result = ask(question)
    print(f"Q: {result['question']}")
    print(f"SQL: {result['sql']}")
    print(f"Rows: {len(result['rows'])}")
    print(f"Answer: {result['answer']}")
    print(f"Cost: ${result['cost_usd']:.6f}")
