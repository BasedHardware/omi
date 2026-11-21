"""Read-only compatibility projection of legacy lifecycle facts; no clocks, IO or writes."""

from collections.abc import Mapping
from enum import Enum
from typing import Any


class ConversationPhase(str, Enum):
    CAPTURING = 'capturing'
    SEALED = 'sealed'
    PROCESSING = 'processing'
    TRANSCRIBED = 'transcribed'
    COMPLETE = 'complete'
    SETTLED = 'settled'
    DISCARDED = 'discarded'
    QUARANTINED = 'quarantined'
    DEAD_LETTER = 'dead_letter'
    FAILED = 'failed'
    MERGED = 'merged'


class EpisodePhase(str, Enum):
    LIVE = 'live'
    CLOSING = 'closing'
    CLOSED = 'closed'
    COMPOSED = 'composed'
    REDIRECTED = 'redirected'


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ''


def derive_episode_phase(doc: Mapping[str, Any] | None) -> EpisodePhase:
    """Precedence: redirect > live (closing if wrap-up requested) > closed/composed.

    Explicit ``status=live`` outranks stale closed/composed timestamps after a reopen.
    A closed episode with a fingerprint is composed unless regeneration is requested.
    Missing/unknown status defaults to live; closed_at alone supports legacy closed rows.
    Composition freshness (notes hash, version, member changes, backoff) remains the
    composer's job: this projection makes no reads and cannot verify those facts.
    """
    row = _mapping(doc)
    if row.get('recorded_merged_into'):
        return EpisodePhase.REDIRECTED
    status = _text(row.get('status'))
    if status == 'live' or (status != 'closed' and not row.get('closed_at')):
        return (
            EpisodePhase.CLOSING
            if row.get('wrap_up_requested_at') or row.get('closing_conversation_id')
            else EpisodePhase.LIVE
        )
    if row.get('composed_fingerprint') and not row.get('summary_needs_regeneration'):
        return EpisodePhase.COMPOSED
    return EpisodePhase.CLOSED


def derive_conversation_phase(
    doc: Mapping[str, Any] | None, episode: Mapping[str, Any] | None = None
) -> ConversationPhase:
    """Derive only from stored facts, in this precedence order (first match wins).

    1. Deleted/redirected donors -> merged (there is no separate deleted phase).
    2. Stored/effective relevance discard -> discarded; explicit curation protects
       an old relevance receipt, but never overrides the stored discarded flag.
    3. Dead-letter > failed status/upload failure. Quarantined is reserved: its
       only stored evidence lives on batch receipts, absent from conversation docs.
    4. Batch custody without a durable projection: processing if status says so;
       otherwise sealed if audio is closed with no producers/partial tail, capturing
       otherwise. Provisional live transcript/summary and queued finalization do
       not prove batch delivery. Lane ownership alone never proves admission.
    5. Delivered/waived summary (including local-only completion) -> complete,
       or settled for standalone rows / an already supplied composed episode.
    6. Durable transcript/projection -> transcribed; processing/job ownership ->
       processing; closed audio -> sealed; missing/unknown fields -> capturing.

    Completed alone is insufficient evidence of summary delivery. Below-floor
    server minima intentionally waive summary debt and remain complete/settled.
    No phase field is consulted: this stays an independent shadow of legacy facts.
    No fetching an episode, decoding encrypted text, threshold/flag reads or clocks.
    """
    row = _mapping(doc)
    if row.get('deleted') or row.get('is_deleted') or row.get('sync_merged_into'):
        return ConversationPhase.MERGED
    decision = _mapping(row.get('relevance_decision'))
    curated = any(
        row.get(key)
        for key in ('sync_relevance_user_kept', 'has_photos', 'photos', 'user_title', 'starred', 'folder_user_set')
    )
    if row.get('discarded') or (decision.get('verdict') == 'discard' and not curated):
        return ConversationPhase.DISCARDED
    status = _text(row.get('status'))
    finalization = _text(row.get('finalization_status'))
    if finalization == 'dead_letter':
        return ConversationPhase.DEAD_LETTER
    if status == 'failed' or row.get('record_upload_failed'):
        return ConversationPhase.FAILED
    projected = bool(row.get('record_projection_revision'))
    sealed = bool(
        row.get('record_audio_closed') and not row.get('record_upload_sessions') and not row.get('record_audio_partial')
    )
    if _text(row.get('record_lane_owner')) in ('batch_live_v1', 'batch_sync_v1') and not projected:
        if status == 'processing':
            return ConversationPhase.PROCESSING
        return ConversationPhase.SEALED if sealed else ConversationPhase.CAPTURING
    structured = _mapping(row.get('structured'))
    sections = structured.get('sections')
    summary = bool(
        row.get('summary_completed_at')
        or row.get('summary_output_present')
        or (isinstance(structured.get('overview'), str) and structured['overview'].strip())
        or (
            isinstance(sections, list)
            and any(
                isinstance(_mapping(section).get('body_markdown'), str) and _mapping(section)['body_markdown'].strip()
                for section in sections
            )
        )
    )
    waived = row.get('summary_blocked_reason') == 'content_below_floor' or (
        structured.get('title_provenance') == 'server_minimum'
        and decision.get('verdict') == 'keep'
        and decision.get('decided_by') == 'rule'
        and decision.get('reason') == 'content_below_floor'
    )
    local = (
        row.get('summary_blocked_reason') == 'local_only'
        or row.get('processing_state') == 'local_pending'
        or row.get('deferred')
        or row.get('client_processing')
    )
    if summary or waived or (status == 'completed' and local):
        if (not row.get('episode_id') and episode is None) or (
            episode is not None and derive_episode_phase(episode) == EpisodePhase.COMPOSED
        ):
            return ConversationPhase.SETTLED
        return ConversationPhase.COMPLETE
    segments = row.get('transcript_segments')
    transcript = isinstance(segments, list) and any(
        isinstance(_mapping(segment).get('text'), str) and _mapping(segment)['text'].strip() for segment in segments
    )
    if projected or transcript:
        return ConversationPhase.TRANSCRIBED
    if (
        status in ('processing', 'merging')
        or finalization in ('queued', 'leased', 'blocked_byok')
        or row.get('finalization_job_id')
    ):
        return ConversationPhase.PROCESSING
    return ConversationPhase.SEALED if sealed else ConversationPhase.CAPTURING
