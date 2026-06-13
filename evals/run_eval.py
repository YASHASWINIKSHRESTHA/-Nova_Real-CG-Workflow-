"""
Eval harness: run the Extractor over the gold set and compute:
  - Per-field precision/recall (exact match)
  - Calibration: does confidence bucket match actual accuracy?
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

# Ensure nova is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from nova.agents.extractor import extract

GOLD_CSV = Path(__file__).parent / "gold.csv"

_CONFIDENCE_BUCKETS = [
    (0.0, 0.50, "low [0.0–0.5)"),
    (0.50, 0.85, "mid [0.5–0.85)"),
    (0.85, 1.01, "high [0.85–1.0]"),
]


def _normalize(value: str) -> str:
    return (value or "").strip().upper().replace(",", "").replace("  ", " ")


def _values_match(extracted: str, truth: str) -> bool:
    return _normalize(extracted) == _normalize(truth)


def run_eval():
    print("Loading gold set...")
    gold_rows = []
    with open(GOLD_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            gold_rows.append(row)

    # Group by doc_id → get unique (doc_id, doc_path) pairs
    docs: dict[str, str] = {}
    doc_fields: dict[str, list[dict]] = defaultdict(list)
    for row in gold_rows:
        docs[row["doc_id"]] = row["doc_path"]
        doc_fields[row["doc_id"]].append(row)

    print(f"Evaluating {len(docs)} documents ({len(gold_rows)} field instances)...\n")

    # Per-field stats
    field_correct: dict[str, int] = defaultdict(int)
    field_total: dict[str, int] = defaultdict(int)

    # Calibration: (bucket_label → list of (predicted_correct: bool, confidence: float))
    calibration: dict[str, list[tuple[bool, float]]] = defaultdict(list)

    total_cost = 0.0

    for doc_id, doc_path in docs.items():
        full_path = Path(__file__).parent.parent / doc_path
        if not full_path.exists():
            print(f"  [SKIP] {doc_path} not found")
            continue

        print(f"  Extracting {doc_id}: {doc_path}...")
        try:
            extracted_doc, cost = extract([str(full_path)])
            total_cost += cost
        except Exception as e:
            print(f"  [ERROR] {doc_id}: {e}")
            continue

        for gold_row in doc_fields[doc_id]:
            fname = gold_row["field_name"]
            true_value = gold_row["true_value"]

            try:
                fv = extracted_doc.get_field(fname)
            except AttributeError:
                continue

            is_correct = _values_match(fv.value or "", true_value)
            field_total[fname] += 1
            if is_correct:
                field_correct[fname] += 1

            conf = fv.confidence
            for lo, hi, label in _CONFIDENCE_BUCKETS:
                if lo <= conf < hi:
                    calibration[label].append((is_correct, conf))
                    break

    # ── Print per-field precision/recall ──
    print("\n" + "=" * 70)
    print(f"{'FIELD':<30} {'CORRECT':>8} {'TOTAL':>8} {'ACCURACY':>10}")
    print("-" * 70)
    all_correct = sum(field_correct.values())
    all_total = sum(field_total.values())
    for fname in sorted(field_total.keys()):
        c = field_correct[fname]
        t = field_total[fname]
        acc = c / t if t > 0 else 0.0
        print(f"{fname:<30} {c:>8} {t:>8} {acc:>9.0%}")
    print("-" * 70)
    overall_acc = all_correct / all_total if all_total > 0 else 0.0
    print(f"{'OVERALL':<30} {all_correct:>8} {all_total:>8} {overall_acc:>9.0%}")

    # ── Print calibration ──
    print("\n" + "=" * 70)
    print("CALIBRATION (does confidence bucket ≈ actual accuracy?)")
    print(f"{'BUCKET':<25} {'SAMPLES':>8} {'ACTUAL ACC':>12} {'MEAN CONF':>12} {'CALIBRATION ERR':>16}")
    print("-" * 70)
    for lo, hi, label in _CONFIDENCE_BUCKETS:
        pairs = calibration.get(label, [])
        if not pairs:
            print(f"{label:<25} {'—':>8}")
            continue
        n = len(pairs)
        actual_acc = sum(1 for correct, _ in pairs if correct) / n
        mean_conf = sum(conf for _, conf in pairs) / n
        calib_err = abs(actual_acc - mean_conf)
        flag = " ✓" if calib_err <= 0.10 else " ✗ (overconfident)" if mean_conf > actual_acc else " ✗ (underconfident)"
        print(f"{label:<25} {n:>8} {actual_acc:>11.0%} {mean_conf:>11.0%} {calib_err:>14.2f}{flag}")

    print("\n" + "=" * 70)
    print(f"Total extraction cost: ${total_cost:.4f}")
    print("=" * 70)


if __name__ == "__main__":
    run_eval()
