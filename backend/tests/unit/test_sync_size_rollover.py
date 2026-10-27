"""A sync conversation that cannot grow past Firestore's 1 MiB ceiling hands new speech on.

The temporal merge only ever grows the canonical conversation, so a long day of
adjacent offline chunks could reach the document-size limit and then fail every
later commit after paid transcription. Assignment now estimates the canonical's
encoded size, rolls new speech over to another conversation when it would cross
``SYNC_CONVERSATION_BYTE_BUDGET``, and retries once around a conversation a commit
proved full. Every retry, deletion, provenance and receipt fence still holds.
"""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

from google.api_core.exceptions import InvalidArgument, ServiceUnavailable
from google.cloud.firestore_v1 import DELETE_FIELD, _helpers
from google.cloud.firestore_v1.types import document as document_pb
from google.cloud.firestore_v1.vector import Vector
import pytest

from database._client import FIRESTORE_DOCUMENT_KINDS, firestore_document_kind, firestore_error_document_path
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from tests.unit.test_sync_cross_job_assignment import _smart_merge_pair, chunk, conversations, intake
from utils.conversations.size_limit import projected_document_bytes, projected_size_bucket
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from utils.sync import assignment
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentSuperseded
from utils.sync.pipeline import _firestore_doc_kind

_LONG = 'An unusually long stretch of narration that fills the conversation. ' * 60


def _row(store, cid):
    return store.rows[('users', 'u', 'conversations', cid)]


def _texts(row):
    return [segment['text'] for segment in row['transcript_segments']]


def _events(caplog, needle='event=sync_assignment_target'):
    return [r.getMessage() for r in caplog.records if needle in r.getMessage()]


def _full_store(monkeypatch, *, cid='a', start=1000, **fields):
    """A store whose conversation ``cid`` sits right at the (test-sized) budget."""
    store = StrictFirestore()
    intake(store, dict(chunk(cid, start, text=_LONG), **fields))
    size = estimate_firestore_document_bytes(_row(store, cid), None)
    # Any appended line or absorbed row crosses the budget; a lone short chunk
    # (a few hundred bytes) and the pair of them stay far below it.
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', size + 64)
    return store


# --------------------------------------------------------------- size estimate


_PATH = 'users/u/conversations/c'


def _encoded_conversation(db, level: str, count: int) -> dict:
    """``count`` poorly compressible lines, encoded by the production sync adapter."""
    started = datetime(2026, 10, 3, tzinfo=timezone.utc)
    digest = b'seed'
    segments = []
    for i in range(count):
        digest = hashlib.sha256(digest).digest()
        segments.append({'id': f's{i}', 'start': i * 10.0, 'end': i * 10.0 + 9.5, 'text': digest.hex() * 4})
    return db._prepare_conversation_for_write(
        {
            'id': 'c',
            'started_at': started,
            'finished_at': started,
            'transcript_segments': segments,
            'sync_merged_from': [f'donor-{i:04d}' for i in range(200)],
            'data_protection_level': level,
            'sync_content_revision': 200,
            'structured': {'title': '', 'overview': ''},
        },
        'u',
        level,
    )


def _near_limit_payload(db, level: str, target_bytes: int) -> dict:
    """A production-encoded conversation whose estimate is exactly ``target_bytes``."""
    probe = estimate_firestore_document_bytes(_encoded_conversation(db, level, 500), _PATH)
    per_line = (probe - estimate_firestore_document_bytes(_encoded_conversation(db, level, 0), _PATH)) / 500
    payload = _encoded_conversation(db, level, int(target_bytes * 0.95 / per_line))
    filler = target_bytes - estimate_firestore_document_bytes(payload, _PATH) - len('filler') - 2
    assert filler > 0
    payload['filler'] = 'x' * filler
    return payload


def _wire_bytes(payload: dict, path: str) -> int:
    """Independent reference: the protobuf Document the SDK actually commits."""
    name = f'projects/p/databases/(default)/documents/{path}'
    return document_pb.Document.pb(document_pb.Document(name=name, fields=_helpers.encode_dict(payload))).ByteSize()


@pytest.mark.parametrize('level', ['enhanced', 'standard'])
def test_estimate_tracks_the_committed_document_near_the_limit(adapter, level):
    target = FIRESTORE_MAX_DOCUMENT_BYTES - 4096
    payload = _near_limit_payload(adapter, level, target)
    estimated = estimate_firestore_document_bytes(payload, _PATH)
    wire = _wire_bytes(payload, _PATH)
    assert estimated == target
    # The documented storage-size rules and the wire encoding agree within 1%,
    # far inside the 124 KiB of headroom the budget keeps below the ceiling.
    assert abs(estimated - wire) < wire * 0.01
    assert FIRESTORE_MAX_DOCUMENT_BYTES - assignment.SYNC_CONVERSATION_BYTE_BUDGET == 124 * 1024
    assert estimated > assignment.SYNC_CONVERSATION_BYTE_BUDGET
    # Growth is counted byte for byte: one more line is one line's size larger.
    payload['filler'] += 'x' * 100
    assert estimate_firestore_document_bytes(payload, _PATH) == target + 100


# --------------------------------------------------------- in-transaction plan


def test_below_the_budget_adjacent_chunks_still_merge(caplog):
    store = StrictFirestore()
    intake(store, chunk('a', 1000, text=_LONG))
    result, created, survivors = intake(store, chunk('b', 1060))
    assert result['id'] == 'a' and not created and len(survivors) == 1
    assert len(conversations(store)) == 1
    assert not _events(caplog)


def _sized_row(store, key, timestamp, stored_bytes):
    """Intake ``key`` and pad its stored summary until the row estimates to ``stored_bytes``.

    The bulk sits in ``structured`` (a long stored summary) rather than the
    transcript, so the dedupe text index stays small and the test stays fast.
    """
    intake(store, chunk(key, timestamp))
    row = _row(store, key)
    row['structured'] = {'title': '', 'overview': ''}
    base = estimate_firestore_document_bytes(row, None)
    row['structured']['overview'] = 'x' * (stored_bytes - base)
    assert estimate_firestore_document_bytes(row, None) == stored_bytes


def _receipt_bridge_store(stored_bytes):
    """A labeled ~stored_bytes row 'a' and a small separate row 'c' a bridge will join."""
    store = StrictFirestore()
    _sized_row(store, 'a', 1000, stored_bytes)
    intake(store, chunk('c', 1240, text='A separate later remark.'))
    _row(store, 'a')['manual_speaker_assignments'] = {
        'segments': {'a': {'generation': 1, 'person_id': 'p', 'is_user': False}}
    }
    return store


def test_default_budget_write_that_fits_is_exactly_the_unbounded_assignment(monkeypatch, caplog):
    """750 KiB stored plus a small bridge stays under the absorption cap, so nothing changes.

    The unbounded run (budget lifted far past any document) is the pre-PR
    assignment: same canonical, receipt owner, donor redirect, index and rows.
    """
    stored = 750 * 1024
    unbounded = _receipt_bridge_store(stored)
    with monkeypatch.context() as patch:
        patch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 10**12)
        expected = intake(unbounded, chunk('b', 1120, text='One short bridging sentence.'))
    bounded = _receipt_bridge_store(stored)
    caplog.clear()
    result = intake(bounded, chunk('b', 1120, text='One short bridging sentence.'))
    assert assignment.SYNC_CONVERSATION_BYTE_BUDGET == 900 * 1024
    assert result == expected
    assert bounded.rows == unbounded.rows
    assert result[0]['id'] == 'a' and not result[1]
    assert _row(bounded, 'c')['sync_merged_into'] == 'a'
    assert estimate_firestore_document_bytes(_row(bounded, 'a'), None) < assignment.SYNC_CONVERSATION_BYTE_BUDGET
    assert not _events(caplog)


def test_default_budget_write_just_over_the_budget_rolls_over(caplog):
    store = StrictFirestore()
    _sized_row(store, 'a', 1000, assignment.SYNC_CONVERSATION_BYTE_BUDGET - 50)
    before = deepcopy(_row(store, 'a'))
    assert estimate_firestore_document_bytes(before, None) <= assignment.SYNC_CONVERSATION_BYTE_BUDGET
    caplog.clear()
    result, created, survivors = intake(store, chunk('b', 1060, text='One sentence too many.'))
    assert result['id'] == 'b' and created and len(survivors) == 1
    assert _row(store, 'a') == before
    assert [line.split(" job_ref=")[0] for line in _events(caplog)] == [
        'event=sync_assignment_target reason=size_rollover outcome=rolled_over trigger=estimate created=true excluded=1 projected_size_bucket=lt_500k'
    ]


def test_full_canonical_is_left_untouched_and_new_speech_starts_a_conversation(monkeypatch, caplog):
    store = _full_store(monkeypatch)
    before = deepcopy(_row(store, 'a'))
    result, created, survivors = intake(store, chunk('b', 1060, text='A new sentence after the long part.'))
    assert result['id'] == 'b' and created and len(survivors) == 1
    assert _row(store, 'a') == before
    assert _texts(_row(store, 'b')) == ['A new sentence after the long part.']
    assert not _row(store, 'b').get('sync_merged_from')
    assert len(conversations(store)) == 2
    events = _events(caplog)
    assert [line.split(" job_ref=")[0] for line in events] == [
        'event=sync_assignment_target reason=size_rollover outcome=rolled_over trigger=estimate created=true excluded=1 projected_size_bucket=lt_500k'
    ]
    fallback = _events(caplog, 'omi_fallback_event')
    assert fallback and 'from=canonical_append to=size_rollover' in fallback[0]


def test_identical_retry_and_later_chunks_land_in_the_rollover(monkeypatch, caplog):
    store = _full_store(monkeypatch)
    before = deepcopy(_row(store, 'a'))
    intake(store, chunk('b', 1060, text='A new sentence after the long part.'))
    retried, created, survivors = intake(store, chunk('b', 1060, text='A new sentence after the long part.'))
    assert retried['id'] == 'b' and not created and not survivors
    later, created, survivors = intake(store, chunk('c', 1120, text='And one more after that.'))
    assert later['id'] == 'b' and not created and len(survivors) == 1
    assert _texts(_row(store, 'b')) == ['A new sentence after the long part.', 'And one more after that.']
    assert _row(store, 'a') == before
    assert len(conversations(store)) == 2


def _full_chain(monkeypatch, length=6):
    # Longer than the four-step bound the first version had, so every accepted
    # rollover must be re-checked to reach a safe home.
    store = _full_store(monkeypatch)
    ids = ['a']
    for i, start in enumerate(range(1060, 1000 + 60 * length, 60)):
        cid = f'full-{i}'
        result, created, _ = intake(store, chunk(cid, start, text=_LONG + str(i)))
        assert result['id'] == cid and created
        ids.append(cid)
    return store, ids


@pytest.mark.parametrize('overlapping', [False, True])
def test_a_long_chain_of_full_conversations_is_walked_to_a_safe_home(monkeypatch, caplog, overlapping):
    store, ids = _full_chain(monkeypatch)
    frozen = {cid: deepcopy(_row(store, cid)) for cid in ids}
    caplog.clear()
    if overlapping:
        # Spans every full row, so each must be merged (it could hold this speech)
        # and then excluded in turn; every accepted rollover is re-checked.
        tail = chunk('tail', 1000, text='The last short sentence.')
        tail['transcript_segments'][0].update(start=30.0, end=39.5)
        tail['finished_at'] = chunk('end', 1000 + 60 * len(ids))['finished_at']
    else:
        # Only borders the newest full rows; the continuity chain still reaches
        # every one, and each is merged into the plan and then excluded.
        tail = chunk('tail', 1000 + 60 * len(ids), text='The last short sentence.')
    result, created, survivors = intake(store, tail)
    assert result['id'] == 'tail' and created and len(survivors) == 1
    assert {cid: _row(store, cid) for cid in ids} == frozen
    assert len(conversations(store)) == len(ids) + 1
    assert [line.split(" job_ref=")[0] for line in _events(caplog)] == [
        f'event=sync_assignment_target reason=size_rollover outcome=rolled_over trigger=estimate created=true excluded={len(ids)} projected_size_bucket=lt_500k'
    ]
    assert len(_events(caplog, 'omi_fallback_event')) == 1


def test_speech_already_in_the_full_conversation_is_not_duplicated(monkeypatch):
    store = _full_store(monkeypatch)
    overlap = chunk('b', 1000, text=_LONG)
    overlap['transcript_segments'].append({'start': 60.0, 'end': 69.5, 'text': 'Fresh words.', 'speaker_id': 0})
    overlap['finished_at'] = chunk('x', 1060)['finished_at']
    result, created, survivors = intake(store, overlap)
    assert result['id'] == 'b' and created
    assert [s['text'] for s in survivors] == ['Fresh words.']
    assert _texts(_row(store, 'b')) == ['Fresh words.']


def test_dedupe_only_retry_of_a_full_conversation_writes_in_place(monkeypatch, caplog):
    store = _full_store(monkeypatch)
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 1)
    result, created, survivors = intake(store, chunk('a-retry', 1000, text=_LONG))
    assert result['id'] == 'a' and not created and not survivors
    assert len(conversations(store)) == 1
    assert not _events(caplog)


def test_deleted_rollover_stays_deleted(monkeypatch):
    store = _full_store(monkeypatch)
    intake(store, chunk('b', 1060, text='A new sentence after the long part.'))
    _row(store, 'b')['deleted'] = True
    deleted = deepcopy(_row(store, 'b'))
    with pytest.raises(SyncAssignmentSuperseded):
        intake(store, chunk('b', 1060, text='A new sentence after the long part.'))
    result, created, _ = intake(store, chunk('c', 1120, text='And one more after that.'))
    assert result['id'] == 'c' and created
    assert _row(store, 'b') == deleted


def test_redirected_anchor_with_no_safe_home_uses_fresh_incoming_only_row(monkeypatch, caplog):
    store = _full_store(monkeypatch)
    store.rows[('users', 'u', 'conversations', 'x')] = dict(
        chunk('x', 1060), deleted=True, discarded=True, sync_merged_into='a', sync_content_revision=1
    )
    before = deepcopy(_row(store, 'a'))
    result, created, _ = intake(store, chunk('x', 1060, text='Words for a redirected anchor.'))
    assert result['id'] not in {'a', 'x'} and created
    assert _texts(result) == ['Words for a redirected anchor.']
    assert _row(store, 'a') == before
    assert 'outcome=rolled_over' in caplog.text
    assert 'size_rollover_unavailable' not in caplog.text
    assert _row(store, 'x')['sync_merged_into'] == 'a'


@pytest.mark.parametrize('locked', [False, True])
def test_rollover_respects_capture_partitions(monkeypatch, locked):
    store = _full_store(monkeypatch, is_locked=locked)
    intake(store, dict(chunk('other-device', 1060, device='phone'), is_locked=locked))
    intake(store, dict(chunk('other-lock', 1070), is_locked=not locked))
    partitions = {cid: deepcopy(_row(store, cid)) for cid in ('a', 'other-device', 'other-lock')}
    result, created, _ = intake(store, dict(chunk('b', 1060, text='Locked or not, new words.'), is_locked=locked))
    assert result['id'] == 'b' and created and result['is_locked'] is locked
    assert {cid: _row(store, cid) for cid in partitions} == partitions


def test_full_explicit_live_target_is_left_untouched(monkeypatch, caplog):
    store = StrictFirestore()
    live = chunk('live', 1000, text=_LONG)
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', estimate_firestore_document_bytes(live, None) + 64)
    result, created, survivors = intake(store, chunk('wal', 1060, text='Buffered words.'), target_id='live')
    assert result['id'] == 'wal' and created and len(survivors) == 1
    assert result['sync_live_target'] is False
    assert _row(store, 'live') == live
    repeated, created, survivors = intake(store, chunk('wal', 1060, text='Buffered words.'), target_id='live')
    assert repeated['id'] == 'wal' and not created and not survivors
    assert _row(store, 'live') == live


def test_full_smart_merge_survivor_keeps_its_donor_redirect(monkeypatch):
    store = StrictFirestore()
    _smart_merge_pair(store)
    survivor, donor = deepcopy(_row(store, 'p')), deepcopy(_row(store, 'n'))
    monkeypatch.setattr(
        assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', estimate_firestore_document_bytes(survivor, None) + 32
    )
    result, created, _ = intake(store, chunk('wal-new', 1620, text='Let us order the mushroom one.'), target_id='n')
    assert result['id'] == 'wal-new' and created
    assert _row(store, 'p') == survivor and _row(store, 'n') == donor


def test_full_conversation_with_manual_speakers_is_never_a_donor(monkeypatch):
    store = _full_store(monkeypatch)
    _row(store, 'a')['manual_speaker_assignments'] = {'generation': 1}
    labeled = deepcopy(_row(store, 'a'))
    result, created, _ = intake(store, chunk('b', 1060, text='Unlabeled new speech.'))
    assert result['id'] == 'b' and created
    assert _row(store, 'a') == labeled


def test_commit_proven_full_conversation_is_excluded_even_under_the_budget():
    store = StrictFirestore()
    intake(store, chunk('a', 1000))
    before = deepcopy(_row(store, 'a'))
    with store.lock:
        result, created, _ = assignment.assign_in_transaction(
            store.transaction(),
            store.collection('users').document('u'),
            chunk('b', 1060),
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda payload: None,
            full_ids=frozenset({'a'}),
        )
    assert result['id'] == 'b' and created
    assert _row(store, 'a') == before


# ----------------------------------------------------------- commit backstop


def _size_error(path: str | None) -> InvalidArgument:
    named = f"Document 'projects/p/databases/(default)/documents/{path}' " if path else 'Document '
    return InvalidArgument(
        f'{named}cannot be written because its size (1,048,601 bytes) exceeds the maximum allowed size of '
        '1,048,576 bytes.'
    )


class _RejectingTransaction(StrictFirestoreTransaction):
    """Rejects the commit like Firestore's size limit and rolls the staged writes back."""

    def __init__(self, database, failures, name):
        super().__init__(database)
        self._failures = failures
        self._name = name
        self._snapshot = None
        self.written: list[tuple[str, ...]] = []

    def _begin(self, retry_id=None):
        super()._begin(retry_id)
        self._snapshot = deepcopy(self._database.rows)

    def set(self, ref, data):
        self.written.append(ref.path)
        super().set(ref, data)

    def update(self, ref, patch):
        self.written.append(ref.path)
        super().update(ref, patch)

    def _commit(self):
        if self._failures:
            self._failures.pop()
            raise _size_error(self._name(self.written))

    def _rollback(self):
        self._database.rows.clear()
        self._database.rows.update(self._snapshot)


class _RejectingStore(StrictFirestore):
    def __init__(self, failures, name=lambda written: '/'.join(written[0])):
        super().__init__()
        self.failures = [True] * failures
        self.name = name

    def transaction(self):
        transaction = _RejectingTransaction(self, self.failures, self.name)
        self.transactions.append(transaction)
        return transaction


@pytest.fixture
def adapter(monkeypatch):
    from database import conversations as db

    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *args: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *args: None)
    return db


def _seed(db, store, failures_after):
    db.assign_sync_conversation('u', dict(chunk('a', 1000), data_protection_level='enhanced'), firestore_client=store)
    store.failures[:] = [True] * failures_after
    store.transactions.clear()
    return deepcopy(_row(store, 'a'))


def test_one_size_limit_commit_retries_once_into_a_new_conversation(adapter, caplog):
    store = _RejectingStore(0)
    before = _seed(adapter, store, 1)
    result, created, survivors = adapter.assign_sync_conversation(
        'u', dict(chunk('b', 1060), data_protection_level='enhanced'), firestore_client=store
    )
    assert result['id'] == 'b' and created and len(survivors) == 1
    assert len(store.transactions) == 2
    assert _row(store, 'a') == before
    events = _events(caplog)
    assert (
        events[0].split(' job_ref=')[0]
        == 'event=sync_assignment_target reason=size_limit_retry outcome=rejected firestore_doc_kind=conversation'
    )
    assert (
        'event=sync_assignment_target reason=size_rollover outcome=rolled_over trigger=commit_limit created=true '
        'excluded=1 projected_size_bucket=lt_500k'
    ) in [line.split(" job_ref=")[0] for line in events]
    assert any('to=size_limit_retry' in message for message in _events(caplog, 'omi_fallback_event'))
    # An identical retry later deduplicates into the conversation the backstop
    # created; the original is still full, so its merge is rejected once more.
    store.failures[:] = [True]
    retried, created, survivors = adapter.assign_sync_conversation(
        'u', dict(chunk('b', 1060), data_protection_level='enhanced'), firestore_client=store
    )
    assert retried['id'] == 'b' and not created and not survivors
    assert len(conversations(store)) == 2


def test_a_second_size_limit_failure_is_raised_without_writes(adapter):
    store = _RejectingStore(0)
    _seed(adapter, store, 2)
    before = deepcopy(store.rows)
    with pytest.raises(InvalidArgument) as exc:
        adapter.assign_sync_conversation(
            'u', dict(chunk('b', 1060), data_protection_level='enhanced'), firestore_client=store
        )
    assert len(store.transactions) == 2
    assert store.rows == before
    assert exc.value.sync_firestore_doc_kind == 'conversation'


def test_unnamed_size_limit_excludes_the_attempted_canonical(adapter):
    store = _RejectingStore(0, name=lambda written: None)
    before = _seed(adapter, store, 1)
    result, created, _ = adapter.assign_sync_conversation(
        'u', dict(chunk('b', 1060), data_protection_level='enhanced'), firestore_client=store
    )
    assert result['id'] == 'b' and created and len(store.transactions) == 2
    assert _row(store, 'a') == before


@pytest.mark.parametrize(
    'error',
    [
        _size_error('users/u/sync_assignment/1970-01-01'),
        _size_error('users/u/sync_assignment/recent'),
        InvalidArgument('private unexpected input'),
    ],
)
def test_index_or_unclassified_rejections_are_not_retried(adapter, monkeypatch, error):
    store = _RejectingStore(0)
    _seed(adapter, store, 1)
    monkeypatch.setattr(_RejectingTransaction, '_commit', lambda self: (_ for _ in ()).throw(error))
    with pytest.raises(InvalidArgument):
        adapter.assign_sync_conversation(
            'u', dict(chunk('b', 1060), data_protection_level='enhanced'), firestore_client=store
        )
    assert len(store.transactions) == 1


def test_donor_rejection_is_classified_and_the_donor_left_alone(adapter):
    store = _RejectingStore(0)
    adapter.assign_sync_conversation(
        'u', dict(chunk('a', 1000), data_protection_level='enhanced'), firestore_client=store
    )
    adapter.assign_sync_conversation(
        'u', dict(chunk('c', 1240), data_protection_level='enhanced'), firestore_client=store
    )
    donor = deepcopy(_row(store, 'c'))
    store.failures[:] = [True]
    store.name = lambda written: 'users/u/conversations/c'
    store.transactions.clear()
    result, created, _ = adapter.assign_sync_conversation(
        'u', dict(chunk('bridge', 1120), data_protection_level='enhanced'), firestore_client=store
    )
    assert result['id'] == 'a' and not created and len(store.transactions) == 2
    assert _row(store, 'c') == donor


# ------------------------------------------------------------ bounded tokens


@pytest.mark.parametrize(
    'error,kind',
    [
        (_size_error('users/uid-1/conversations/conv-1'), 'conversation'),
        (_size_error('users/uid-1/sync_assignment/2026-10-03'), 'sync_day_index'),
        (_size_error('users/uid-1/sync_assignment/recent'), 'sync_recent'),
        (_size_error('users/uid-1/conversations/conv-1/photos/p-1'), 'other'),
        (_size_error('users/uid-1'), 'other'),
        (_size_error(None), 'none'),
        (InvalidArgument('The transaction has expired'), 'none'),
        (ServiceUnavailable("documents/users/uid-1/conversations/conv-1'"), 'none'),
        (ValueError("documents/users/uid-1/conversations/conv-1'"), 'none'),
    ],
)
def test_document_kind_comes_from_collection_segments_only(error, kind):
    assert firestore_document_kind(error) == kind
    assert kind in FIRESTORE_DOCUMENT_KINDS


def test_document_path_is_parsed_from_the_verbatim_prod_message():
    error = _size_error('users/uid-1/conversations/conv-1')
    assert firestore_error_document_path(error) == ('users', 'uid-1', 'conversations', 'conv-1')
    # The quoted path is kept whole: an id may legitimately end in punctuation.
    error = _size_error('users/uid-1/conversations/conv-1.')
    assert firestore_error_document_path(error) == ('users', 'uid-1', 'conversations', 'conv-1.')


def test_estimate_sizes_vectors_per_dimension_and_sets_as_arrays():
    empty = estimate_firestore_document_bytes({}, 'p/d')
    assert estimate_firestore_document_bytes({'v': Vector([0.1, 0.2, 0.3])}, 'p/d') == empty + 2 + 8 * 3
    assert estimate_firestore_document_bytes({'s': {'ab', 'c'}}, 'p/d') == empty + 2 + 3 + 2
    assert estimate_firestore_document_bytes({'s': frozenset({1, 2})}, 'p/d') == empty + 2 + 16
    assert estimate_firestore_document_bytes({'s': {'ab', 'c'}}, 'p/d') == estimate_firestore_document_bytes(
        {'s': ['ab', 'c']}, 'p/d'
    )


def test_estimate_counts_references_and_floors_unknown_values():
    class _Ref:
        path = 'users/u/conversations/c'

    class _Terse:
        def __str__(self):
            return 'x'

    assert estimate_firestore_document_bytes({'r': _Ref()}, 'p/d') == (
        # Each of the four segments plus one byte, plus 16 (slashes are not stored).
        estimate_firestore_document_bytes({}, 'p/d')
        + 2
        + (len('usersuconversationsc') + 4 + 16)
    )
    assert (
        estimate_firestore_document_bytes({'t': _Terse()}, 'p/d')
        == estimate_firestore_document_bytes({}, 'p/d') + 2 + 16
    )


@pytest.mark.parametrize(
    'path,canonical,expected',
    [
        ('users/u/conversations/full', 'full', ('full', 'conversation')),
        ('users/u/conversations/donor', 'full', ('donor', 'donor')),
        (None, 'full', ('full', 'none')),
        ('users/u/sync_assignment/recent', 'full', (None, 'sync_recent')),
        # A path is present but unparseable: it could be an index document.
        ('users', 'full', (None, 'none')),
    ],
)
def test_size_limited_conversation_names_only_conversations(path, canonical, expected):
    error = _size_error(path)
    assert assignment.size_limited_conversation(error, canonical) == expected
    assert error.sync_firestore_doc_kind == expected[1]
    assert assignment.size_limited_conversation(InvalidArgument('other'), canonical) == (None, 'none')


def test_backstop_runs_at_most_twice_and_only_for_a_routable_rejection():
    calls = []

    def run(full_ids):
        calls.append(full_ids)
        if len(calls) == 1:
            raise _size_error('users/u/conversations/full')
        return 'ok'

    assert assignment.run_with_size_limit_backstop(run, lambda: 'full') == 'ok'
    assert calls == [frozenset(), frozenset({'full'})]

    calls.clear()

    def always(full_ids):
        calls.append(full_ids)
        raise _size_error('users/u/conversations/full')

    with pytest.raises(InvalidArgument):
        assignment.run_with_size_limit_backstop(always, lambda: 'full')
    assert len(calls) == 2

    calls.clear()

    def other(full_ids):
        calls.append(full_ids)
        raise ServiceUnavailable('transient')

    with pytest.raises(ServiceUnavailable):
        assignment.run_with_size_limit_backstop(other, lambda: 'full')
    assert len(calls) == 1


def test_pipeline_doc_kind_prefers_the_bounded_stamp():
    error = _size_error('users/u/conversations/c')
    assert _firestore_doc_kind(error) == 'conversation'
    error.sync_firestore_doc_kind = 'donor'
    assert _firestore_doc_kind(error) == 'donor'
    error.sync_firestore_doc_kind = 'users/u/conversations/c'
    assert _firestore_doc_kind(error) == 'conversation'


# --------------------------------------------------------- pre-absorption cap


def test_absorption_cap_stops_donors_but_keeps_fitting_incoming_append_on_canonical(caplog):
    """The 800 KiB donor cap does not forbid an append that fits the 900 KiB budget."""
    store = _receipt_bridge_store(850 * 1024)
    donor = deepcopy(_row(store, 'c'))
    result, created, survivors = intake(store, chunk('b', 1120, text='One short bridging sentence.'))
    assert result['id'] == 'a' and not created and survivors
    assert _row(store, 'c') == donor
    assert _texts(_row(store, 'a'))[-1] == 'One short bridging sentence.'
    assert len(conversations(store)) == 2
    assert [line.split(" job_ref=")[0] for line in _events(caplog)] == [
        'event=sync_assignment_target outcome=size_cap_stop projected_size_bucket=800_900k'
    ]
    assert not result['sync_merged_from']


def test_over_budget_bridge_rolls_incoming_to_a_safe_neighbour(caplog):
    store = _receipt_bridge_store(950 * 1024)
    before = {cid: deepcopy(_row(store, cid)) for cid in ('a', 'c')}
    result, created, survivors = intake(store, chunk('b', 1120, text='One short bridging sentence.'))
    assert result['id'] == 'c' and not created and survivors
    assert _row(store, 'a') == before['a']
    assert _texts(_row(store, 'c')) == ['One short bridging sentence.', 'A separate later remark.']
    assert any('reason=size_rollover outcome=rolled_over' in line for line in _events(caplog))


def test_donor_redirect_projection_is_capped_too(caplog):
    store = _receipt_bridge_store(1000)
    # Bulk retained only on the donor is not copied into the survivor.
    _row(store, 'c')['retained_metadata'] = 'x' * (801 * 1024)
    before = deepcopy(_row(store, 'c'))
    intake(store, chunk('b', 1120))
    assert _row(store, 'c') == before
    assert 'outcome=size_cap_stop' in caplog.text


@pytest.mark.parametrize('level', ['enhanced', 'standard'])
def test_assignment_cap_measures_the_actual_encoder(adapter, monkeypatch, level):
    # A compressible transcript is large in plaintext but small on disk.
    store = StrictFirestore()

    def assign(row):
        return adapter.assign_sync_conversation('u', dict(row, data_protection_level=level), firestore_client=store)

    assign(chunk('a', 1000, text='synthetic speech ' * 1000))
    assign(chunk('c', 1240, text='separate synthetic speech ' * 1000))
    before = deepcopy(store.rows)
    observed = []
    original = assignment.projected_document_bytes

    def observe(reference, payload, current=None):
        observed.append((deepcopy(payload), deepcopy(current)))
        return original(reference, payload, current)

    monkeypatch.setattr(assignment, 'projected_document_bytes', observe)
    merged, _, _ = assign(chunk('b', 1120))
    assert _row(store, 'c')['deleted']
    assert len(merged['transcript_segments']) == 3
    assert isinstance(_row(store, 'a')['transcript_segments'], str if level == 'enhanced' else bytes)
    assert observed
    # Replay the identical plan with the cap one byte below its actual encoded size.
    # StrictFirestore retains DELETE_FIELD sentinels literally. Remove them
    # when measuring what the real update stores.
    actual = original(
        store.collection('users').document('u').collection('conversations').document('a'), _row(store, 'a')
    )
    store.rows = deepcopy(before)
    monkeypatch.setattr(assignment, 'CONVERSATION_ABSORPTION_BYTE_CAP', actual)
    assign(chunk('b', 1120))
    assert _row(store, 'c')['deleted']  # encoded equality fits; plaintext is much larger
    store.rows = deepcopy(before)
    monkeypatch.setattr(assignment, 'CONVERSATION_ABSORPTION_BYTE_CAP', actual - 1)
    assign(chunk('b', 1120))
    assert _row(store, 'c') == before[('users', 'u', 'conversations', 'c')]


@pytest.mark.parametrize(
    'size, expected',
    [
        (0, 'lt_500k'),
        (500 * 1024 - 1, 'lt_500k'),
        (500 * 1024, '500_700k'),
        (700 * 1024 - 1, '500_700k'),
        (700 * 1024, '700_800k'),
        (800 * 1024 - 1, '700_800k'),
        (800 * 1024, '800_900k'),
        (900 * 1024 - 1, '800_900k'),
        (900 * 1024, '900k_1m'),
        (1024 * 1024, '900k_1m'),
        (1024 * 1024 + 1, 'gt_1m'),
    ],
)
def test_projected_size_bucket_boundaries(size, expected):
    assert projected_size_bucket(size) == expected


def test_cap_accepts_a_donor_prefix_and_keeps_remaining_speech(caplog):
    store = StrictFirestore()
    _sized_row(store, 'a', 1000, 700 * 1024)
    intake(store, chunk('c', 1240, text='First synthetic donor. ' * 2600))
    intake(store, chunk('e', 1480, text='Second synthetic donor. ' * 2600))
    before = deepcopy(_row(store, 'e'))
    incoming = chunk('b', 1120, text='Synthetic bridging speech.')
    incoming['finished_at'] = chunk('end', 1400)['finished_at']
    result, _, _ = intake(store, incoming)
    assert _row(store, 'c')['sync_merged_into'] == 'a'
    assert _row(store, 'e') == before
    assert len(result['transcript_segments']) == 3
    assert _texts(result)[1] == 'Synthetic bridging speech.'
    assert len(conversations(store)) == 2
    assert estimate_firestore_document_bytes(_row(store, 'a'), None) <= 800 * 1024
    assert any('outcome=size_cap_stop' in event for event in _events(caplog))


def test_projection_counts_retained_fields_and_real_delete_sentinels():
    ref = SimpleNamespace(path='users/synthetic/conversations/projected')
    before = {'retained': 'x' * 1000, 'removed': 'x' * 900000, 'replaced': 'before'}
    patch = {'removed': DELETE_FIELD, 'replaced': b'after'}
    expected = {'retained': before['retained'], 'replaced': b'after'}
    assert projected_document_bytes(ref, patch, before) == estimate_firestore_document_bytes(expected, ref.path)
    assert 'removed' in before


@pytest.mark.parametrize('new_speech', [False, True])
def test_cap_stop_never_recreates_an_excluded_existing_anchor(new_speech):
    store = _receipt_bridge_store(850 * 1024)
    donor = _row(store, 'c')
    donor['started_at'] = chunk('start', 1100)['started_at']
    donor['finished_at'] = chunk('finish', 1500)['finished_at']
    donor['transcript_segments'] = [
        dict(chunk('early', 1100, text='Earlier durable speech.')['transcript_segments'][0]),
        dict(chunk('tail', 1500, text='Original tail speech.')['transcript_segments'][0], start=400.0, end=409.5),
    ]
    before = {cid: deepcopy(_row(store, cid)) for cid in ('a', 'c')}
    store.transactions.clear()
    text = 'New tail speech.' if new_speech else 'Original tail speech.'
    # The original anchor owns earlier speech and bridges the otherwise
    # disconnected 850KiB survivor to this late/retried chunk.
    result, created, _ = intake(store, chunk('c', 1520 if new_speech else 1500, text=text))
    assert result['id'] == 'c' and not created
    assert _row(store, 'a') == before['a']
    assert _texts(result) == ['Earlier durable speech.', 'Original tail speech.'] + ([text] if new_speech else [])
    assert not _row(store, 'c').get('deleted')
    assert not any(path[2] == 'conversations' for path, _ in store.transactions[-1].sets)


@pytest.mark.parametrize('destination', ['new_row', 'sibling_row', 'fresh_row'])
def test_rollover_attribution_describes_limited_payload(monkeypatch, caplog, destination):
    from uuid import uuid4

    from config.sync_telemetry import bounded_correlation_ref
    from utils.sync.size_telemetry import with_size_attribution

    store = _full_store(monkeypatch)
    if destination == 'sibling_row':
        intake(store, chunk('sibling', 1120, text='Speech already on the sibling.'))
    elif destination == 'fresh_row':
        store.rows[('users', 'u', 'conversations', 'incoming')] = dict(
            chunk('incoming', 1060), deleted=True, discarded=True, sync_merged_into='a', sync_content_revision=1
        )
    caplog.clear()
    job, attempt = str(uuid4()), str(uuid4())

    @with_size_attribution
    def invoke(*, job_id, attempt_ref):
        return intake(store, chunk('incoming', 1060, text='Private speech that must never be logged.'))

    result, created, _ = invoke(job_id=job, attempt_ref=attempt)
    event = next(line for line in _events(caplog) if 'reason=size_rollover' in line)
    assert f'job_ref={bounded_correlation_ref(job)} attempt_ref={bounded_correlation_ref(attempt)}' in event
    assert f"rollover_target_kind={'new_row' if destination == 'fresh_row' else destination}" in event
    assert 'outcome=rolled_over' in event
    # The destination has fewer segments. Report the plan that exceeded the limit.
    assert f"segments_bucket={'3' if destination == 'sibling_row' else '2'}" in event
    assert 'speech_seconds_bucket=30' in event
    assert all(value not in event for value in [job, attempt, 'Private speech', 'incoming', 'pendant'])
    assert created is (destination != 'sibling_row')
    if destination == 'fresh_row':
        assert result['id'] not in {'incoming', 'a'}
    else:
        assert result['id'] == {'new_row': 'incoming', 'sibling_row': 'sibling'}[destination]


def test_backstop_logs_rollover_only_after_successful_commit(adapter, caplog):
    from uuid import uuid4

    from utils.sync.size_telemetry import with_size_attribution

    store = _RejectingStore(0)
    _seed(adapter, store, 1)

    @with_size_attribution
    def invoke(*, job_id, attempt_ref):
        return adapter.assign_sync_conversation(
            'u', dict(chunk('b', 1060), data_protection_level='enhanced'), firestore_client=store
        )

    invoke(job_id=str(uuid4()), attempt_ref=str(uuid4()))
    events = _events(caplog)
    rejection = next(line for line in events if 'reason=size_limit_retry' in line)
    rollover = next(line for line in events if 'reason=size_rollover ' in line)
    assert 'segments_bucket=2' in rejection and 'speech_seconds_bucket=30' in rejection
    assert 'outcome=rolled_over' in rollover and 'stage=commit' in rollover
    assert 'rollover_target_kind=new_row' in rollover
    assert 'stage=plan' not in caplog.text


def test_abandoned_transaction_plan_never_claims_a_committed_rollover(monkeypatch, caplog):
    store = _full_store(monkeypatch)
    caplog.clear()

    def retry_like_sdk(_full_ids):
        intake(store, chunk('b', 1060, text='Words rolled over by the losing plan.'))
        # The next snapshot observes a concurrent deletion of the old full row.
        # It is now a dedupe-only plan and owes no rollover success event.
        _row(store, 'a')['deleted'] = True
        return intake(store, chunk('b', 1060, text='Words rolled over by the losing plan.'))

    result, created, survivors = assignment.run_with_size_limit_backstop(retry_like_sdk, lambda: 'b')
    assert result['id'] == 'b' and not created and not survivors
    assert not [line for line in _events(caplog) if 'outcome=rolled_over' in line]


@pytest.mark.parametrize('commit_rejection', [False, True])
@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_batch_live_replacement_sizes_before_write_and_routes_commit_retry(
    adapter, monkeypatch, caplog, level, commit_rejection
):
    store = _RejectingStore(0)
    original = dict(chunk('live', 1000), data_protection_level=level, record_lane_owner='batch_live_v1')
    original['transcript_segments'][0]['id'] = 'old'
    original['structured'] = {'overview': 'x' * 4000}
    encoded = adapter._prepare_conversation_for_write(deepcopy(original), 'u', level)
    store.rows[('users', 'u', 'conversations', 'live')] = encoded
    before = deepcopy(encoded)
    incoming = dict(chunk('replacement', 1000, text='Entirely new finalized speech.'), data_protection_level=level)
    incoming['transcript_segments'][0]['id'] = 'new'
    incoming['_batch_replace_live'] = {'start': 1000, 'end': 1010}
    incoming['_batch_require_live_target'] = True
    if commit_rejection:
        store.failures[:] = [True]
    else:
        monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 3500)
    result, created, survivors = adapter.assign_sync_conversation(
        'u', incoming, target_id='live', firestore_client=store
    )
    assert created and result['id'] != 'live' and survivors
    assert _row(store, 'live') == before
    assert _texts(result) == ['Entirely new finalized speech.']
    assert len(store.transactions) == (2 if commit_rejection else 1)
    writes = store.transactions[-1].written
    assert ('users', 'u', 'conversations', 'live') not in writes
    assert 'outcome=rolled_over' in caplog.text
    assert f"trigger={'commit_limit' if commit_rejection else 'estimate'}" in caplog.text
    assert incoming['_batch_replace_live'] == {'start': 1000, 'end': 1010}


def _many_segments(count=4):
    incoming = chunk('large-input', 1060)
    incoming['transcript_segments'] = [
        {
            'id': f'line-{i}',
            'text': f'Unique line {i}. ' + 'x' * 900,
            'start': i * 10.0,
            'end': i * 10.0 + 9.5,
            'speaker_id': 0,
        }
        for i in range(count)
    ]
    incoming['finished_at'] = chunk('finish', 1060 + (count - 1) * 10)['finished_at']
    return incoming


def test_incoming_alone_splits_in_order_without_loss_and_indexes_every_row(monkeypatch):
    store = StrictFirestore()
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 2400)
    incoming = _many_segments()
    before = deepcopy(incoming)
    result, created, survivors = intake(store, incoming)
    rows = sorted(conversations(store), key=lambda row: row['started_at'])
    assert created and len(rows) == 4
    assert [text for row in rows for text in _texts(row)] == _texts(incoming)
    assert len(survivors) == 4 and incoming == before
    assert all(estimate_firestore_document_bytes(row, None) <= 2400 for row in rows)
    recent = store.rows[('users', 'u', 'sync_assignment', 'recent')]['entries']
    day = store.rows[('users', 'u', 'sync_assignment', '1970-01-01')]['entries']
    assert {r['id'] for r in recent} == {r['id'] for r in day} == {r['id'] for r in rows}
    replay, _, kept = intake(store, incoming)
    assert not kept
    assert [text for row in conversations(store) for text in _texts(row)] == [
        text for row in rows for text in _texts(row)
    ]


def test_indivisible_oversized_segment_rejects_before_any_write_with_attribution(monkeypatch, caplog):
    from uuid import uuid4
    from config.sync_telemetry import bounded_correlation_ref
    from utils.sync.size_telemetry import with_size_attribution

    store = StrictFirestore()
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 2400)
    incoming = _many_segments()
    incoming['transcript_segments'][-1]['text'] = 'unlogged input ' * 1000
    before = deepcopy(incoming)
    job, attempt = str(uuid4()), str(uuid4())

    @with_size_attribution
    def invoke(*, job_id, attempt_ref):
        return intake(store, incoming)

    with pytest.raises(SyncAssignmentConflict, match='exceeds sync size budget'):
        invoke(job_id=job, attempt_ref=attempt)
    assert incoming == before and not store.rows
    assert all(not tx.has_written for tx in store.transactions)
    event = next(e for e in _events(caplog) if 'reason=size_rollover_unavailable' in e)
    assert 'outcome=rejected' in event and 'rollover_target_kind=none' in event
    assert f'job_ref={bounded_correlation_ref(job)} attempt_ref={bounded_correlation_ref(attempt)}' in event
    assert 'segments_bucket=1' in event and 'speech_seconds_bucket=10' in event
    assert job not in event and attempt not in event and 'unlogged input' not in event


def test_cap_rollover_attributes_the_actual_sibling_destination(monkeypatch, caplog):
    from uuid import uuid4
    from config.sync_telemetry import bounded_correlation_ref
    from utils.sync.size_telemetry import with_size_attribution

    store = _receipt_bridge_store(850 * 1024)
    # The donor itself is the incoming anchor. Removing it strands its early
    # survivor, so the cap replan appends to the durable donor instead.
    donor = _row(store, 'c')
    donor['started_at'] = chunk('start', 1100)['started_at']
    donor['finished_at'] = chunk('finish', 1500)['finished_at']
    job, attempt = str(uuid4()), str(uuid4())

    @with_size_attribution
    def invoke(*, job_id, attempt_ref):
        return intake(store, chunk('c', 1520, text='Unlogged new tail speech.'))

    result, created, _ = invoke(job_id=job, attempt_ref=attempt)
    assert result['id'] == 'c' and not created
    event = next(e for e in _events(caplog) if 'reason=size_rollover ' in e)
    assert 'trigger=size_cap' in event and 'outcome=rolled_over' in event
    assert 'rollover_target_kind=sibling_row' in event
    assert f'job_ref={bounded_correlation_ref(job)} attempt_ref={bounded_correlation_ref(attempt)}' in event
    assert 'segments_bucket=3' in event and 'speech_seconds_bucket=30' in event
    assert job not in event and attempt not in event and 'Unlogged' not in event


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_split_rollover_sizes_every_part_with_real_encoder_and_indexes_all(adapter, monkeypatch, level):
    incoming = _many_segments()
    incoming['data_protection_level'] = level
    for i, segment in enumerate(incoming['transcript_segments']):
        segment['text'] = ''.join(hashlib.sha256(f'{i}:{j}'.encode()).hexdigest() for j in range(30))
    probe = StrictFirestore()
    single = deepcopy(incoming)
    single['transcript_segments'] = single['transcript_segments'][:1]
    adapter.assign_sync_conversation('u', single, firestore_client=probe)
    budget = estimate_firestore_document_bytes(_row(probe, single['id']), None) + 250
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', budget)
    indexed = []
    monkeypatch.setattr(adapter, 'index_sync_assignment', lambda uid, ids, donors: indexed.extend(ids))
    store = StrictFirestore()
    result, created, survivors = adapter.assign_sync_conversation('u', incoming, firestore_client=store)
    assert created and len(survivors) == 4
    rows = sorted(conversations(store), key=lambda row: row['started_at'])
    assert len(rows) == 4
    assert set(indexed) == {r['id'] for r in rows}
    decoded = [
        adapter.decode_transcript_segments_verified(
            'u', r['transcript_segments'], r.get('transcript_segments_compressed', False)
        )
        for r in rows
    ]
    assert [s['text'] for segments in decoded for s in segments] == _texts(incoming)
    assert all(estimate_firestore_document_bytes(row, None) <= budget for row in rows)
    assert all(
        estimate_firestore_document_bytes(payload, None) <= budget
        for tx in store.transactions
        for path, payload in tx.sets
        if path[2] == 'conversations'
    )


def test_split_rollover_legacy_completion_finishes_every_row_before_acknowledging(monkeypatch):
    import threading
    from utils.sync.intake_completion import complete_sync_intake

    store = StrictFirestore()
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', 2400)
    incoming = _many_segments()
    result, created, survivors = intake(store, incoming)
    ids = {row['id'] for row in conversations(store)}
    effects = []
    response = {'new_memories': set(), 'updated_memories': set()}
    complete_sync_intake(
        uid='u',
        assigned=result,
        created=created,
        survivors=survivors,
        response=response,
        lock=threading.Lock(),
        language='en',
        audio_enabled=True,
        store_audio=lambda cid: effects.append(('audio', cid)),
        finish=lambda uid, row, *args, **kwargs: effects.append(('finish', row['id'])),
        mark_finalize=lambda: None,
        acknowledge=lambda: effects.append(('ack', None)),
    )
    assert {cid for kind, cid in effects if kind == 'audio'} == ids
    assert {cid for kind, cid in effects if kind == 'finish'} == ids
    assert response['new_memories'] == ids
    assert effects[-1] == ('ack', None)
    assert sum(kind == 'ack' for kind, _ in effects) == 1
    assert '_sync_size_rollover_rows' not in result
