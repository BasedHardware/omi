"""
Database operations for feedback and reporting.
"""
import hashlib
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from google.cloud import firestore

from backend.config import get_settings

settings = get_settings()


def _normalize_id(value: str) -> str:
    """Normalize and validate ID strings by stripping whitespace and checking for emptiness."""
    if not isinstance(value, str):
        raise ValueError(f"Expected string, got {type(value).__name__}")
    normalized = value.strip()
    if not normalized:
        raise ValueError("ID cannot be empty or whitespace-only")
    return normalized


def _idempotent_event_id(uid: str, feedback_id: str) -> str:
    """Generate a deterministic idempotency key from normalized inputs."""
    normalized_uid = _normalize_id(uid)
    normalized_feedback_id = _normalize_id(feedback_id)
    return hashlib.sha256(f"{normalized_uid}:{normalized_feedback_id}".encode()).hexdigest()


def get_db() -> firestore.Client:
    """Get Firestore client instance."""
    return firestore.Client(project=settings.gcp_project)


def record_feedback_event(
    uid: str,
    target_id: str,
    feedback_type: str,
    metadata: Optional[Dict[str, Any]] = None,
    feedback_id: Optional[str] = None,
) -> str:
    """
    Record a feedback event in Firestore with idempotency.
    
    Args:
        uid: User identifier (normalized)
        target_id: Target identifier (normalized)
        feedback_type: Type of feedback
        metadata: Optional additional metadata
        feedback_id: Optional explicit feedback ID (normalized if provided)
    
    Returns:
        The generated or provided feedback_id
    """
    normalized_uid = _normalize_id(uid)
    normalized_target_id = _normalize_id(target_id)
    
    if feedback_id:
        normalized_feedback_id = _normalize_id(feedback_id)
    else:
        normalized_feedback_id = _idempotent_event_id(normalized_uid, normalized_target_id)
    
    db = get_db()
    doc_ref = db.collection("feedback_events").document(normalized_feedback_id)
    
    doc_ref.set({
        "uid": normalized_uid,
        "target_id": normalized_target_id,
        "feedback_type": feedback_type,
        "metadata": metadata or {},
        "timestamp": firestore.SERVER_TIMESTAMP,
    }, merge=True)
    
    return normalized_feedback_id


def get_feedback_event(feedback_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a feedback event by its ID.
    
    Args:
        feedback_id: Feedback event identifier
    
    Returns:
        The feedback event document or None if not found
    """
    normalized_feedback_id = _normalize_id(feedback_id)
    db = get_db()
    doc_ref = db.collection("feedback_events").document(normalized_feedback_id)
    doc = doc_ref.get()
    return doc.to_dict() if doc.exists else None


def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a report by its ID.
    
    Args:
        report_id: Report identifier
    
    Returns:
        The report document or None if not found
    """
    normalized_report_id = _normalize_id(report_id)
    db = get_db()
    doc_ref = db.collection("reports").document(normalized_report_id)
    doc = doc_ref.get()
    return doc.to_dict() if doc.exists else None


def save_report(report_id: str, data: Dict[str, Any]) -> None:
    """
    Save a report to Firestore.
    
    Args:
        report_id: Report identifier (normalized)
        data: Report data to save
    """
    normalized_report_id = _normalize_id(report_id)
    if not isinstance(data, dict):
        raise ValueError("Report data must be a dictionary")
    
    db = get_db()
    db.collection("reports").document(normalized_report_id).set(data)


def list_negative_events(uid: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    List negative feedback events for a user.
    
    Args:
        uid: User identifier (normalized)
        limit: Maximum number of events to return
    
    Returns:
        List of negative feedback events
    """
    normalized_uid = _normalize_id(uid)
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("Limit must be a positive integer")
    
    db = get_db()
    query = (
        db.collection("feedback_events")
        .where("uid", "==", normalized_uid)
        .where("feedback_type", "==", "negative")
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    
    return [doc.to_dict() for doc in query.stream()]
