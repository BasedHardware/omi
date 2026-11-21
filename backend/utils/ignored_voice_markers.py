"""Ignored-voice marker reconciliation shared by every manual speaker writer.

Live-sheet exclusions, reject-route answers, and tag-prompt answers all write
the same ignored-voice marker, and a later positive assignment replaces an
exclusion (the live sheet is reversible by design). Two writers used to own
their own copies of that bookkeeping; keeping them in sync is exactly how a
tag-prompt ``Me``/person answer could leave a positively assigned voice
listed under Settings > Ignored Voices. Both paths now call these helpers so
marker accounting rides the same rules everywhere.
"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional

from database import voice_profiles as voice_profiles_db
from utils.manual_speaker_assignments import manual_rejected_speakers
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def record_exclusion_markers(
    uid: str,
    conversation_id: str,
    raw: Mapping[str, Any],
    resolved: List[str],
    *,
    speaker_id: Optional[int],
    logger_: Optional[logging.Logger] = None,
    voice_profiles: Any = None,
) -> None:
    """Record ignored-voice markers for a committed ``not_a_person`` exclusion.

    The assignment transaction has already committed the exclusion (prompt
    suppression and no-teaching ride on the receipt); the marker only powers
    Settings > Ignored Voices and restoration, so a persistence failure is
    fail-open: log, emit fallback telemetry, and keep the committed edit
    authoritative rather than reporting a saved decision as unsaved.
    """
    log = logger_ or logger
    db = voice_profiles or voice_profiles_db
    resolved_ids = set(resolved)
    receipt = raw.get('manual_speaker_assignments') or {}
    generation = receipt.get('generation')
    # Whole-voice markers are consumed at whole-voice scope (prompt selection,
    # historical voice matching, Settings > Ignored Voices). Only a winning
    # whole-voice rejection at this write's generation licenses one: a range
    # exclusion commits ``segment_only`` entries that deliberately do not
    # unseat a whole-voice decision, so recording a marker for it would
    # suppress segments outside the requested range and list the voice as
    # globally ignored without a matching whole-voice rejection to restore.
    rejected = manual_rejected_speakers(receipt)
    affected = {
        int(segment['speaker_id'])
        for segment in raw.get('transcript_segments') or []
        if segment.get('id') in resolved_ids and isinstance(segment.get('speaker_id'), int)
    } or ({speaker_id} if speaker_id is not None else set())
    for affected_speaker in sorted(affected):
        decision = rejected.get(affected_speaker)
        if decision is None or decision.get('generation') != generation:
            continue
        try:
            db.record_ignored_voice(
                uid,
                conversation_id,
                affected_speaker,
                datetime.now(timezone.utc),
                assignment_generation=generation,
            )
        except Exception:
            log.exception(
                'ignored-voice marker record failed after commit uid=%s conv=%s speaker=%s',
                uid,
                conversation_id,
                affected_speaker,
            )
            record_fallback(
                component='speaker_assignments',
                from_mode='ignored_voice_marker',
                to_mode='receipt_only',
                reason='firestore_error',
                outcome='degraded',
                log=log,
            )


def retire_exclusion_markers(
    uid: str,
    conversation_id: str,
    raw: Mapping[str, Any],
    resolved: List[str],
    *,
    speaker_id: Optional[int],
    logger_: Optional[logging.Logger] = None,
    voice_profiles: Any = None,
) -> None:
    """Retire ignored-voice markers a committed positive assignment supersedes.

    Range-only entries (``segment_only``) do not unseat a whole-voice
    rejection, so those assignments keep the marker restorable. Marker
    retirement is post-commit bookkeeping: a failure must not report the saved
    decision as unsaved, so log, emit fallback telemetry, and continue. A
    stale marker is self-healing — the record path fences stale generations
    and Settings > Ignored Voices restore remains available.
    """
    log = logger_ or logger
    db = voice_profiles or voice_profiles_db
    receipt = raw.get('manual_speaker_assignments') or {}
    if not receipt:
        # No persisted manual decisions for this conversation means no
        # generation-fenced marker from it — nothing a positive assignment
        # could retire.
        return
    resolved_ids = set(resolved)
    reassigned = {
        int(segment['speaker_id'])
        for segment in raw.get('transcript_segments') or []
        if segment.get('id') in resolved_ids and isinstance(segment.get('speaker_id'), int)
    } or ({speaker_id} if speaker_id is not None else set())
    # Ignored-voice markers exist only for not_a_person exclusions, so only a
    # still-winning not_a_person rejection keeps one: a newer not_me /
    # not_person / unnamed decision supersedes the exclusion and must retire
    # its marker even though that newer decision is itself a rejection.
    still_excluded = {
        excluded
        for excluded, decision in manual_rejected_speakers(receipt).items()
        if (decision.get('rejection') or {}).get('kind') == 'not_a_person'
    }
    retired = sorted(reassigned - still_excluded)
    if not retired:
        return
    generation = receipt.get('generation')
    try:
        db.clear_ignored_voices(uid, conversation_id, retired, assignment_generation=generation)
    except Exception:
        log.exception(
            'ignored-voice marker retirement failed after commit uid=%s conv=%s speakers=%s',
            uid,
            conversation_id,
            retired,
        )
        record_fallback(
            component='speaker_assignments',
            from_mode='ignored_voice_marker',
            to_mode='receipt_only',
            reason='firestore_error',
            outcome='degraded',
            log=log,
        )
