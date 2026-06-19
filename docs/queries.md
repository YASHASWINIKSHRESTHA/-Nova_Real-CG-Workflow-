# Sample NL Queries + Real Outputs

These queries were run against the live SQLite database (`nova.db`) after processing
shipment ACME_002 (cross-doc HS code mismatch: BOL 8471.30 vs INVOICE 9999.99).

Run via: `python -m nova.query "<question>"` or the NL Query tab in `app_cg.py`.

---

## Q1: How many shipments were processed this week?

**SQL generated:**
```sql
SELECT COUNT(*) AS n
FROM shipments
WHERE created_at >= datetime('now', '-7 days')
```

**Raw result:**
```json
[{"n": 1}]
```

**Answer:**
1 shipment was processed this week (shipment_ACME_002, customer: Acme Logistics,
processed on 2026-06-13 — triggered a draft amendment due to a cross-document
HS code inconsistency).

---

## Q2: Which shipments had cross-document HS code mismatches?

**SQL generated:**
```sql
SELECT s.trace_id, s.customer, s.status, s.created_at,
       c.field, c.status AS cross_status, c.reason
FROM shipments s
JOIN cross_doc_checks c ON s.trace_id = c.trace_id
WHERE c.field = 'hs_code' AND c.status = 'inconsistent'
ORDER BY s.created_at DESC
```

**Raw result:**
```json
[{
  "trace_id": "79384e2b-8146-4116-a662-6d881840cc4e",
  "customer": "Acme Logistics",
  "status": "draft_amendment",
  "created_at": "2026-06-13T19:05:26.470243",
  "field": "hs_code",
  "cross_status": "inconsistent",
  "reason": "hs_code differs across documents: BOL: '8471.30', INVOICE: '9999.99', PACKING_LIST: '8471.30'"
}]
```

**Answer:**
1 shipment had a cross-document HS code mismatch: Acme Logistics shipment processed
on 2026-06-13. The BOL and Packing List both show HS 8471.30, but the Commercial
Invoice shows 9999.99. A draft amendment was generated; the agent did not auto-send.

---

## Q3: Show me the HS codes across all documents for the latest shipment

**SQL generated:**
```sql
SELECT f.value AS hs_code, f.confidence, s.customer, s.created_at
FROM fields f
JOIN shipments s ON s.trace_id = f.trace_id
WHERE f.field_name = 'hs_code'
ORDER BY s.created_at DESC
```

**Raw result:**
```json
[
  {"hs_code": "8471.30", "confidence": 0.9, "customer": "Acme Logistics", "created_at": "2026-06-13T19:05:26.470243"},
  {"hs_code": "9999.99", "confidence": 0.9, "customer": "Acme Logistics", "created_at": "2026-06-13T19:05:26.470243"},
  {"hs_code": "8471.30", "confidence": 0.9, "customer": "Acme Logistics", "created_at": "2026-06-13T19:05:26.470243"}
]
```

**Answer:**
The latest Acme Logistics shipment (2026-06-13) has three HS code values — one per
document. BOL: 8471.30 (90% confidence), Commercial Invoice: 9999.99 (90% confidence),
Packing List: 8471.30 (90% confidence). The INVOICE value is the outlier that
triggered the cross-document inconsistency flag and the draft amendment.

---

## Q4: Show me everything pending review for Acme Logistics

**SQL generated:**
```sql
SELECT s.trace_id, s.customer, s.status, s.created_at,
       d.action, d.reasoning
FROM shipments s
LEFT JOIN decisions d ON s.trace_id = d.trace_id
WHERE s.customer = 'Acme Logistics'
ORDER BY s.created_at DESC
```

**Raw result:**
```json
[{
  "trace_id": "79384e2b-8146-4116-a662-6d881840cc4e",
  "customer": "Acme Logistics",
  "status": "draft_amendment",
  "created_at": "2026-06-13T19:05:26.470243",
  "action": "draft_amendment",
  "reasoning": "Cross-document inconsistency detected — amendment required:\n  • hs_code: BOL: '8471.30' | INVOICE: '9999.99' | PACKING_LIST: '8471.30'"
}]
```

**Answer:**
1 Acme Logistics shipment is pending CG action (status: draft_amendment). It was
processed on 2026-06-13. The cross-document consistency check flagged hs_code as
inconsistent — the BOL and Packing List agree on 8471.30 but the Commercial Invoice
shows 9999.99. A draft amendment email has been prepared for CG review. The agent has
not sent it; dispatch requires a human CG operator click.
