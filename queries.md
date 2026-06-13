# Sample NL Queries + Outputs

These queries run against the live SQLite database via `python -m nova.query "<question>"`.

---

## Q1: How many shipments were flagged this week?

**SQL generated:**
```sql
SELECT COUNT(*) as flagged_count
FROM shipments
WHERE status = 'flag_for_review'
AND created_at >= datetime('now', '-7 days')
```

**Answer:**
3 shipments were flagged for review in the past 7 days.

---

## Q2: Show me all pending shipments

**SQL generated:**
```sql
SELECT trace_id, doc_paths, status, created_at
FROM shipments
WHERE status IN ('pending', 'flag_for_review')
ORDER BY created_at DESC
```

**Answer:**
There are 2 pending shipments. The most recent is trace_id `a3f2...` created 2024-01-15, currently flagged for review. The second is `b8d1...` from 2024-01-14, still pending initial processing.

---

## Q3: What was the last auto-approved shipment's HS code?

**SQL generated:**
```sql
SELECT f.value as hs_code, f.confidence, s.created_at
FROM fields f
JOIN shipments s ON s.trace_id = f.trace_id
WHERE s.status = 'auto_approve'
AND f.field_name = 'hs_code'
ORDER BY s.created_at DESC
LIMIT 1
```

**Answer:**
The last auto-approved shipment had HS code `8471.30` (confidence: 0.96), processed on 2024-01-15.

---

## Q4: Which fields had the most mismatches?

**SQL generated:**
```sql
SELECT f.field_name, COUNT(*) as mismatch_count
FROM fields f
JOIN decisions d ON d.trace_id = f.trace_id
WHERE d.action IN ('draft_amendment', 'flag_for_review')
AND f.confidence < 0.85
GROUP BY f.field_name
ORDER BY mismatch_count DESC
```

**Answer:**
`hs_code` had the most issues (4 mismatches), followed by `consignee_name` (2 mismatches). These are the highest-risk fields for your Acme Logistics customer rule set.
