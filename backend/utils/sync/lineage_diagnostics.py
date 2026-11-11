"""Shared first-exclusion classification for recording-lineage candidates.

``recording_lineage._generations`` filters candidate rows and the no-rows
recording-id probe explains why one specific row could not be returned, so both
must classify the same way. This one pure classifier returns fixed tokens only —
never ids, field values, transcript text or exception messages — so emitted
diagnostics can never disagree with the filter or leak user data.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from utils.sync.recording_session_target import clean_text, source_value, unix_seconds

EXCLUSION_PRECEDENCE = (
    'dropped_invalid',
    'dropped_unstamped',
    'dropped_deleted',
    'dropped_source',
    'dropped_device',
    'dropped_lock',
    'dropped_interval',
)


def classify_generation_row(
    row: Mapping[str, Any], *, origin_id: str, source: Any, client_device_id: Any, is_locked: bool
) -> Optional[str]:
    """The first lineage-filter stage that rejects ``row``, or None when it is a candidate.

    ``source``/``client_device_id``/``is_locked`` are the already-normalized
    upload values; the row is compared against them field by field.
    """
    row_id = clean_text(row.get('id'))
    if not row_id:
        return 'dropped_invalid'
    external = row.get('external_data')
    external = external if isinstance(external, Mapping) else {}
    if origin_id not in (
        clean_text(external.get('recording_origin_id')),
        clean_text(external.get('recording_session_id')),
    ):
        return 'dropped_unstamped'
    # Only redirect tombstones stay in the lineage; nothing else sets deleted.
    if row.get('deleted') and not clean_text(row.get('sync_merged_into')):
        return 'dropped_deleted'
    if source_value(row.get('source')) != source:
        return 'dropped_source'
    if clean_text(row.get('client_device_id')) != client_device_id:
        return 'dropped_device'
    if bool(row.get('is_locked')) != is_locked:
        return 'dropped_lock'
    start, end = unix_seconds(row.get('started_at')), unix_seconds(row.get('finished_at'))
    if start is None or end is None or end < start:
        return 'dropped_interval'
    return None


def probe_token(
    row: Optional[Mapping[str, Any]], *, origin_id: str, source: Any, client_device_id: Any, is_locked: bool
) -> str:
    """Classify the exact recording-id probe row into the fixed ``id_probe`` token set.

    A document read that found no row reports ``missing`` — that only says the
    document is absent at read time (a write race or a row that never existed);
    it says nothing about why the lineage query returned no candidates.
    """
    if not isinstance(row, Mapping):
        return 'missing'
    reason = classify_generation_row(
        row, origin_id=origin_id, source=source, client_device_id=client_device_id, is_locked=is_locked
    )
    if reason is None:
        return 'compatible'
    return reason[len('dropped_') :]
