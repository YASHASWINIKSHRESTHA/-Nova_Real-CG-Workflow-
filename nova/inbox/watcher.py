"""
Mock SU inbox. A folder under inbox/incoming/ == one email with N attachments.
poll_once()        → new shipment folders not yet in processing/
mark_processing()  → moves folder from incoming/ to processing/ (acts as a lock)
mark_processed()   → moves folder from processing/ to processed/
save_result()      → writes _result.json + _state.json into the folder
load_result()      → reads _result.json from a folder
"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

INBOX = Path(__file__).parent.parent.parent / "inbox"

_ATTACHMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def poll_once() -> list[Path]:
    """Return unprocessed shipment folders in inbox/incoming/."""
    incoming = INBOX / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in incoming.iterdir() if p.is_dir())


def read_email(folder: Path) -> dict:
    """Read email.json from a shipment folder."""
    email_file = folder / "email.json"
    if not email_file.exists():
        return {}
    return json.loads(email_file.read_text(encoding="utf-8"))


def attachments(folder: Path) -> list[str]:
    """Return absolute paths of all attachment files (PDF/image) in a folder."""
    return sorted(
        str(p) for p in folder.iterdir()
        if p.suffix.lower() in _ATTACHMENT_EXTENSIONS
    )


def mark_processing(folder: Path) -> Path:
    """Move folder from incoming/ to processing/ (acts as a processing lock)."""
    dest = INBOX / "processing" / folder.name
    (INBOX / "processing").mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.move(str(folder), str(dest))
    return dest


def mark_processed(folder: Path) -> Path:
    """Move folder from processing/ (or incoming/) to processed/."""
    dest = INBOX / "processed" / folder.name
    (INBOX / "processed").mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(str(dest))
    shutil.move(str(folder), str(dest))
    return dest


def save_result(folder: Path, trace_id: str, status: str, state_json: str) -> None:
    """
    Write _result.json and _state.json into the folder.
    _result.json   — lightweight meta (trace_id, status, timestamps)
    _state.json    — full serialised PipelineState for UI reconstruction
    """
    result = {
        "trace_id": trace_id,
        "status": status,
        "processed_at": datetime.utcnow().isoformat(),
        "reply_sent": False,
        "sent_at": None,
    }
    (folder / "_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (folder / "_state.json").write_text(state_json, encoding="utf-8")


def load_result(folder: Path) -> Optional[dict]:
    """Read _result.json from a folder. Returns None if not present."""
    result_file = folder / "_result.json"
    if not result_file.exists():
        return None
    try:
        return json.loads(result_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def mark_reply_sent(folder: Path, edited_email: str) -> None:
    """Update _result.json to record that the CG operator sent the reply."""
    result_file = folder / "_result.json"
    if not result_file.exists():
        return
    result = json.loads(result_file.read_text(encoding="utf-8"))
    result["reply_sent"] = True
    result["sent_at"] = datetime.utcnow().isoformat()
    result["sent_email"] = edited_email
    result_file.write_text(json.dumps(result, indent=2), encoding="utf-8")


def list_all_shipments() -> list[dict]:
    """
    Return all shipment folders across incoming/, processing/, processed/,
    sorted newest-first within each group.
    """
    result = []
    for phase in ("incoming", "processing", "processed"):
        phase_dir = INBOX / phase
        if not phase_dir.exists():
            continue
        for folder in sorted(phase_dir.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            email = read_email(folder)
            res = load_result(folder)
            result.append({
                "folder": folder,
                "phase": phase,
                "name": folder.name,
                "customer": email.get("customer", "Unknown"),
                "subject": email.get("subject", folder.name),
                "received_at": email.get("received_at", ""),
                "from_addr": email.get("from", ""),
                "n_attachments": len(attachments(folder)),
                "trace_id": res.get("trace_id") if res else None,
                "status": res.get("status") if res else None,
                "reply_sent": res.get("reply_sent", False) if res else False,
            })
    return result
