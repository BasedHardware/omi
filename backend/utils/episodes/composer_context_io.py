"""Owner-scoped, bounded profile projections for episode context only."""

from typing import Any


def profile(uid: str, budget: Any) -> dict:
    from database._client import db

    budget.check()
    doc = (
        db.collection('users')
        .document(uid)
        .get(field_paths=['ai_user_profile'], timeout=budget.rpc_timeout(), retry=None)
    )
    budget.charge(1)
    return (doc.to_dict() or {}).get('ai_user_profile') or {}


def goals(uid: str, budget: Any) -> list[dict]:
    from database._client import db
    from google.cloud.firestore_v1 import FieldFilter
    from utils.other.list_budget import budgeted_stream_list

    # A bounded active subset is enough background; do not scan/sort all goals.
    query = db.collection('users').document(uid).collection('goals')
    query = query.where(filter=FieldFilter('is_active', '==', True)).limit(5).select(['title', 'description', 'status'])
    return [
        row.to_dict() or {}
        for row in budgeted_stream_list(query, budget)
        if (row.to_dict() or {}).get('status') not in {'achieved', 'abandoned'}
    ]


def people(uid: str, ids: list[str], budget: Any) -> list[dict]:
    from database._client import db

    if not ids:
        return []
    budget.check()
    collection = db.collection('users').document(uid).collection('people')
    refs = [collection.document(pid) for pid in ids[:20]]
    docs = list(
        db.get_all(
            refs,
            field_paths=['name', 'relationship', 'description', 'is_dismissed'],
            timeout=budget.rpc_timeout(),
            retry=None,
        )
    )
    budget.charge(len(refs))
    return [row.to_dict() or {} for row in docs if row.exists]
