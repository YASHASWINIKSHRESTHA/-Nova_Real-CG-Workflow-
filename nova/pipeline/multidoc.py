"""
Multi-document extraction: run the Part 1 extractor once per attachment.
Preserves per-doc provenance — the BOL, Invoice, and Packing List each get
their own ExtractedDoc with their own doc_type and source snippets.
Calls are independent GPT-4o vision calls (I/O-bound), so a thread pool
reduces wall-clock to ~1× extraction time regardless of attachment count.
"""
from concurrent.futures import ThreadPoolExecutor

from nova.agents.extractor import extract
from nova.domain.models import ExtractedDoc


def extract_all(
    attachment_paths: list[str],
    max_workers: int = 4,
) -> tuple[list[ExtractedDoc], float]:
    """
    Extract each attachment in parallel. Returns (list_of_ExtractedDoc, total_cost_usd).
    Order is preserved (pool.map guarantees input order).
    Cost is identical to sequential — same tokens, better latency.
    Falls back to serial execution if threading raises a RuntimeError
    (e.g. certain Streamlit versions block thread-local context access).
    """
    n = max(1, len(attachment_paths))
    try:
        with ThreadPoolExecutor(max_workers=min(max_workers, n)) as pool:
            results = list(pool.map(lambda p: extract([p]), attachment_paths))
    except RuntimeError:
        results = [extract([p]) for p in attachment_paths]
    docs = [doc for doc, _ in results]
    total_cost = sum(cost for _, cost in results)
    return docs, total_cost
