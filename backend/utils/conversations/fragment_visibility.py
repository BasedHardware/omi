"""Which sync review fragments intake stores as discarded.

Sync keeps short filler speech as a durable, reviewable record so a later
chunk can promote the complete recording; intake stores it ``discarded=True``
and every reader trusts that stored flag.  Rows written before intake did so
are rewritten by ``scripts/conversation_relevance_backfill.py``.

This predicate deliberately uses only server-owned metadata.  It never
decodes transcript text, and it never treats duration by itself as evidence
that a recording is low signal.  The content verdict itself belongs to the
relevance step (``utils/conversations/relevance.py``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from utils.conversations import phase_shadow

BATCH_RECORD_OWNERS = frozenset({'batch_live_v1', 'batch_sync_v1'})
SETTLING_ROW_MAX_SECONDS = 60
# The batch timeliness alarm: a row still unsettled here is an incident to show, not a fragment to hide.
SETTLING_MAX_HOLD_SECONDS = 2 * 60 * 60
SETTLING_FIELDS = (
    'summary_blocked_reason',
    'record_lane_owner',
    'record_projection_revision',
    'record_upload_failed',
    'record_audio_partial',
)


def _value(value: Any) -> Any:
    """Return enum values without importing model modules into read paths."""
    return getattr(value, 'value', value)


def is_user_curated(data: Mapping[str, Any]) -> bool:
    """Whether a user action (or a live owner) protects this row from any relevance discard.

    Only user actions count. A generated summary is not evidence that anyone
    cares: the pipeline writes one for whatever it processes.
    """
    return bool(
        data.get('sync_relevance_user_kept')
        or data.get('has_photos')
        or data.get('photos')
        or data.get('user_title')
        or data.get('starred')
        or data.get('folder_user_set')
    )


def is_relevance_discarded(data: Mapping[str, Any]) -> bool:
    """Final visibility verdict; sync_relevance is only intake's keep/review hint.

    A restore outranks an older assessment. The stored discarded flag also
    covers explicit discards without a relevance receipt.
    """
    decision = data.get('relevance_decision')
    return bool(
        data.get('discarded')
        or (isinstance(decision, Mapping) and decision.get('verdict') == 'discard' and not is_user_curated(data))
    )


_RULE_DISCARD_REASONS = frozenset({'no_content_words', 'filler_only', 'mic_check', 'empty_transcript'})


def is_rule_discard_decision(decision: Any) -> bool:
    """Whether ``relevance_decision`` records a deterministic-rule discard."""
    return (
        isinstance(decision, Mapping)
        and decision.get('verdict') == 'discard'
        and decision.get('decided_by') == 'rule'
        and isinstance(decision.get('reason'), str)
        and decision.get('reason') in _RULE_DISCARD_REASONS
    )


def superseded_intake_discard(data: Mapping[str, Any], content_changed: bool) -> bool:
    """Meaningful appended speech supersedes an automatic verdict on older text.

    Called only by the atomic intake writer after it constructs a new content
    revision. Transport replays and content still needing fragment review retain
    the previous model assessment.
    Deterministic rule receipts keep their existing occasion-deferral behavior.
    """
    decision = data.get('relevance_decision')
    return is_rule_discard_decision(decision) or bool(
        content_changed
        and data.get('sync_relevance') == 'keep'
        and isinstance(decision, Mapping)
        and decision.get('verdict') == 'discard'
        and decision.get('decided_by') in {'model', 'jev', 'deterministic'}
    )


def is_automatic_discard(data: Mapping[str, Any]) -> bool:
    """Whether a stored discard is only the pipeline's verdict, never the user's.

    An explicit discard writes ``sync_relevance_user_kept=False`` (or carries no
    relevance receipt at all); a restore marks the row curated. Either one
    leaves the discard to the user.
    """
    decision = data.get('relevance_decision')
    return bool(
        data.get('discarded')
        and isinstance(decision, Mapping)
        and decision.get('verdict') == 'discard'
        and decision.get('decided_by') in {'rule', 'model', 'jev', 'deterministic'}
        and 'sync_relevance_user_kept' not in data
        and not data.get('jev_discard_restored')
        and not is_user_curated(data)
    )


def is_completed_rule_discard(data: Mapping[str, Any] | None) -> bool:
    """Whether ``data`` is a finished, uncurated row the rules already discarded.

    Rows written while live ownership or sharing counted as curation carry the
    stored ``rule``/``discard`` decision but kept ``discarded=False``. Readers
    treat that decision as the durable verdict: the conversation is hidden
    until a user restores it, and ``prepare_conversation_for_read`` projects
    the effective flag onto the read copy without rewriting storage.
    """
    if not data:
        return False
    if _value(data.get('status')) != 'completed':
        return False
    if is_user_curated(data):
        return False
    return is_rule_discard_decision(data.get('relevance_decision'))


def is_low_signal_sync_fragment(data: Mapping[str, Any] | None) -> bool:
    """Whether ``data`` is an uncurated completed sync review fragment."""
    if not data:
        return False
    if _value(data.get('status')) != 'completed':
        return False
    if data.get('sync_relevance') != 'review':
        return False
    return not is_user_curated(data)


def is_completed_below_floor(data: Mapping[str, Any]) -> bool:
    """A settled content verdict has no expiry; curation still releases it."""
    decision = data.get('relevance_decision')
    return bool(
        _value(data.get('status')) == 'completed'
        and not is_user_curated(data)
        and (
            data.get('summary_blocked_reason') == 'content_below_floor'
            or (isinstance(decision, Mapping) and decision.get('reason') == 'content_below_floor')
        )
    )


@phase_shadow.compare('settling_hold')
def is_settling_fragment(data: Mapping[str, Any], *, now: float | None = None) -> bool:
    """Hold minimum/floor rows across capture lanes, without discarding speech.

    Batch-owned short provisional rows retain their existing hold too. User
    curation releases every hold. Only unsettled rows expire after two hours;
    a completed below-floor verdict stays off Home permanently.
    """
    from config.episodes import home_hide_below_floor_rows_enabled

    if not home_hide_below_floor_rows_enabled():
        return False
    if is_completed_below_floor(data):
        return True
    if is_user_curated(data):
        return False
    if data.get('record_projection_revision') or data.get('record_upload_failed') or data.get('record_audio_partial'):
        return False
    if _value(data.get('status')) != 'completed':
        return False
    started, finished = data.get('started_at'), data.get('finished_at')
    if not isinstance(finished, datetime):
        return False
    current = datetime.now(timezone.utc).timestamp() if now is None else now
    if current - finished.timestamp() >= SETTLING_MAX_HOLD_SECONDS:
        return False
    structured = data.get('structured')
    server_minimum = isinstance(structured, Mapping) and structured.get('title_provenance') == 'server_minimum'
    batch_short = (
        isinstance(started, datetime)
        and data.get('record_lane_owner') in BATCH_RECORD_OWNERS
        and (finished - started).total_seconds() < SETTLING_ROW_MAX_SECONDS
    )
    return server_minimum or batch_short
