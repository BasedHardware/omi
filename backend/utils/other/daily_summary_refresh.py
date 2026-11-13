"""Legacy recap refresh identity. Metadata writes never revise content."""

import hashlib
import json
import math
from datetime import datetime, timezone

FIELD = 'late_input_fingerprint_v1'


class RefreshedSummary(dict):
    """Per-call delivery/metric signal; never persisted as a document flag."""


# Generic `revision` is deliberately absent: starring also advances it.
REVISION_FIELDS = (
    'sync_content_revision',
    'content_revision',
    'notes_llm_output_hash',
    'summary_completed_at',
    'discarded',
    'deleted',
    'is_locked',
    'content_kind',
    'relevance_decision',
    'sync_relevance_user_kept',
)


def fingerprint(rows):
    """Membership, content provenance and legacy summary content; no transcript or update_time.

    Only descriptions of action items participate, never checkbox state. Location,
    folders, stars and geocoding do not participate. Legacy summary text is the
    fallback for producers without a revision/hash; only the digest is persisted.
    """
    entries = []
    for row in rows:
        structured = row.get('structured') or {}
        entries.append(
            {
                'id': row.get('id'),
                **{key: row.get(key) for key in REVISION_FIELDS},
                'summary': {key: structured.get(key) for key in ('title', 'overview', 'sections')},
                'actions': [item.get('description') for item in structured.get('action_items') or []],
                'events': [
                    {key: event.get(key) for key in ('title', 'description', 'start', 'duration')}
                    for event in structured.get('events') or []
                ],
                'apps': [item.get('content') for item in row.get('apps_results') or []],
            }
        )
    entries.sort(key=lambda entry: str(entry['id']))
    return hashlib.sha256(json.dumps(entries, sort_keys=True, default=str).encode()).hexdigest()


def _timestamp(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp()
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
        except ValueError:
            pass
    return None


def adoption_needs_repair(existing, rows):
    """Unknown content age is repair debt, not proof that a legacy recap is fresh."""
    generated = _timestamp(existing.get('generated_at'))
    if generated is None:
        return True
    for row in rows:
        completed = _timestamp(row.get('summary_completed_at'))
        created = _timestamp(row.get('created_at'))
        if completed is None or created is None or completed > generated or created > generated:
            return True
        # An ordinal cannot be compared to generation wall time. Conservatively
        # repair legacy multi-revision input once, even if its first completion is old.
        if (row.get('sync_content_revision') or 0) > 1 or (row.get('content_revision') or 0) > 1:
            return True
    return False
