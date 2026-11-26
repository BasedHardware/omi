"""Bounded, presentation-only wait for a completed server-batch capture's transcript.

The completion CAS stamps the server wait once. The first seal admission may
advance its presentation anchor once; readers never renew it or write status. Shared database
hydration must remain authoritative for replace_record and finalization replay;
apply project only at API exits.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Literal

from google.api_core.exceptions import GoogleAPICallError

from config.episodes import (
    home_step_projection_enabled,
    home_transcription_deadline_seconds,
    home_transcription_max_age_seconds,
    home_transcription_presentation_gate_enabled,
    home_transcription_queue_hold_enabled,
)
from config.transcription_pending import pending_retry_enabled, seal_wait_enabled
from database.batch_pipeline_admission_view import read_jobs as read_admission_jobs
from database.batch_pipeline_allowance_hold import EXHAUSTED, STATE
from utils.conversations import empty_capture
from utils.conversations.fragment_visibility import BATCH_RECORD_OWNERS
from utils.conversations.home_titles import notes_pending, placeholder_title_wire, untitled_pending
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted
from utils.sync.stage import InvalidSyncStage, current_stage

if TYPE_CHECKING:
    from database.batch_pipeline_store import FirestoreStore

TranscriptionAdmission = Literal['allowance_held', 'processing']
_CONVERSATIONS_PER_QUERY = 30
_MAX_ADMISSION_JOB_READS = 256
_ADMISSION_READ_SECONDS = 1.5

READ_FIELDS = (
    'created_at',
    'home_transcription_pending_at',
    'home_transcription_deadline_at',
    'record_lane_owner',
    'status',
    'record_projection_revision',
    'record_upload_failed',
    'finalization_status',
    'user_title',
    'record_admitted_at',
    'home_transcription_queue_observed_at',
    'has_content',
    'episode_transcription_pending_at',
    'episode_transcription_deadline_at',
    'sync_content_revision',
    'is_locked',
    'server_batch_audio_received',
    'server_batch_audio_closed',
)


def transcription_presentation(deadline: datetime, *, failed: bool = False, now: datetime | None = None):
    """The Episodes Home transcription labels, shared with conversation reads."""
    overdue = (now or datetime.now(timezone.utc)) >= deadline
    return ("Couldn't transcribe", 'failed') if failed or overdue else ('Transcribing…', 'processing')


def applies(row: Mapping[str, Any], *, stored: bool = False) -> bool:
    """Only stamped completed batch captures without a transcript or title qualify."""
    return bool(
        _unprojected_batch_capture(row, stored=stored)
        and _has_wait_clock(row)
        and not str(row.get('user_title') or '').strip()
        # A placeholder stamped on a capture stub is not a title; a placeholder
        # beside real notes is a finished row and keeps them visible.
        and untitled_pending(row.get('structured') or {})
    )


def _unprojected_batch_capture(row: Mapping[str, Any], *, stored: bool = False) -> bool:
    """Indexed list reads omit transcript data. The batch projection receipt
    prevents an omitted-but-landed transcript from becoming a placeholder.
    has_content is intentionally ignored: closed raw audio sets it before STT.
    Raw storage may encode even an empty transcript as bytes or encrypted text.
    That blob is unknown to visibility, not proof of speech; the batch receipt
    remains authoritative there. API projection runs after transcript hydration.
    """
    segments = row.get('transcript_segments')
    has_transcript = bool(segments) and (not stored or isinstance(segments, (list, tuple)))
    return bool(
        home_transcription_presentation_gate_enabled()
        and getattr(row.get('status'), 'value', row.get('status')) == 'completed'
        and row.get('record_lane_owner') in BATCH_RECORD_OWNERS
        and not row.get('record_projection_revision')
        and not has_transcript
    )


def _has_wait_clock(row: Mapping[str, Any]) -> bool:
    return isinstance(row.get('home_transcription_deadline_at'), datetime) or (
        seal_wait_enabled()
        and home_transcription_queue_hold_enabled()
        and isinstance(row.get('episode_transcription_deadline_at'), datetime)
    )


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def wait_started_at(row: Mapping[str, Any], *, prefix: str = 'home_transcription') -> datetime | None:
    """Server wait start, including old rows that retained only its deadline.

    Capture end can predate offline upload by days. Creation is only a fallback
    when neither pending stamp exists; updated_at and read time never renew it.
    """
    for key in (f'{prefix}_pending_at', f'{prefix}_deadline_at', 'created_at'):
        value = row.get(key)
        if not isinstance(value, (datetime, str)):
            continue
        try:
            anchor = _utc(value)
        except ValueError:
            continue
        return (
            anchor - timedelta(seconds=home_transcription_deadline_seconds())
            if key.endswith('_deadline_at')
            else anchor
        )
    return None


def deadline(row: Mapping[str, Any], *, prefix: str = 'home_transcription') -> datetime:
    """Read-time bound heals old stamps without a write, renewal, or job lookup."""
    if (
        prefix == 'home_transcription'
        and not row.get('home_transcription_pending_at')
        and not row.get('home_transcription_deadline_at')
        and seal_wait_enabled()
        and isinstance(row.get('episode_transcription_deadline_at'), datetime)
    ):
        prefix = 'episode_transcription'
    if not home_transcription_queue_hold_enabled():
        return _utc(row[f'{prefix}_deadline_at'])
    anchor = wait_started_at(row, prefix=prefix)
    if anchor is None:
        raise ValueError('transcription wait has no server timestamp')
    # Both native seal and full-proof repair CAS this first-admission clock only
    # when absent. Reconnects, retries, requeues and repeated reads cannot move
    # it. Do not use record_sealed_at: that clock changes on every reseal.
    if seal_wait_enabled():
        for key in ('record_admitted_at', 'home_transcription_queue_observed_at'):
            admitted = row.get(key)
            if (
                isinstance(admitted, (int, float))
                and not isinstance(admitted, bool)
                and math.isfinite(admitted)
                and admitted > 0
            ):
                try:
                    anchor = max(anchor, datetime.fromtimestamp(admitted, timezone.utc))
                except (OverflowError, OSError, ValueError):
                    pass
    return anchor + timedelta(seconds=home_transcription_max_age_seconds())


def failed(row: Mapping[str, Any]) -> bool:
    """Explicit row failure receipts win over the queue wait, irrespective of age."""
    return bool(
        getattr(row.get('status'), 'value', row.get('status')) == 'failed'
        or row.get('record_upload_failed')
        or row.get('finalization_status') == 'dead_letter'
    )


def _pending_admission(row: Mapping[str, Any]) -> bool:
    if (
        row.get('deleted')
        or row.get('discarded')
        or row.get('is_locked')
        or failed(row)
        or not _unprojected_batch_capture(row)
        or row.get('summary_output_present')
        or row.get('summary_completed_at')
    ):
        return False
    if not (
        _has_wait_clock(row)
        or row.get('record_audio_closed') is True
        or row.get('server_batch_audio_closed') is True
        or row.get('record_admitted_at')
        or row.get('home_transcription_queue_observed_at')
    ):
        return False
    structured = row.get('structured') or {}
    if str(row.get('user_title') or '').strip() and isinstance(structured, Mapping):
        # The hydrated title can be owner-written even though the transcript is absent.
        structured = {**structured, 'title': ''}
    return notes_pending(structured)


def _recent(clock: object, now: float, max_age: float) -> bool:
    return isinstance(clock, (int, float)) and not isinstance(clock, bool) and 0 <= now - clock < max_age


def _admission(jobs: list[dict[str, Any]], now: float, max_age: float) -> TranscriptionAdmission | None:
    if any(
        job.get('state') in {'dead', 'quarantined', 'privacy_blocked'}
        or (job.get('state') == 'committed' and job.get('recovery_state') in {'held', 'failed_held', 'cancelled'})
        for job in jobs
    ):
        return None
    active = False
    for job in jobs:
        state = job.get('state')
        decision = job.get('compute_decision')
        if isinstance(decision, Mapping) and decision.get('outcome') == 'held' and decision.get('reason') == EXHAUSTED:
            if state in {STATE, 'retry'}:
                return 'allowance_held'
            # Legacy queue recovery can requeue a retry without a release receipt.
            continue
        lease = job.get('lease_until')
        if (
            (state == 'ready' and _recent(job.get('available_at'), now, max_age))
            or (
                state == 'leased'
                and isinstance(lease, (int, float))
                and not isinstance(lease, bool)
                and 0 < lease - now <= max_age
            )
            or (state in {'result_ready', 'committed'} and _recent(job.get('ready_at'), now, max_age))
        ):
            active = True
    return 'processing' if active else None


def _open_admission_store(stage: str) -> FirestoreStore:
    # Generic presentation also serves MCP reads that never need batch-job dependencies.
    from database.batch_pipeline_store import FirestoreStore

    return FirestoreStore(f'batch_pipeline_{stage}')


def read_admissions(
    uid: str,
    rows: list[dict[str, Any]],
    *,
    budget: ListReadBudget | None = None,
    store: FirestoreStore | None = None,
    now: datetime | None = None,
) -> dict[str, TranscriptionAdmission]:
    """Match owned pre-transcript rows to current jobs without mutating either."""
    ids = list(
        dict.fromkeys(cid for row in rows if isinstance(cid := row.get('id'), str) and cid and _pending_admission(row))
    )
    if not ids:
        return {}
    if store is None:
        try:
            stage = current_stage()
        except InvalidSyncStage:
            return {}
        if stage not in {'prod', 'dev'}:
            return {}
        store = _open_admission_store(stage)
    observed_at = (now or datetime.now(timezone.utc)).timestamp()
    max_age = home_transcription_max_age_seconds()
    deadline = time.monotonic() + _ADMISSION_READ_SECONDS
    remaining = _MAX_ADMISSION_JOB_READS
    states: dict[str, TranscriptionAdmission] = {}
    for start in range(0, len(ids), _CONVERSATIONS_PER_QUERY):
        batch = ids[start : start + _CONVERSATIONS_PER_QUERY]
        limit = min(remaining, budget.remaining_documents) if budget is not None else remaining
        timeout = deadline - time.monotonic()
        if limit <= 0 or timeout <= 0:
            break
        try:
            if budget is not None:
                timeout = min(budget.rpc_timeout(), timeout)
            jobs = read_admission_jobs(store, uid, batch, limit=limit, timeout=timeout)
            reads = max(1, len(jobs))  # Firestore bills a minimum read for an empty query.
            remaining -= reads
            if budget is not None:
                budget.charge(reads)
        except (GoogleAPICallError, ListReadBudgetExhausted):
            record_fallback(
                component='other',
                from_mode='record_transcription_admission',
                to_mode='transcription_wait',
                reason='other',
                outcome='degraded',
            )
            break
        if len(jobs) == limit:
            # A truncated chunk cannot establish that all matching siblings were considered.
            break
        by_id: dict[str, list[dict[str, Any]]] = {cid: [] for cid in batch}
        for job in jobs:
            cid = job.get('conversation_id')
            if job.get('owner_id') == uid and isinstance(cid, str) and cid in by_id:
                by_id[cid].append(job)
        for cid, siblings in by_id.items():
            state = _admission(siblings, observed_at, max_age)
            if state is not None:
                states[cid] = state
    return states


def project(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    home_list: bool = False,
    admission: TranscriptionAdmission | None = None,
) -> dict[str, Any]:
    """Return a wire copy; expired/error captures stay visible as completed rows."""
    empty = empty_capture.project(row, now=now)
    if empty is not row:
        return empty
    admission = admission if admission is not None and _pending_admission(row) else None
    if admission == 'processing':
        return {
            **row,
            'status': 'processing',
            'structured': {**(row.get('structured') or {}), 'title': row.get('user_title') or 'Transcribing…'},
            'summary_retryable': False,
            'transcription_admission': admission,
            **({'home_step': 'transcribing'} if home_list and home_step_projection_enabled() else {}),
        }
    if not applies(row):
        # home_list is set only after the route computed the current wire step.
        wire = placeholder_title_wire(
            row, label_recording=home_list and home_step_projection_enabled() and row.get('home_step') == 'ready'
        )
        if admission == 'allowance_held':
            return {**wire, 'summary_retryable': False, 'transcription_admission': admission}
        return wire
    deadline_at = deadline(row)
    receipt_failed = failed(row)
    title, status = transcription_presentation(
        deadline_at,
        failed=receipt_failed,
        now=now,
    )
    return {
        **row,
        'status': 'completed' if status == 'failed' else status,
        'structured': {**(row.get('structured') or {}), 'title': title},
        **({'summary_retryable': False} if home_transcription_queue_hold_enabled() and not receipt_failed else {}),
        # The wait ran out with no failure receipt: the audio is kept and still waiting for
        # transcription (for example held by the free allowance). Clients that know the owner's
        # allowance is spent say so instead of offering a retry; older clients ignore the field.
        **({'transcription_wait': 'overdue'} if status == 'failed' and not receipt_failed else {}),
        **({'transcription_admission': admission} if admission is not None else {}),
    }


def retry_pending(row: Mapping[str, Any]) -> bool:
    """Stored capture evidence, independent of titles and display switches.

    A title (including a user title) is not transcript evidence. In particular,
    Couldn't transcribe is synthesized on reads, never required in storage.
    This handler receives the hydrated full row, not a slim list projection.
    """
    return bool(
        pending_retry_enabled()
        and row.get('record_lane_owner') in BATCH_RECORD_OWNERS
        and row.get('status') in {'completed', 'in_progress', 'processing', 'failed'}
        and any(
            isinstance(row.get(key), datetime)
            for key in ('home_transcription_deadline_at', 'episode_transcription_deadline_at')
        )
        and not row.get('record_projection_revision')
        and not row.get('transcript_segments')
    )


def retry_wire(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    """No model or job mutation. None asks the API to return a clear non-200.

    There is no owner-click priority promotion in this pipeline. Do not turn
    old audio into fresh audio or overwrite a worker's claim/backoff. A recent
    first seal is enough to return the released client's processing contract.
    """
    empty = empty_capture.project(row, now=now)
    if empty is not row:
        return empty
    prefix = (
        'home_transcription'
        if isinstance(row.get('home_transcription_deadline_at'), datetime)
        else 'episode_transcription'
    )
    title, status = transcription_presentation(deadline(row, prefix=prefix), failed=failed(row), now=now)
    if status == 'failed' or row.get('discarded'):
        return None
    return {
        **row,
        'status': 'processing',
        'home_step': 'transcribing',
        'summary_retryable': False,
        'structured': {**(row.get('structured') or {}), 'title': row.get('user_title') or title},
    }
