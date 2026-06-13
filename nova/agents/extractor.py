"""
Extractor agent: PDF/image → ExtractedDoc with per-field evidence.
Every field MUST have a source_snippet; missing snippet → confidence capped at 0.3.
"""
import json
import sys
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from nova.infrastructure.llm import call_vision, parse_json_response
from nova.domain.models import ExtractedDoc, FieldValue

_EXTRACTION_PROMPT = """You are a trade-document extraction specialist. Extract the following 8 fields from the document image(s).

Fields to extract:
1. consignee_name      — the name of the consignee / importer
2. hs_code             — Harmonized System code (tariff classification)
3. port_of_loading     — origin port
4. port_of_discharge   — destination port
5. incoterms           — trade terms (e.g. FOB, CIF, EXW)
6. description_of_goods — description of the cargo/goods
7. gross_weight        — total gross weight with unit
8. invoice_number      — invoice or bill-of-lading reference number

Return ONLY a JSON object with this exact structure (no prose, no markdown fences):
{
  "doc_type": "<BOL|INVOICE|PACKING_LIST|OTHER>",
  "consignee_name":      {"value": "...", "confidence": 0.95, "source_snippet": "exact text from doc", "source_page": 1},
  "hs_code":             {"value": "...", "confidence": 0.90, "source_snippet": "exact text from doc", "source_page": 1},
  "port_of_loading":     {"value": "...", "confidence": 0.95, "source_snippet": "exact text from doc", "source_page": 1},
  "port_of_discharge":   {"value": "...", "confidence": 0.95, "source_snippet": "exact text from doc", "source_page": 1},
  "incoterms":           {"value": "...", "confidence": 0.90, "source_snippet": "exact text from doc", "source_page": 1},
  "description_of_goods":{"value": "...", "confidence": 0.85, "source_snippet": "exact text from doc", "source_page": 1},
  "gross_weight":        {"value": "...", "confidence": 0.90, "source_snippet": "exact text from doc", "source_page": 1},
  "invoice_number":      {"value": "...", "confidence": 0.95, "source_snippet": "exact text from doc", "source_page": 1}
}

RULES:
- source_snippet MUST be verbatim text found in the document. Copy it exactly.
- If you cannot find a field, set value=null, confidence=0.1, source_snippet=null, source_page=null.
- confidence reflects how certain you are (0.0 to 1.0).
- Never fabricate values. If unsure, lower confidence and include partial evidence.
"""


def _render_pdf_pages(pdf_path: str, dpi: int = 150) -> list[bytes]:
    """Render each PDF page to PNG bytes in memory (no temp files)."""
    doc = fitz.open(pdf_path)
    pages_bytes = []
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        pages_bytes.append(pix.tobytes("png"))
    doc.close()
    return pages_bytes


def _load_images(doc_paths: list[str], dpi: int = 150) -> list[str | bytes]:
    """Convert doc paths to image file paths (for JPEG/PNG) or PNG bytes (for PDF)."""
    images: list[str | bytes] = []
    for path in doc_paths:
        suffix = Path(path).suffix.lower()
        if suffix == ".pdf":
            images.extend(_render_pdf_pages(path, dpi=dpi))
        else:
            images.append(path)
    return images


def _count_missing_snippets(data: dict) -> int:
    field_keys = [
        "consignee_name", "hs_code", "port_of_loading", "port_of_discharge",
        "incoterms", "description_of_goods", "gross_weight", "invoice_number",
    ]
    return sum(1 for k in field_keys if not data.get(k, {}).get("source_snippet"))


def extract(doc_paths: list[str], retries: int = 0) -> tuple[ExtractedDoc, float]:
    """
    Run extraction on one or more doc paths.
    Returns (ExtractedDoc, cost_usd).
    Fallback: if >50% fields lack snippets, re-render at 2x DPI and retry once.
    """
    dpi = 150
    image_paths = _load_images(doc_paths, dpi=dpi)

    raw, cost = call_vision(image_paths, _EXTRACTION_PROMPT)
    data = parse_json_response(raw)

    missing = _count_missing_snippets(data)
    total_fields = 8
    if missing > total_fields / 2 and retries < 1:
        print(f"[extractor] {missing}/{total_fields} fields lack snippets — retrying at 2x DPI")
        image_paths_hd = _load_images(doc_paths, dpi=300)
        raw2, cost2 = call_vision(image_paths_hd, _EXTRACTION_PROMPT)
        data = parse_json_response(raw2)
        cost += cost2

    extracted = ExtractedDoc(**data)
    return extracted, cost


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "samples/clean_bol.pdf"
    doc, cost = extract([path])
    print(doc.model_dump_json(indent=2))
    print(f"\nTotal cost: ${cost:.6f}")
