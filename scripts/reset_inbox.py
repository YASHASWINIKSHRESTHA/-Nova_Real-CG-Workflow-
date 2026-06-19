"""
Reset the inbox to a clean demo state:
  - inbox/incoming/  → 2 fresh shipments (ACME_001, ACME_002) with source docs only
  - inbox/processing/ → empty
  - inbox/processed/  → empty

Run before every demo or after processing shipments.
Usage: python scripts/reset_inbox.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
INBOX = ROOT / "inbox"

INCOMING   = INBOX / "incoming"
PROCESSING = INBOX / "processing"
PROCESSED  = INBOX / "processed"

ARTIFACT_NAMES = {"_result.json", "_state.json"}


def _wipe_folder(folder: Path) -> None:
    for child in folder.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
            print(f"  removed {child.relative_to(ROOT)}")


def _strip_artifacts(folder: Path) -> None:
    """Remove pipeline artifacts (_result.json, _state.json) inside a shipment folder."""
    for name in ARTIFACT_NAMES:
        target = folder / name
        if target.exists():
            target.unlink()
            print(f"  removed {target.relative_to(ROOT)}")


def _write_email_json(folder: Path, data: dict) -> None:
    path = folder / "email.json"
    path.write_text(json.dumps(data, indent=2))


def main() -> None:
    print("=== Nova inbox reset ===\n")

    # 1. Clear processing/ and processed/
    print("[1/3] Clearing processing/ ...")
    _wipe_folder(PROCESSING)

    print("[2/3] Clearing processed/ ...")
    _wipe_folder(PROCESSED)

    # 2. Strip any artifacts left in incoming/
    print("[3/3] Stripping artifacts from incoming/ ...")
    for shipment_dir in INCOMING.iterdir():
        if shipment_dir.is_dir():
            _strip_artifacts(shipment_dir)

    # 3. Regenerate PDFs and email.json for both shipments
    print("\n[4/4] Regenerating sample documents ...")
    try:
        sys.path.insert(0, str(ROOT))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "generate_inbox_samples",
            ROOT / "scripts" / "generate_inbox_samples.py",
        )
        gen = importlib.util.module_from_spec(spec)  # type: ignore
        spec.loader.exec_module(gen)  # type: ignore
        gen.main()
    except Exception as exc:
        print(f"  WARNING: could not regenerate PDFs — {exc}")
        print("  Run: python scripts/generate_inbox_samples.py  manually.")

    # 4. Ensure email.json exists for both shipments
    _write_email_json(
        INCOMING / "shipment_ACME_001",
        {
            "message_id": "su-acme-2026-001",
            "from": "exports@acme-supplier.com",
            "to": "cg@gocomet.com",
            "subject": "Shipment docs — PO 4471 — ACME Logistics (CLEAN)",
            "body": (
                "Dear GoComet CG team,\n\nPlease find attached the Bill of Lading, "
                "Commercial Invoice, and Packing List for shipment PO-4471. All documents "
                "have been prepared per the agreed terms (FOB Shanghai, HS 8471.30).\n\n"
                "Kindly confirm clearance at your earliest convenience.\n\n"
                "Best regards,\nTech Export Co Ltd"
            ),
            "customer": "Acme Logistics",
            "received_at": "2026-06-13T09:00:00",
        },
    )
    _write_email_json(
        INCOMING / "shipment_ACME_002",
        {
            "message_id": "su-acme-2026-002",
            "from": "exports@guangzhou-parts.com",
            "to": "cg@gocomet.com",
            "subject": "Shipment docs — PO 4472 — ACME Logistics",
            "body": (
                "Dear GoComet CG team,\n\nPlease find attached the Bill of Lading, "
                "Commercial Invoice, and Packing List for shipment PO-4472 (Guangzhou origin). "
                "Documents prepared per agreed FOB terms.\n\nKindly process clearance.\n\n"
                "Best regards,\nGuangzhou Parts Co Ltd"
            ),
            "customer": "Acme Logistics",
            "received_at": "2026-06-13T10:30:00",
        },
    )

    print("\n=== Reset complete ===")
    print(f"  incoming/: {list(p.name for p in INCOMING.iterdir() if p.is_dir())}")
    print("  processing/: empty")
    print("  processed/:  empty")
    print("\nApp will show 2 NEW shipments on next page load.")


if __name__ == "__main__":
    main()
