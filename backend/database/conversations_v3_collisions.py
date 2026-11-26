"""Which document, and which writer, made a v3 grouping pass lose its commit.

A grouping pass ends with one transaction over every recording row and conversation it loaded
(``conversations_v3.commit_projection``). The pass is lost in two ways:

``raced``         a document it loaded was changed before the commit, so the pass is thrown away;
``lock_failed``   another writer held a lock the commit needed until the commit gave up.

A third outcome costs time but not the pass: ``lock_retried``, a commit the SDK had to run again after a
lock abort.

Until now neither loss said which document it was or who changed it. This module records that, for every
loss, as one log line and one counter step:

    event=v3_pass_collision outcome=raced lane=builder doc=conversation writer=summary
        fields=structured,tile_state phase=documents attempt=1 changed_ago=0.4 waited=- cause=- trace_id=...

``doc`` is the kind of document (a recording row, the open conversation, another conversation, the pass's
own lease). ``fields`` are the names of the top-level fields that differ, never their values, and ``writer``
is the family of code that writes those fields (the table below). ``changed_ago`` is how long before the
commit the other write landed: a fraction of a second is two writers at the same moment, many seconds is a
pass that ran long after it loaded. ``waited`` is how long the lost try ran, lock wait included.

A lock outcome can only name a document that was visibly changed while the commit waited. When none was,
the line says ``doc=unknown writer=no_visible_write``: the lock was held by a write that changed no value
(``mark_pending`` on a row that is already marked; a third of its writes in production on 2026-11-25), by
a transaction that only read these documents, or on a document the commit does not track. ``mark_pending``
therefore reports its own side as well (``marked`` below).

How the changed fields are known without keeping a second copy of every document: when the pass loads a
document, ``fingerprint`` keeps one small token per top-level field (``FIELDS_KEY`` on the loaded row). A
lost commit compares those tokens with the document as it is now.

Nothing here changes what a pass does. No report can fail or delay a commit that succeeds; a failed commit
pays one extra read of the documents it had loaded (``CommitWatch.failed``) to see what moved.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from prometheus_client import Counter

from database._client import firestore_failure_reason
from database.home_feed_fields import COMMIT_STAMPED_FIELDS
from utils.conversations.v3 import request_log_trace_id

logger = logging.getLogger(__name__)

# The key a loaded row carries its field tokens under. Like every ``_v3_`` key it is never written.
FIELDS_KEY = '_v3_loaded_fields'

RACED, LOCK_RETRIED, LOCK_FAILED = 'raced', 'lock_retried', 'lock_failed'
OUTCOMES = (RACED, LOCK_RETRIED, LOCK_FAILED)

RECORDING_ROW, OPEN_CONVERSATION, CONVERSATION, LEASE, MISSING, UNKNOWN = (
    'recording_row',
    'open_conversation',
    'conversation',
    'lease',
    'missing',
    'unknown',
)
# The pass's own lease is watched beside the documents; a document id cannot contain a slash.
LEASE_KEY = '/lease'

# Failures of the commit that mean "another writer was in the way" (``firestore_failure_reason`` tokens).
LOCK_CAUSES = frozenset({'contention', 'expired_transaction', 'deadline_exceeded'})

# A writer that just won the lock commits a moment after this commit gives up; the look at what moved
# waits this long so it sees that write. Paid only by a commit that already failed.
SETTLE_SECONDS = 0.25
# Documents named per lost commit. A pass that lost to twenty writes says so in ``more=``.
MAX_REPORTED = 6
MAX_FIELDS = 12
READ_CHUNK = 100
# A document changed before the commit began was not holding a lock against it. One second of slack for
# the difference between this machine's clock and the database's.
WINDOW_SLACK_SECONDS = 1.0

COLLISIONS = Counter(
    'omi_conversations_v3_pass_collision_total',
    'Documents that made a v3 grouping pass lose or repeat its commit, by outcome, kind of document and '
    'the family of code that changed it',
    ['outcome', 'doc', 'writer', 'lane'],
)

# The other side of the same lock. After every append of speech, ``mark_pending`` marks the recording row as
# owing a pass with its own small transaction. ``outcome`` is what that write changed: ``armed`` (the row
# was not marked), ``already_pending`` (it was: the write takes the row's lock and changes nothing, so a
# pass that loses to it sees no change), ``skipped`` (not a live recording row), ``failed``. ``lock`` is
# whether the mark itself met a lock: ``clean``, ``retried`` (the SDK ran it again) or ``failed``.
MARKS = Counter(
    'omi_conversations_v3_mark_pending_total',
    'Marks of a recording row as owing a v3 grouping pass, by what the write changed and whether it met a lock',
    ['outcome', 'lock'],
)
MARK_OUTCOMES = ('armed', 'already_pending', 'skipped', 'failed')

# Written by every conversation write (the Home feed hook), so they say nothing about who wrote.
IGNORED_FIELDS = frozenset({*COMMIT_STAMPED_FIELDS, 'id', 'updated_at'})

# Which family of code writes a field, from a survey of every writer of users/{uid}/conversations
# (2026-11-25). The first family with a changed field names the writer, so the order runs from the most
# telling field to the least: attaching an uploaded unit also sets ``v3_pending``, and it is the attach step
# we want named, so the families that write few fields come last. Kept per kind of document, because the
# same field is written by different code on a recording row and on a conversation. Each family is exact
# names plus name prefixes. A field in no family reports ``other``; its name is still in the log line, which
# is how this table gets corrected.
Family = tuple[str, frozenset[str], tuple[str, ...]]
WRITERS: dict[str, tuple[Family, ...]] = {
    RECORDING_ROW: (
        ('delete', frozenset({'deleted', 'deleted_spans', 'v3_audio_erased'}), ()),
        ('merge', frozenset({'sync_merged_into', 'sync_merged_from', 'smart_merge'}), ()),
        # Fields only the attach step for uploaded units writes (utils/sync/assignment.py, live_projection.py).
        (
            'upload_attach',
            frozenset(
                {
                    'sync_recorded_end_at',
                    'sync_live_target',
                    'sync_processing_hold',
                    'sync_relevance',
                    'sync_bridge_pending',
                    'capture_time_trust',
                    'episode_transcript_updated_at',
                    'record_projection_revision',
                    'record_transcription_empty',
                }
            ),
            (),
        ),
        # Fields only the live listen append writes (database/conversations.py update_conversation_segments).
        (
            'live_append',
            frozenset({'last_speech_at', 'last_activity_at', 'audio_timeline', 'live_transcript_replay_receipt'}),
            (),
        ),
        # Speech landed, by either of the two above: the changed fields do not say which.
        (
            'speech',
            frozenset(
                {
                    'transcript_segments',
                    'transcript_segments_compressed',
                    'has_content',
                    'started_at',
                    'finished_at',
                    'v3_speech_landed_at',
                    'sync_content_revision',
                    'capture_evidence',
                    'speaker_match_scores',
                }
            ),
            (),
        ),
        ('end', frozenset({'v3_manual_end', 'v3_manual_end_requested', 'v3_finish_no_pointer_window_id'}), ()),
        (
            'ownership',
            frozenset({'claims', 'recording', 'v3_derived', 'v3_claims_transferred_to'}),
            ('v3_audio_purge_', 'v3_backfill_'),
        ),
        ('lock_or_privacy', frozenset({'is_locked', 'data_protection_level'}), ()),
        ('record_lane', frozenset({'seal_claim'}), ('record_', 'server_batch_audio_')),
        ('status', frozenset({'status', 'processing_admitted_at', 'deferred'}), ('finalization_',)),
        ('audio', frozenset({'audio_files'}), ()),
        # Nothing but the "owes a pass" marker: mark_pending after an append, or a commit of another pass.
        ('owes_a_pass', frozenset({'v3_pending', 'v3_pending_since'}), ()),
    ),
    CONVERSATION: (
        (
            'delete',
            frozenset({'deleted', 'discarded', 'home_hidden', 'sync_merged_into', 'v3_claims_transferred_to'}),
            (),
        ),
        ('lock_or_privacy', frozenset({'is_locked', 'data_protection_level'}), ()),
        (
            'user_edit',
            frozenset(
                {
                    'user_title',
                    'starred',
                    'visibility',
                    'owner_uid',
                    'folder_user_set',
                    'manual_speaker_assignments',
                    'manual_speaker_assignments_compressed',
                    'has_transcript_corrections',
                    'transcript_correction_overlay',
                    'calendar_event',
                    'has_photos',
                }
            ),
            (),
        ),
        # The title and summary shown while a conversation is still open.
        ('live_title', frozenset({'v3_live_title_state'}), ()),
        ('live_summary', frozenset({'v3_live_summary'}), ()),
        ('summary', frozenset({'structured', 'title_locked', 'content_word_units'}), ('summary_',)),
        (
            'processing',
            frozenset(
                {
                    'tile_state',
                    'status',
                    'v3_notes_written',
                    'v3_unlocked',
                    'v3_open_locked',
                    'apps_results',
                    'suggested_summarization_apps',
                    'folder_id',
                    'processing_admitted_at',
                }
            ),
            ('v3_process_', 'v3_created_', 'v3_backfill_', 'finalization_'),
        ),
        ('audio', frozenset({'conversation_audio', 'conversation_audio_artifact_fingerprint', 'audio_files'}), ()),
        ('ownership', frozenset({'v3_recording_ids', 'v3_derived', 'v3_refined'}), ()),
        (
            'content',
            frozenset({'transcript_segments', 'transcript_segments_compressed', 'sync_content_revision'}),
            (),
        ),
    ),
}
WRITERS[OPEN_CONVERSATION] = WRITERS[CONVERSATION]
WRITER_NAMES = frozenset(
    {name for table in WRITERS.values() for name, _, _ in table}
    | {'other', 'unknown', 'no_value_change', 'no_visible_write', 'retained_custody', 'task_links', 'plan', 'lease'}
)

_SAFE_FIELD = re.compile(r'^[A-Za-z0-9_]{1,48}$')
_MISSING = ('missing',)


def _plain(value: Any) -> Any:
    # Firestore values json cannot write: times, bytes, references, geo points. The address in a default
    # repr must never reach the token, or two reads of one stored value would differ.
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return ['bytes', len(value), hash(bytes(value))]
    path = getattr(value, 'path', None)
    if isinstance(path, str):
        return ['ref', path]
    return [type(value).__name__, sorted((k, str(v)) for k, v in getattr(value, '__dict__', {}).items())]


def _token(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, datetime)):
        return value
    if isinstance(value, (str, bytes)):
        return (len(value), hash(value))
    try:
        text = json.dumps(value, sort_keys=True, default=_plain)
    except (TypeError, ValueError):
        return ('unreadable', type(value).__name__)
    return (type(value).__name__, len(text), hash(text))


def fingerprint(raw: dict[str, Any] | None) -> dict[str, Any]:
    """One small comparable token per top-level field of a stored document. Never the content itself.

    Tokens compare within one process only (``hash`` is salted per process), which is all a pass needs.
    """
    try:
        return {key: _token(value) for key, value in (raw or {}).items() if key not in IGNORED_FIELDS}
    except Exception:
        return {}


def changed_fields(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[str] | None:
    """Names of the top-level fields that differ between two fingerprints; None when one is not known."""
    if before is None or after is None:
        return None
    return sorted(
        key
        for key in before.keys() | after.keys()
        if key not in IGNORED_FIELDS
        and not key.startswith('_')
        and before.get(key, _MISSING) != after.get(key, _MISSING)
    )


def doc_kind(raw: dict[str, Any] | None) -> str:
    if raw is None:
        return MISSING
    if raw.get('recording'):
        return RECORDING_ROW
    return OPEN_CONVERSATION if raw.get('status') == 'in_progress' else CONVERSATION


def writer_of(doc: str, fields: Iterable[str] | None) -> str:
    """The family of code that writes these fields on this kind of document."""
    if doc == LEASE:
        return 'lease'
    if doc == MISSING:
        return 'delete'
    if fields is None:
        return 'unknown'
    names = set(fields)
    if not names:
        # The document's revision moved and no field differs: a write of the values it already had (the
        # local emulator moves the revision for such a write) or of nothing but the stamp of every write.
        return 'no_value_change'
    for name, owned, prefixes in WRITERS.get(doc, ()):
        if names & owned or (prefixes and any(field.startswith(prefixes) for field in names)):
            return name
    return 'other'


def _seconds_ago(update_time: Any) -> float | None:
    if not isinstance(update_time, datetime):
        return None
    moment = update_time if update_time.tzinfo else update_time.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - moment).total_seconds())


def report(
    outcome: str,
    doc: str,
    fields: Iterable[str] | None,
    *,
    writer: str | None = None,
    lane: str = 'builder',
    phase: str = '-',
    attempt: int = 1,
    update_time: Any = None,
    cause: str = '-',
    more: int = 0,
    waited: float | None = None,
) -> None:
    """Count one collision and write its line. Never raises: a meter must not fail a commit."""
    try:
        names = None if fields is None else [name for name in fields if _SAFE_FIELD.match(name)]
        who = writer if writer in WRITER_NAMES else writer_of(doc, names)
        lane = 'builder' if lane == 'builder' else 'other'
        COLLISIONS.labels(outcome, doc, who, lane).inc()
        ago = _seconds_ago(update_time)
        shown = '?' if names is None else (','.join(names[:MAX_FIELDS]) or '-')
        # A raced pass is an expected, handled race: info. A commit that failed on a lock is a fault.
        logger.log(
            logging.WARNING if outcome == LOCK_FAILED else logging.INFO,
            'event=v3_pass_collision outcome=%s lane=%s doc=%s writer=%s fields=%s phase=%s attempt=%d '
            'changed_ago=%s waited=%s cause=%s more=%d trace_id=%s',
            outcome,
            lane,
            doc,
            who,
            shown,
            phase,
            attempt,
            '-' if ago is None else f'{ago:.1f}',
            '-' if waited is None else f'{waited:.1f}',
            cause,
            more,
            request_log_trace_id(),
        )
    except Exception:
        pass


class CommitWatch:
    """What one commit saw on each try, so a later try or a failure can say what moved in between.

    The transaction body calls ``begin`` at its top, ``phase`` as it moves on, ``saw`` for every document
    it reads and ``reads_done`` after the last read. All of that is bookkeeping on values the body already
    holds: no read, no copy. ``raced`` reports the document that throws a pass away; ``failed`` reports
    what moved while a commit was failing on a lock.
    """

    def __init__(self, lane: str, loaded: dict[str, dict[str, Any]], *, lead: Iterable[str] = ()):
        self.lane = lane
        self.loaded = loaded
        # Fields named first in a line (the ones that decide a recording row's fate), so the cap on the
        # number of names never hides them.
        self.lead = frozenset(lead)
        self.reset()

    def _ordered(self, fields: list[str] | None) -> list[str] | None:
        return None if fields is None else sorted(fields, key=lambda name: (name not in self.lead, name))

    def reset(self) -> None:
        """A new commit batch: its own tries, its own window."""
        self.attempt = 0
        self.at = '-'
        self.started = time.time()
        self.try_started = time.monotonic()
        self.previous_try_seconds: float | None = None
        # id -> (update_time, stored document) as the latest try that read it saw it.
        self.seen: dict[str, tuple[Any, dict[str, Any] | None]] = {}
        self.current: dict[str, tuple[Any, dict[str, Any] | None]] = {}

    def begin(self) -> None:
        self.attempt += 1
        now = time.monotonic()
        # How long the try before this one ran, lock wait included, before it was aborted.
        self.previous_try_seconds = now - self.try_started if self.attempt > 1 else None
        self.try_started = now
        self.at = 'lease'
        self.current = {}

    def phase(self, name: str) -> None:
        self.at = name

    def saw(self, key: str, snapshot: Any, stored: dict[str, Any] | None) -> None:
        self.current[key] = (getattr(snapshot, 'update_time', None), stored)

    def reads_done(self) -> None:
        """After a re-run's reads: every document that moved since the previous try beat it to a lock."""
        try:
            previous, self.seen = self.seen, {**self.seen, **self.current}
            if self.attempt < 2:
                return
            moved = [key for key, (stamp, _) in self.current.items() if key in previous and previous[key][0] != stamp]
            # The SDK re-runs a commit only after an abort of the commit call itself, so the try that
            # lost is the one before this one and the step it lost at is the commit.
            self._report(
                LOCK_RETRIED,
                moved,
                previous,
                self.current,
                cause='contention',
                phase='commit',
                attempt=self.attempt - 1,
                waited=self.previous_try_seconds,
            )
        except Exception:
            pass

    def raced(self, key: str, row: dict[str, Any], snapshot: Any, stored: dict[str, Any] | None) -> None:
        """The loaded document ``key`` is not what the pass planned from, so the pass is thrown away."""
        try:
            before = row.get(FIELDS_KEY)
            fields = changed_fields(before, fingerprint(stored)) if stored is not None else None
            report(
                RACED,
                doc_kind(stored) if stored is not None else MISSING,
                self._ordered(fields),
                lane=self.lane,
                phase=self.at,
                attempt=self.attempt,
                update_time=getattr(snapshot, 'update_time', None),
            )
        except Exception:
            pass

    def failed(self, error: BaseException, client: Any, coll: Any, lease_ref: Any) -> None:
        """A commit failed on a lock: read the documents once more, outside any transaction, and name
        every one that moved while the commit was running. One read per loaded document, paid by a
        commit that already failed.
        """
        try:
            cause = firestore_failure_reason(error)
            if cause not in LOCK_CAUSES:
                return
            if SETTLE_SECONDS:
                time.sleep(SETTLE_SECONDS)
            baseline = {
                **{key: (row.get('_v3_revision'), None) for key, row in self.loaded.items()},
                **self.seen,
                **self.current,
            }
            now: dict[str, tuple[Any, dict[str, Any] | None]] = {}
            keys = [key for key in baseline if key != LEASE_KEY]
            for start in range(0, len(keys), READ_CHUNK):
                chunk = keys[start : start + READ_CHUNK]
                for snapshot in client.get_all([coll.document(key) for key in chunk]):
                    stored = (snapshot.to_dict() or {}) if snapshot.exists else None
                    now[snapshot.reference.id] = (getattr(snapshot, 'update_time', None), stored)
            if LEASE_KEY in baseline:
                snapshot = lease_ref.get()
                now[LEASE_KEY] = (
                    getattr(snapshot, 'update_time', None),
                    snapshot.to_dict() if snapshot.exists else None,
                )
            moved = [
                key for key, (stamp, _) in now.items() if baseline[key][0] != stamp and self._in_window(now[key][0])
            ]
            self._report(
                LOCK_FAILED,
                moved,
                baseline,
                now,
                cause=cause,
                phase=self.at,
                attempt=self.attempt,
                waited=time.monotonic() - self.try_started - SETTLE_SECONDS,
            )
        except Exception:
            pass

    def _in_window(self, update_time: Any) -> bool:
        if not isinstance(update_time, datetime):
            return True
        moment = update_time if update_time.tzinfo else update_time.replace(tzinfo=timezone.utc)
        return moment.timestamp() >= self.started - WINDOW_SLACK_SECONDS

    def _report(
        self,
        outcome: str,
        moved: list[str],
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        cause: str,
        phase: str,
        attempt: int,
        waited: float | None,
    ) -> None:
        if not moved:
            # Nothing the commit read was changed while it waited. The lock was held by a write that
            # changed no value (marking a row that is already marked), by a transaction that only read
            # these documents, or on a document the commit does not track by id (a tombstone).
            report(
                outcome,
                UNKNOWN,
                None,
                writer='no_visible_write',
                lane=self.lane,
                phase=phase,
                attempt=attempt,
                cause=cause,
                waited=waited,
            )
            return
        for index, key in enumerate(moved[:MAX_REPORTED]):
            stamp, stored = after[key]
            prior = before[key][1]
            # The previous try's copy when there is one, else the tokens kept when the pass loaded it.
            tokens = fingerprint(prior) if prior is not None else (self.loaded.get(key) or {}).get(FIELDS_KEY)
            if key == LEASE_KEY:
                doc, fields = LEASE, changed_fields(tokens, fingerprint(stored))
            else:
                doc = doc_kind(stored) if stored is not None else MISSING
                fields = changed_fields(tokens, fingerprint(stored)) if stored is not None else None
            report(
                outcome,
                doc,
                self._ordered(fields),
                lane=self.lane,
                phase=phase,
                attempt=attempt,
                update_time=stamp,
                cause=cause,
                more=max(0, len(moved) - MAX_REPORTED) if index == 0 else 0,
                waited=waited,
            )


def marked(outcome: str, tries: int, seconds: float, error: BaseException | None = None) -> None:
    """Count one ``mark_pending`` and, when it met a lock, write its line. Never raises."""
    try:
        outcome = outcome if outcome in MARK_OUTCOMES else 'failed'
        cause = firestore_failure_reason(error) if error is not None else '-'
        lock = 'failed' if cause in LOCK_CAUSES else ('retried' if tries > 1 else 'clean')
        MARKS.labels(outcome, lock).inc()
        if lock != 'clean':
            logger.log(
                logging.WARNING if lock == 'failed' else logging.INFO,
                'event=v3_mark_pending_collision outcome=%s lock=%s attempts=%d seconds=%.2f cause=%s',
                outcome,
                lock,
                tries,
                seconds,
                cause,
            )
    except Exception:
        pass
