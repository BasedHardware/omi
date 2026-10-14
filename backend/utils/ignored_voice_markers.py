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
    affected = {
        int(segment['speaker_id'])
        for segment in raw.get('transcript_segments') or []
        if segment.get('id') in resolved_ids and isinstance(segment.get('speaker_id'), int)
    } or ({speaker_id} if speaker_id is not None else set())
    generation = (raw.get('manual_speaker_assignments') or {}).get('generation')
    for affected_speaker in sorted(affected):
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
    still_rejected = set(manual_rejected_speakers(receipt))
    retired = sorted(reassigned - still_rejected)
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
