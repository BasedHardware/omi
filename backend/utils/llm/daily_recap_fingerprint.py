"""Daily recap idempotency follows input revisions, never the scheduler's date alone."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

FINGERPRINT_FIELD = 'notes_input_fingerprint'
_REVISION_FIELDS = (
    'revision',
    'sync_content_revision',
    'content_revision',
    'updated_at',
    'notes_llm_output_hash',
    'discarded',
    'content_kind',
    'is_locked',
)
_CONTENT_FIELDS = ('structured', 'apps_results')


def input_fingerprint(conversations: Sequence[Mapping[str, Any]], *, extra_revision_fields: Sequence[str] = ()) -> str:
    """IDs plus revisions; hash summary inputs as a safety net for legacy unversioned writes.

    Raw transcripts never enter the digest. Order is immaterial. No fingerprint or
    conversation identifiers are logged; only agree/disagree counters are emitted.
    """
    entries = [
        {key: row.get(key) for key in ('id', *_REVISION_FIELDS, *_CONTENT_FIELDS, *extra_revision_fields)}
        for row in conversations
    ]
    entries.sort(key=lambda row: str(row.get('id') or ''))
    encoded = json.dumps(entries, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
