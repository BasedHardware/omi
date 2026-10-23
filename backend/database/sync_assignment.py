"""Legacy sync assignment transaction runner, shared write codec and sub-phase clock."""

from contextlib import contextmanager
from typing import Any
import os
import time
from google.cloud import firestore
import config.speaker_match_scores as match_scores


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
        lambda transaction: run_transactional(client, assign, full_ids=full_ids, initial_transaction=transaction),
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
