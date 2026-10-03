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

from google.api_core.exceptions import InvalidArgument, ServiceUnavailable
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.types import document as document_pb
from google.cloud.firestore_v1.vector import Vector
import pytest

from database._client import FIRESTORE_DOCUMENT_KINDS, firestore_document_kind, firestore_error_document_path
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from tests.unit.test_sync_cross_job_assignment import _smart_merge_pair, chunk, conversations, intake
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes
from utils.sync import assignment
from utils.sync.assignment_errors import SyncAssignmentSuperseded
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
    """850 KiB stored plus a small bridge stays under 900 KiB, so nothing changes.

    The unbounded run (budget lifted far past any document) is the pre-PR
    assignment: same canonical, receipt owner, donor redirect, index and rows.
    """
    stored = 850 * 1024
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
    assert _events(caplog) == [
        'event=sync_assignment_target outcome=size_rollover trigger=estimate created=true excluded=1'
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
    assert events == ['event=sync_assignment_target outcome=size_rollover trigger=estimate created=true excluded=1']
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
    assert _events(caplog) == [
        f'event=sync_assignment_target outcome=size_rollover trigger=estimate created=true excluded={len(ids)}'
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


def test_redirected_anchor_with_no_safe_home_keeps_the_original_write(monkeypatch, caplog):
    store = _full_store(monkeypatch)
    store.rows[('users', 'u', 'conversations', 'x')] = dict(
        chunk('x', 1060), deleted=True, discarded=True, sync_merged_into='a', sync_content_revision=1
    )
    result, created, _ = intake(store, chunk('x', 1060, text='Words for a redirected anchor.'))
    assert result['id'] == 'a' and not created
    assert _events(caplog) == ['event=sync_assignment_target outcome=size_rollover_unavailable trigger=estimate']
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
    assert events[0] == 'event=sync_assignment_target outcome=size_limit_retry firestore_doc_kind=conversation'
    assert (
        'event=sync_assignment_target outcome=size_rollover trigger=commit_limit created=true ' 'excluded=1'
    ) in events
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
