"""Legacy sync assignment transaction runner, shared write codec and sub-phase clock."""

from contextlib import contextmanager
from typing import Any
import os
import time
from google.cloud import firestore
import config.speaker_match_scores as match_scores
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, OPEN_LOOP_EXTRACTIONS_FIELD


class SyncAssignmentDiscovery:
    """One bounded discovery per call, reused across read-only stamp-gap replanning."""

    def __init__(self, lineage_eligible: bool):
        self.lineage_eligible = lineage_eligible
        self.candidate_ids: tuple[str, ...] = ()
        self.lookup: dict = {'lookup_complete': False, 'incomplete_reason': 'discovery_skipped'}
        self.attempted = False

    def plan_kwargs(self) -> dict:
        if not self.lineage_eligible:
            return {}
        return {
            'live_lookup_complete': self.lookup.get('lookup_complete', False),
            'live_lookup_incomplete_reason': self.lookup.get('incomplete_reason'),
            'discover_on_stamp_gap': not self.attempted,
        }

    def discover(self, user_ref, incoming, find_candidates):
        self.attempted = True
        # A lookup that omits diagnostics differs from one that never ran.
        self.lookup.clear()
        self.candidate_ids = find_candidates(
            user_ref, incoming, **({'diagnostics': self.lookup} if self.lineage_eligible else {})
        )

    def run(self, assign, attempted_canonical, discover):
        from utils.sync.assignment import SyncAssignmentDiscoveryRequired, run_with_size_limit_backstop

        try:
            return run_with_size_limit_backstop(assign, attempted_canonical)
        except SyncAssignmentDiscoveryRequired:
            discover()
            return run_with_size_limit_backstop(assign, attempted_canonical)


def encode_sync_assignment_plan(uid: str, client: Any, transaction: Any, payload: dict, current: dict | None) -> dict:
    from database import conversations

    if current and current.get('has_transcript_corrections'):
        from utils.agent_capabilities.transcripts import load_entries, preserves_correction_anchors
        from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason

        captured = conversations.decode_transcript_segments_verified(
            uid, current.get('transcript_segments') or [], bool(current.get('transcript_segments_compressed'))
        )
        corrections = load_entries(uid, payload['id'], firestore_client=client, transaction=transaction)
        if not preserves_correction_anchors(captured, payload.get('transcript_segments') or [], corrections):
            raise SyncAssignmentConflict(
                'sync append changed corrected speech', subtype=SyncAssignmentConflictReason.CORRECTED_SPEECH_CHANGED
            )
    encoded = conversations._prepare_conversation_for_write(  # type: ignore[reportPrivateUsage]
        payload,
        uid,
        payload.get('data_protection_level') or 'enhanced',
        preserve_transcript_identity=bool(current and current.get('has_transcript_corrections')),
    )
    if current is not None and OPEN_LOOP_EXTRACTIONS_FIELD in current:
        # The decoded plan never carries retained extractions (the encoded blob
        # must not reach the logical encoder), and the stored row is their only
        # authoritative source on an existing row. An unchanged protection level
        # carries the stored blob and its marker verbatim — no decrypt/decompress
        # on the transaction replay path. A level change strictly decodes and
        # re-protects; an unreadable blob then aborts before any write, never
        # becomes empty content.
        level = payload.get('data_protection_level') or 'enhanced'
        if (current.get('data_protection_level') or 'standard') == level:
            encoded[OPEN_LOOP_EXTRACTIONS_FIELD] = current[OPEN_LOOP_EXTRACTIONS_FIELD]
            encoded[OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD] = current.get(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD)
        else:
            retained = conversations.decode_open_loop_extractions(
                uid,
                current[OPEN_LOOP_EXTRACTIONS_FIELD],
                bool(current.get(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD)),
            )
            encoded.update(
                conversations._prepare_conversation_for_write(  # type: ignore[reportPrivateUsage]
                    {OPEN_LOOP_EXTRACTIONS_FIELD: retained},
                    uid,
                    level,
                )
            )
    conversations.guard_match_score_size(encoded, current)
    if (
        current
        and match_scores.FIELD in current
        and match_scores.FIELD not in encoded
        and current.get('data_protection_level') != payload.get('data_protection_level')
    ):
        encoded[match_scores.FIELD] = firestore.DELETE_FIELD
    return encoded


def run_sync_assignment(client: Any, assign: Any, full_ids: frozenset[str], *, retry_contention: bool = False):
    from database._client import run_transactional
    from database.firestore_transaction_retry import run_with_transaction_contention_retry

    if (
        not retry_contention
        and os.getenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'false').strip().lower() != 'true'
    ):
        return run_transactional(client, assign, full_ids=full_ids)
    return run_with_transaction_contention_retry(
        client.transaction,
        # attempts=1: the outer budget owns every attempt, so an expired chain
        # costs one bounded outer retry instead of up to three inner restarts
        # (which multiplied the worst case to 15 chains).
        lambda transaction: run_transactional(
            client, assign, full_ids=full_ids, initial_transaction=transaction, attempts=1
        ),
        operation_name='sync_assignment',
    )


class SyncAssignmentClock:
    """Accumulates assign_sync_conversation sub-phases for one bounded log line.

    Disabled clocks are no-ops, so the transaction body needs no branches.
    ``plan`` excludes the nested ``encode`` time. ``commit`` is the final
    commit after the last transaction body; ``retry`` is the remaining
    transaction time (failed commits, rollbacks, backoff and size retries).
    """

    PHASES = ('live_overlap', 'fence', 'plan', 'encode', 'persist', 'transaction', 'index')

    def __init__(self, logger, *, enabled: bool):
        self.logger, self.enabled = logger, enabled
        self.started = time.monotonic()
        self.ms: dict[str, float] = dict.fromkeys(self.PHASES, 0.0)
        self.attempts = 0
        self.body_ms = 0.0
        self.attempt_started = None
        self.last_body_end = None
        self.transaction_end = None
        self.donors = 0

    def attempt(self):
        self.attempts += 1
        self.attempt_started = time.monotonic()

    def body_done(self):
        now = time.monotonic()
        if self.attempt_started is not None:
            self.body_ms += (now - self.attempt_started) * 1000
        self.last_body_end = now

    @contextmanager
    def timed(self, phase: str):
        if not self.enabled:
            yield
            return
        started = time.monotonic()
        try:
            yield
        finally:
            elapsed_ms = (time.monotonic() - started) * 1000
            self.ms[phase] += elapsed_ms
            if phase == 'encode':
                self.ms['plan'] -= elapsed_ms
            if phase == 'transaction':
                self.transaction_end = time.monotonic()

    @contextmanager
    def call(self):
        """Wraps the whole call; logs one line on success or failure when enabled."""
        try:
            yield self
        except Exception as error:
            if self.enabled:
                self.log('error', type(error).__name__)
            raise
        if self.enabled:
            self.log('completed', None)

    def log(self, outcome: str, exception_type: str | None):
        commit_ms = 0.0
        if self.last_body_end is not None and self.transaction_end is not None:
            commit_ms = max(0.0, (self.transaction_end - self.last_body_end) * 1000)
        retry_ms = max(0.0, self.ms['transaction'] - self.body_ms - commit_ms)
        self.logger.info(
            'event=sync_assignment_timing outcome=%s attempts=%d live_overlap_ms=%d fence_ms=%d plan_ms=%d '
            'encode_ms=%d persist_ms=%d body_ms=%d commit_ms=%d retry_ms=%d index_ms=%d donors=%d total_ms=%d%s',
            outcome,
            self.attempts,
            int(self.ms['live_overlap']),
            int(self.ms['fence']),
            int(max(0.0, self.ms['plan'])),
            int(self.ms['encode']),
            int(self.ms['persist']),
            int(self.body_ms),
            int(commit_ms),
            int(retry_ms),
            int(self.ms['index']),
            self.donors,
            int((time.monotonic() - self.started) * 1000),
            f' exception_type={exception_type}' if exception_type else '',
        )
