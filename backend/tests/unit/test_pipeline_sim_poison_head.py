"""Poison-head invariant over the real owner-chain walk (sim harness).

David, 10-29 (simtests): tonight's batch wedges were deterministic and
testable, but no test covered the property that failed. A permanently failing
unit at the head of an owner's capture-ordered chain froze the whole owner
(#23932, unhandled record-target conflict); a committed payload that violates
the result contract had the same shape until this suite pinned it.

For every failure kind the projection walk can raise, inject it permanently at
an owner's chain head and assert one of exactly two observable outcomes:

- ``advance``: within K walk attempts the head takes the held disposition
  (quarantine receipt, recovery owns the unit, audio retained), the owner
  watermark moves past it, and later units project.
- ``wait``: a bounded, observable wait state — the head stays ``pending``, no
  receipt or hold is written, the watermark stays frozen — for kinds another
  writer or a lease TTL can still resolve (fresh awaiting-writer conflicts,
  unlabeled conflicts, Firestore commit contention, a busy advisory claim).

The exception-taxonomy contract (``test_batch_projection_exception_taxonomy``)
fails when a new raise site appears that this matrix does not cover.
"""

from contextlib import contextmanager

import pytest

# The assignment seam's monkeypatch string targets resolve database.conversations
# on first use, and build_incoming's function-level imports (pre_recorded pulls
# the deepgram SDK, deterministic_minimum, models.conversation, sync.capture)
# land in whichever test calls them first. Import them at collection so no
# test's duration-guard call phase pays that graph.
from database import conversations  # noqa: F401
import models.conversation  # noqa: F401
import utils.conversations.deterministic_minimum  # noqa: F401
import utils.stt.pre_recorded  # noqa: F401
import utils.sync.capture  # noqa: F401
from database.batch_pipeline_projection_protocol import ProjectionGenerationAmbiguous
from tests.unit.test_batch_pipeline_owner_chain_projection import (
    BURST,
    SUCCESS_PAYLOAD,
    ResultLog,
    advisory_claim,
    patch_conversation_assignment,
    projector_for,
)
from utils.batch_pipeline import projection
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.assignment_errors import (
    SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER,
    SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL,
    SYNC_ASSIGNMENT_CONFLICT_SUBTYPES,
)

# Bounds the "within K attempts" promise: the walk retries the head forever,
# so any disposition must land on the first or second pass, never later.
CHAIN_ATTEMPTS = 2
WAIT_ATTEMPTS = 3

ADVANCE = 'advance'
WAIT = 'wait'

# Every bounded conflict subtype plus the unlabeled fallback. Subtypes outside
# both strike sets (bridge_source_not_tombstone today) wait on every lane.
POISON_CONFLICT_SUBTYPES = frozenset(SYNC_ASSIGNMENT_CONFLICT_SUBTYPES) | {'other'}
# Committed-payload contract violations that must take the held disposition.
POISON_PAYLOAD_KINDS = frozenset(
    {
        'payload:duration-mismatch',
        'payload:split-duration',
        'payload:no-words',
        'payload:vad-spans-missing',
        'payload:source-manifest',
        'payload:corrupt-artifact',
        'payload:non-object-result',
        'payload:tampered-artifact',
    }
)

CONFLICT_KINDS = sorted(f'conflict:{subtype}' for subtype in POISON_CONFLICT_SUBTYPES)
ALL_KINDS = CONFLICT_KINDS + sorted(POISON_PAYLOAD_KINDS) + ['contention-value-error', 'generation-ambiguous']


def expected_outcome(kind: str, lane: str) -> str:
    if kind == 'contention-value-error':
        return WAIT
    if kind.startswith('conflict:'):
        subtype = kind.split(':', 1)[1]
        if subtype in SYNC_ASSIGNMENT_CONFLICT_STRUCTURAL:
            return ADVANCE
        if subtype in SYNC_ASSIGNMENT_CONFLICT_AWAITING_WRITER:
            return ADVANCE if lane == 'backfill' else WAIT
        return WAIT  # the unlabeled fallback and every unclassified subtype
    return ADVANCE


def poison_payload(kind: str, head: str):
    """load_result poisoning only the head row; siblings stay healthy."""

    def load(item, uri):
        if item.segment_id != head:
            return dict(SUCCESS_PAYLOAD)
        if kind == 'payload:duration-mismatch':
            return {**SUCCESS_PAYLOAD, 'audio_seconds': 2.0}
        if kind == 'payload:split-duration':
            return {**SUCCESS_PAYLOAD, 'audio_seconds': 1.5}
        if kind == 'payload:no-words':
            return {**SUCCESS_PAYLOAD, 'words': []}
        if kind == 'payload:vad-spans-missing':
            return {key: value for key, value in SUCCESS_PAYLOAD.items() if key != 'speech_spans'}
        if kind == 'payload:corrupt-artifact':
            # The real ArtifactStore seam: envelope/size/reference violations.
            raise ValueError('invalid batch artifact envelope')
        if kind == 'payload:non-object-result':
            # load_result is json.loads: a valid non-object body.
            return ['not', 'an', 'object']
        if kind == 'payload:tampered-artifact':
            # Authenticated decryption of altered ciphertext: InvalidTag, not
            # ValueError (Luna round 2).
            from cryptography.exceptions import InvalidTag

            raise InvalidTag()
        return dict(SUCCESS_PAYLOAD)

    return load


def owner_chain(*, record=True, fresh_capture=False, outcome='success'):
    log = ResultLog()
    ids = [f'p-{n}' for n in range(3)]
    for sid in ids:
        log.commit(BURST, 'p', sid, ids, record=record, fresh_capture=fresh_capture, outcome=outcome)
    return log, ids


@pytest.mark.parametrize('lane', ['backfill', 'fresh'])
@pytest.mark.parametrize('kind', ALL_KINDS, ids=ALL_KINDS)
def test_permanent_poison_head_advances_or_waits_observably(monkeypatch, kind, lane):
    """The matrix: each injected kind must produce its declared outcome within
    the bounded attempt count — nothing may wedge a third state."""
    outcome = expected_outcome(kind, lane)
    record = kind != 'payload:no-words' and kind != 'payload:split-duration'
    log, ids = owner_chain(record=record, fresh_capture=(lane == 'fresh'))
    head = ids[0]

    if kind.startswith('conflict:'):
        from utils.sync.assignment_errors import SyncAssignmentConflictReason

        subtype = kind.split(':', 1)[1]
        reason = getattr(SyncAssignmentConflictReason, subtype.upper(), None) if subtype != 'other' else None
        patch_conversation_assignment(monkeypatch, reason or subtype, fail_first_n=10**9)
        projector = projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD))
    elif kind in POISON_PAYLOAD_KINDS:
        # Healthy siblings assign through the hermetic seam; only the head's
        # committed payload is poisoned.
        patch_conversation_assignment(monkeypatch, None, fail_first_n=0)
        projector = projector_for(log, poison_payload(kind, head))
        if kind == 'payload:source-manifest':
            import utils.batch_pipeline.audio as audio_module

            for sid in ids:
                log.jobs[sid]['requires_compute_admission'] = True
            projector.fetch_audio = lambda item: b'poison' if item.segment_id == head else b'ok'

            def read_context(raw):
                if raw == b'poison':
                    raise ValueError('retained audio manifest binding mismatch')
                return None

            monkeypatch.setattr(audio_module, 'read_context', read_context)
    elif kind == 'contention-value-error':
        # Luna round 2: the load seam's Firestore-backed authorization can
        # exhaust Aborted retries, surfacing the contention ValueError inside
        # the disposition's scope. It must stay retryable — no quarantine.
        from database.firestore_transaction_retry import FirestoreAborted

        def load(item, uri):
            if item.segment_id == head:
                error = ValueError('Failed to commit transaction in 5 attempts')
                error.__cause__ = FirestoreAborted('synthetic contention')
                raise error
            return dict(SUCCESS_PAYLOAD)

        patch_conversation_assignment(monkeypatch, None, fail_first_n=0)
        projector = projector_for(log, load)
    else:  # generation-ambiguous: the head's first transactional prepare fails
        patch_conversation_assignment(monkeypatch, None, fail_first_n=0)
        real_session = log.session
        poisoned = set()

        def session(sid, binding, now, **kwargs):
            built = real_session(sid, binding, now, **kwargs)
            real_prepare = built.prepare

            def prepare(transaction, **_):
                if sid == head and sid not in poisoned:
                    poisoned.add(sid)
                    raise ProjectionGenerationAmbiguous('synthetic generation skew')
                return real_prepare(transaction)

            built.prepare = prepare
            return built

        log.session = session
        projector = projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD))

    attempts = CHAIN_ATTEMPTS if outcome == ADVANCE else WAIT_ATTEMPTS
    for _ in range(attempts):
        projector.project_owner(BURST)
    key = owner_key(BURST)
    if outcome == ADVANCE:
        assert log.projection_watermark(key) == ids[-1], 'poison head must not freeze the watermark'
        assert log.persist_order == ids, 'later units must project behind the held head'
        assert log.results[head]['projection_state'] == 'quarantine_held'
        assert log.results[head]['projection']['state'] == 'quarantined'
        assert log.jobs[head]['recovery_state'] == 'held'
        assert log.jobs[head]['audio_uri'] == 'gs://synthetic/audio', 'held audio stays in custody'
        assert all(log.results[sid]['projection_state'] != 'pending' for sid in ids[1:])
    else:
        assert log.projection_watermark(key) is None
        assert log.persist_order == []
        assert all(log.results[sid]['projection_state'] == 'pending' for sid in ids)
        assert 'recovery_state' not in log.jobs[head], 'wait kinds must not take the held disposition'


def test_conflicting_conflict_seam_raises_the_named_subtype(monkeypatch):
    """The conflict seam really raises SyncAssignmentConflict, not a lookalike."""
    from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason

    log, ids = owner_chain(fresh_capture=False)
    calls = patch_conversation_assignment(
        monkeypatch, SyncAssignmentConflictReason.RECORD_TARGET_DISCARDED, fail_first_n=10**9
    )
    projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD)).project_owner(BURST)
    assert calls['n'] >= 1


def test_busy_claim_is_a_bounded_observable_wait_then_the_chain_advances(monkeypatch):
    """Claim errors wait (lease-bounded) and never disposition anything; the
    chain advances as soon as the claim is available again."""
    log, ids = owner_chain(fresh_capture=False)
    patch_conversation_assignment(monkeypatch, None, fail_first_n=0)

    @contextmanager
    def busy(*_args, **_kwargs):
        yield False

    monkeypatch.setattr(projection, 'projection_claim', busy)
    projector = projector_for(log, lambda item, uri: dict(SUCCESS_PAYLOAD))
    for _ in range(WAIT_ATTEMPTS):
        projector.project_owner(BURST)
    assert log.persist_order == [] and log.projection_watermark(owner_key(BURST)) is None
    assert all(log.results[sid]['projection_state'] == 'pending' for sid in ids)

    @contextmanager
    def free(*_args, **_kwargs):
        yield True

    monkeypatch.setattr(projection, 'projection_claim', free)
    projector.project_owner(BURST)
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]
    assert log.persist_order == ids


def test_contention_shaped_value_error_stays_retryable_at_the_unit_level():
    """The discriminator: Firestore commit exhaustion is a ValueError that must
    never take the payload-contract disposition."""
    from database.firestore_transaction_retry import FirestoreAborted

    contention = ValueError('Failed to commit transaction in 5 attempts')
    contention.__cause__ = FirestoreAborted('synthetic contention')
    assert not projection.payload_contract_violation(contention)
    assert not projection.payload_contract_violation(RuntimeError('synthetic'))
    from cryptography.exceptions import InvalidTag

    assert projection.payload_contract_violation(InvalidTag())  # tampered artifact body
    for permanent in (
        ValueError('result audio duration differs from admitted capture'),
        ValueError('successful batch result must contain words'),
        ValueError('retained audio manifest binding mismatch'),
    ):
        assert projection.payload_contract_violation(permanent)
