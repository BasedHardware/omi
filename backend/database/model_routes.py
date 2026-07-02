"""Firestore persistence for benchmark-selected LLM model routes."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ._client import db

COLLECTION = "model_router"
HISTORY_DOCUMENT = "benchmark_runs"


def _active_doc_id(profile: str) -> str:
    safe_profile = "".join(ch for ch in profile if ch.isalnum() or ch in ("-", "_")) or "default"
    return f"active_routes_{safe_profile}"


def get_active_model_routes(profile: str) -> Optional[Dict[str, Any]]:
    doc = db.collection(COLLECTION).document(_active_doc_id(profile)).get()
    if not doc.exists:
        return None
    return doc.to_dict() or None


def set_active_model_routes(profile: str, route_table: Dict[str, Any]) -> None:
    payload = dict(route_table)
    payload["profile"] = profile
    payload["stored_at"] = datetime.now(timezone.utc)
    db.collection(COLLECTION).document(_active_doc_id(profile)).set(payload)


def record_model_route_run(profile: str, route_table: Dict[str, Any]) -> None:
    updated_at = route_table.get("updated_at") or datetime.now(timezone.utc).isoformat()
    doc_id = f"{profile}_{str(updated_at).replace(':', '-').replace('.', '-')}"
    payload = dict(route_table)
    payload["profile"] = profile
    payload["stored_at"] = datetime.now(timezone.utc)
    db.collection(COLLECTION).document(HISTORY_DOCUMENT).collection(profile).document(doc_id).set(payload)
