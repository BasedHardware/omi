"""Fail-closed operator decisions for empty, dead-lettered captures.

No clients, providers or credentials are constructed here. The adapter supplies
the repository transcript codec and whole-document update-time compare-and-set.
Every decision and outcome is a closed label, safe for aggregate-only output.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import base64
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Callable

OPERATION = 'empty-capture-recovery-v1'
MARKER = 'capture_empty_recovery'
ROW_FIELDS = (
    'status',
    'finalization_status',
    'discarded',
    'deleted',
    'sync_merged_into',
    'structured',
    'user_title',
    'transcript_segments',
    'transcript_segments_compressed',
    'data_protection_level',
    'audio_files',
    'started_at',
    'finished_at',
    'created_at',
    'has_transcript_corrections',
    'transcript_correction_overlay',
    'user_corrections',
    'user_corrections_compressed',
    'manual_speaker_assignments',
    'sync_relevance_user_kept',
    'starred',
    'folder_user_set',
    'photos',
    'has_photos',
    'apps_results',
    'events',
    'action_items',
    'notes',
    'is_locked',
    'record_lane_owner',
    'uses_custom_stt',
    'listen_finalization_requires_byok',
    'private_cloud_sync_enabled',
    MARKER,
)
_MINIMUM_TITLE = re.compile(r'Recording(?: · (?:[0-2]?\d:[0-5]\d(?: [AP]M)?))?\Z')
_EDIT_FIELDS = (
    'user_title',
    'has_transcript_corrections',
    'transcript_correction_overlay',
    'manual_speaker_assignments',
    'sync_relevance_user_kept',
    'starred',
    'folder_user_set',
    'photos',
    'has_photos',
    'apps_results',
    'events',
    'action_items',
    'notes',
)


@dataclass
class Observed:
    """Private in-memory row; never serialize this object to an operator report."""

    uid: str
    conversation_id: str
    row: dict[str, Any]
    revision: Any
    trigger: str = 'server_recovery'
    requires_byok: bool | None = False
    recovery_jobs: tuple[str, ...] = ()
    privacy_generation: int | None = None
    rejection: str | None = None


def duration_seconds(row: dict[str, Any]) -> float | None:
    files = row.get('audio_files')
    if not isinstance(files, list) or not files:
        return None
    durations: list[float] = []
    for part in files:
        if not isinstance(part, dict):
            return None
        value: Any = part.get('duration')
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            return None
        durations.append(float(value))
    return math.fsum(durations)


def classify(observed: Observed, decode: Callable) -> str:
    row = observed.row
    if observed.rejection:
        return observed.rejection
    if not row:
        return 'missing_row'
    if (
        observed.requires_byok is not False
        or row.get('listen_finalization_requires_byok')
        or row.get('uses_custom_stt')
    ):
        return 'byok_or_custom_stt'
    if row.get('deleted') or row.get('sync_merged_into'):
        return 'deleted_or_redirected'
    if row.get('discarded'):
        return 'already_hidden'
    if row.get('status') != 'completed' or row.get('finalization_status') != 'dead_letter':
        return 'not_terminal'
    if row.get('is_locked') or row.get('record_lane_owner'):
        return 'other_owner_or_locked'
    if row.get(MARKER):
        return 'already_attempted'
    if any(row.get(field) for field in _EDIT_FIELDS):
        return 'protected_content'
    corrections = row.get('user_corrections')
    if corrections is not None:
        try:
            # Production writes even [] through the protected JSON codec. Its
            # nonempty blob is not an edit. Only a verified empty list passes;
            # nonempty corrections need no text decoding to remain protected.
            if decode(observed.uid, corrections, bool(row.get('user_corrections_compressed'))) != []:
                return 'protected_content'
        except Exception:
            return 'protected_content'
    # Even an empty overlay may carry an edit receipt. Unknown shapes abstain.
    if row.get('transcript_correction_overlay') is not None:
        return 'protected_content'
    structured = row.get('structured')
    if structured is not None and not isinstance(structured, dict):
        return 'structured_unproven'
    structured = structured or {}
    title = structured.get('title')
    if title is not None and not isinstance(title, str):
        return 'structured_unproven'
    if title and not _MINIMUM_TITLE.fullmatch(title):
        return 'protected_title'
    # Defaults emitted by Structured carry no user content. Everything else is
    # preserved, including unknown future fields, notes and summary sections.
    defaults = {
        'title',
        'overview',
        'emoji',
        'category',
        'action_items',
        'events',
        'sections',
        'meeting_type',
        'participants',
        'insights',
        'note_claims',
        'title_provenance',
        'salience',
    }
    if structured.get('title_provenance') not in {None, 'server_minimum'}:
        return 'protected_title'
    if any(value for key, value in structured.items() if key not in {'title', 'emoji', 'category', 'title_provenance'}):
        return 'protected_content'
    if set(structured) - defaults:
        return 'structured_unproven'
    if row.get('data_protection_level') not in {'standard', 'enhanced'}:
        return 'protection_unproven'
    bare = not title
    raw = row.get('transcript_segments')
    if raw is None and not bare:
        return 'transcript_unproven'
    try:
        segments = [] if raw is None else decode(observed.uid, raw, bool(row.get('transcript_segments_compressed')))
    except Exception:
        return 'transcript_unproven'
    if not isinstance(segments, list):
        return 'transcript_unproven'
    if segments:
        return 'nonempty_transcript'
    if observed.trigger not in {'server_recovery', 'capture_end'}:
        return 'other_trigger'
    if bare:
        return 'reprocess_shell'
    if observed.trigger != 'server_recovery':
        return 'other_trigger'
    duration = duration_seconds(row)
    if duration is None:
        return 'duration_unproven'
    return 'reprocess_long' if duration > 60 else 'short_needs_measurement'


def speech_bucket(seconds: float) -> str:
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError('speech_unproven')
    if seconds == 0:
        return 'zero'
    if seconds < 1:
        return 'under_1s'
    if seconds <= 3:
        return '1_to_3s'
    if seconds <= 10:
        return '3_to_10s'
    return 'over_10s'


def row_digest(row: dict[str, Any]) -> str:
    def normalize(value: Any) -> Any:
        if isinstance(value, bytes):
            return {'bytes': base64.b64encode(value).decode('ascii')}
        if isinstance(value, datetime):
            return {'datetime': value.isoformat()}
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items())}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    content = {key: value for key, value in row.items() if key not in {MARKER, 'discarded'}}
    return hashlib.sha256(json.dumps(normalize(content), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Changed(Exception):
    """The whole-document update-time precondition lost; no blind retry."""


class MutationUncertain(Exception):
    """A submitted write has no conclusive receipt; stop without a retry."""


class AuthorityBlocked(Exception):
    """A current privacy or payer fence forbids the operation."""


STOP_OUTCOMES = frozenset(
    {
        'claim_commit_unproven',
        'fill_commit_unproven',
        'hide_commit_unproven',
        'undo_commit_unproven',
        'ledger_prepare_failed',
        'hide_receipt_unproven',
        'visibility_index_unproven',
    }
)


def reprocess_one(observed, *, decode, encode, cas, transcribe, speech_seconds=None) -> str:
    """Claim once before paid STT, then fill only the unchanged empty row.

    ``cas(observed, patch)`` returns its new revision or raises Changed. A crash
    or uncertain provider reply leaves a claim, which subsequent runs report
    as already_attempted. Automatic retries can never duplicate paid work.
    Titles and every other content field are outside both write masks.
    """
    decision = classify(observed, decode)
    if decision not in {'reprocess_long', 'reprocess_shell', 'short_needs_measurement'}:
        return decision
    if decision == 'short_needs_measurement' and (speech_seconds is None or speech_bucket(speech_seconds) == 'zero'):
        return 'short_speech_unproven'
    marker = {'operation': OPERATION, 'state': 'claimed'}
    try:
        revision = cas(observed, {MARKER: marker})
    except Changed:
        return 'row_changed'
    except MutationUncertain:
        return 'claim_commit_unproven'
    except AuthorityBlocked:
        return 'authority_blocked'
    claimed = replace(observed, row={**observed.row, MARKER: marker}, revision=revision)
    try:
        segments = transcribe(claimed)
        # Encoding uses the row's persisted protection level, never today's
        # user preference. No plaintext fallback is permitted for enhanced.
        if not isinstance(segments, list) or not segments:
            patch = {MARKER: {'operation': OPERATION, 'state': 'empty'}}
            result = 'still_empty'
        else:
            patch = {
                'transcript_segments': encode(observed.uid, segments, observed.row['data_protection_level']),
                'transcript_segments_compressed': True,
                MARKER: {'operation': OPERATION, 'state': 'filled'},
            }
            result = 'filled'
    except AuthorityBlocked:
        return 'authority_blocked'
    except Exception:
        # Do not echo exceptions, which can contain identifiers or provider text.
        patch = {MARKER: {'operation': OPERATION, 'state': 'unproven'}}
        result = 'reprocess_unproven'
    try:
        cas(claimed, patch)
    except Changed:
        return 'row_changed_after_claim'
    except MutationUncertain:
        return 'fill_commit_unproven'
    except AuthorityBlocked:
        return 'authority_blocked'
    return result


def _converge(observed, converge):
    try:
        return bool(converge(observed))
    except Exception:
        return False


def hide_one(observed, speech_seconds, *, decode, cas, ledger, converge=None) -> str:
    decision = classify(observed, decode)
    if decision != 'short_needs_measurement':
        return decision
    if speech_bucket(speech_seconds) != 'zero':
        return 'measured_speech_keep'
    marker = {'operation': OPERATION, 'state': 'hidden', 'token': ledger.token()}
    # The fsynced intent survives an uncertain commit for investigation.
    try:
        ledger.prepare(observed, marker)
    except Exception:
        return 'ledger_prepare_failed'
    try:
        revision = cas(observed, {'discarded': True, MARKER: marker})
    except Changed:
        return 'row_changed'
    except MutationUncertain:
        return 'hide_commit_unproven'
    except AuthorityBlocked:
        return 'authority_blocked'
    try:
        ledger.committed(marker['token'], revision)
    except Exception:
        return 'hide_receipt_unproven'
    if not _converge(observed, converge):
        return 'visibility_index_unproven'
    return 'hidden'


def undo_one(observed, entry, *, cas, converge=None) -> str:
    """Restore only this ledger's discard. Never revive a deletion or user edit."""
    row = observed.row
    if row.get('deleted') or row.get('sync_merged_into'):
        return 'deleted_or_redirected'
    if row.get(MARKER) != entry['marker'] or not row.get('discarded'):
        return 'undo_not_owned'
    # The committed revision fences changes outside the field mask as well.
    # An intent without its write receipt is uncertain, not automatic undo.
    if not entry.get('committed_revision'):
        return 'undo_revision_unproven'
    if observed.revision is None or observed.revision.isoformat() != entry['committed_revision']:
        return 'undo_row_changed'
    # Adapter checks the entire pre-hide decision fingerprint too, including
    # absent-vs-false discarded. The marker alone is not permission to restore.
    if row_digest(row) != entry['before_sha256']:
        return 'undo_row_changed'
    patch = {'discarded': entry['prior_discarded'], MARKER: {'operation': OPERATION, 'state': 'undone'}}
    try:
        cas(observed, patch)
    except Changed:
        return 'row_changed'
    except MutationUncertain:
        return 'undo_commit_unproven'
    except AuthorityBlocked:
        return 'authority_blocked'
    if not _converge(observed, converge):
        return 'visibility_index_unproven'
    return 'restored'
