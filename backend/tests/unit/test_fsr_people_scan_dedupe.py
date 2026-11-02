"""Task-attempt raw People reuse: counted streams, explicit safety and fill fences."""

from contextvars import Context, copy_context
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import person_aliases as people


class CountingFirestore:
    def __init__(self):
        self.rows = {
            'u1': {'p1': {'name': 'Alice', 'aliases': ['Ally']}, 'p2': {'name': 'Hidden', 'is_dismissed': True}},
            'u2': {'p1': {'name': 'Other owner'}},
        }
        self.scans = []
        self.after_snapshot = None
        self.failure = None
        self.generations = {uid: 1 for uid in self.rows}
        self.generation_reads = []
        self.generation_failure = None
        self.document_reads = 0

    def collection(self, name):
        assert name == 'users'
        return SimpleNamespace(document=lambda uid: Owner(self, uid))

    def transaction(self):
        return SimpleNamespace(
            update=lambda ref, patch: self.rows[ref.uid][ref.person_id].update(deepcopy(patch)),
            set=lambda ref, patch, **kwargs: self.generations.__setitem__(
                ref.uid, self.generations.get(ref.uid, 0) + 1
            ),
        )


class Owner:
    def __init__(self, db, uid):
        self.db, self.uid = db, uid

    def collection(self, name):
        if name == 'people':
            return Query(self.db, self.uid, name)
        assert name == 'people_meta'
        return SimpleNamespace(document=lambda key: SimpleNamespace(uid=self.uid, get=self.generation))

    def generation(self):
        self.db.generation_reads.append(self.uid)
        if self.db.generation_failure:
            raise self.db.generation_failure
        value = self.db.generations.get(self.uid)
        return SimpleNamespace(exists=value is not None, to_dict=lambda: {'generation': value}, update_time=value)


class Query:
    def __init__(self, db, uid, name, limit=None):
        assert name == 'people'
        self.db, self.uid, self.cap = db, uid, limit

    def limit(self, cap):
        return Query(self.db, self.uid, 'people', cap)

    def document(self, person_id):
        return SimpleNamespace(
            uid=self.uid,
            id=person_id,
            parent=SimpleNamespace(parent=Owner(self.db, self.uid)),
            person_id=person_id,
            get=lambda **kwargs: SimpleNamespace(
                exists=person_id in self.db.rows[self.uid],
                to_dict=lambda: deepcopy(self.db.rows[self.uid][person_id]),
            ),
        )

    def stream(self):
        self.db.scans.append((self.uid, self.cap))
        if self.db.failure:
            raise self.db.failure
        rows = list(self.db.rows[self.uid].items())
        if self.cap is not None:
            rows = rows[: self.cap]
        self.db.document_reads += max(1, len(rows))
        snapshots = [SimpleNamespace(id=key, to_dict=lambda row=deepcopy(row): row) for key, row in rows]
        if self.db.after_snapshot:
            callback, self.db.after_snapshot = self.db.after_snapshot, None
            callback()
        return iter(snapshots)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"people_scan_dedupe":100}')
    monkeypatch.delenv('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_ENTRIES', raising=False)
    monkeypatch.delenv('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_BYTES', raising=False)
    return CountingFirestore()


def hint(db, uid='u1', **kwargs):
    return people.list_people(db, uid, memoize=True, **kwargs)


@pytest.mark.parametrize('enabled,expected', [(False, 2), (True, 1)])
def test_two_identical_calls_two_streams_off_one_on(db, monkeypatch, enabled, expected):
    if not enabled:
        monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    with people.people_scan_attempt():
        first = hint(db)
        assert first == hint(db) == [{'name': 'Alice', 'aliases': ['Ally'], 'id': 'p1'}]
    assert len(db.scans) == expected


@pytest.mark.parametrize('raw', ['', '{broken', '{"people_scan_dedupe":0}'])
def test_off_path_identity_keeps_live_reads_and_values(db, monkeypatch, raw):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)

    def no_serialization(*args, **kwargs):
        pytest.fail('off path must not serialize or deserialize')

    monkeypatch.setattr(people.pickle, 'dumps', no_serialization)
    monkeypatch.setattr(people.pickle, 'loads', no_serialization)
    with people.people_scan_attempt():
        assert hint(db)[0]['name'] == 'Alice'
        db.rows['u1']['p1']['name'] = 'Renamed outside aliases'
        assert hint(db)[0]['name'] == 'Renamed outside aliases'
        assert hint(db, include_dismissed=True)[1]['id'] == 'p2'
        assert hint(db, limit=1)[0]['id'] == 'p1'
    assert db.scans == [('u1', None), ('u1', None), ('u1', None), ('u1', 1)]


def test_uid_gate_is_consulted_on_each_call(db, monkeypatch):
    calls = []

    def enabled(name, uid):
        calls.append((name, uid))
        return uid == 'u1'

    monkeypatch.setattr(people, 'lever_enabled', enabled)
    with people.people_scan_attempt():
        for uid in ('u1', 'u1', 'u2', 'u2'):
            hint(db, uid)
    assert len(db.scans) == 3
    assert calls == [('people_scan_dedupe', uid) for uid in ('u1', 'u1', 'u2', 'u2')]


def test_scope_required_and_new_attempt_always_reads(db):
    hint(db)
    hint(db)
    for _ in range(2):
        with people.people_scan_attempt():
            hint(db)
            hint(db)
    assert len(db.scans) == 4
    assert people._people_scan_memo.get() is None


def test_exit_on_error_clears_even_copied_executor_context(db):
    with pytest.raises(RuntimeError):
        with people.people_scan_attempt():
            hint(db)
            memo = people._people_scan_memo.get()
            copied = copy_context()
            raise RuntimeError('attempt failed')
    assert not memo.active and not memo.entries and memo.bytes_used == 0 and memo.client is None
    copied.run(hint, db)
    copied.run(hint, db)
    assert len(db.scans) == 3


def test_new_attempt_in_inherited_context_and_nested_scope_are_isolated(db):
    with people.people_scan_attempt():
        hint(db)
        with people.people_scan_attempt():
            assert len(people._people_scan_memo.get().entries) == 0
            db.rows['u1']['p1']['name'] = 'New attempt'
            hint(db)
        assert hint(db)[0]['name'] == 'New attempt'
    assert len(db.scans) == 3


def test_uid_limit_and_dismissed_variants_never_share(db):
    with people.people_scan_attempt():
        assert hint(db) == hint(db)
        assert hint(db, limit=1) == hint(db, limit=1)
        assert hint(db, limit=0) == []
        assert hint(db, 'u2')[0]['name'] == 'Other owner'
        assert len(hint(db, include_dismissed=True)) == 2
        assert len(hint(db, include_dismissed=True)) == 2
    assert db.scans == [('u1', None), ('u1', 1), ('u1', 0), ('u2', None), ('u1', None), ('u1', None)]


def test_other_firestore_client_cannot_share_same_uid(db):
    other = CountingFirestore()
    other.rows['u1']['p1']['name'] = 'Other database'
    with people.people_scan_attempt():
        hint(db)
        assert hint(other)[0]['name'] == 'Other database'
        assert hint(other)[0]['name'] == 'Other database'
    assert len(db.scans) == 1 and len(other.scans) == 2


@pytest.mark.parametrize('kwargs', [{}, {'include_dismissed': True}])
def test_authority_privacy_and_mutation_adjacent_defaults_always_live(db, kwargs):
    with people.people_scan_attempt():
        hint(db)
        db.rows['u1']['p1']['is_dismissed'] = True
        first = people.list_people(db, 'u1', **kwargs)
        second = people.list_people(db, 'u1', **kwargs)
        assert first == second
        assert (len(second) == 2) if kwargs else (second == [])
        assert hint(db) == []
    assert len(db.scans) == 4


def test_caller_mutation_does_not_pollute_raw_memo(db):
    stamp = datetime(2026, 10, 17, tzinfo=timezone.utc)
    db.rows['u1']['p1']['created_at'] = stamp
    with people.people_scan_attempt():
        first = hint(db)
        first[0]['aliases'].append('Caller mutation')
        first[0]['voice_learning_state'] = 'derived authority'
        second = hint(db)
        second[0]['aliases'].clear()
        third = hint(db)
        assert third[0]['aliases'] == ['Ally']
        assert third[0]['created_at'] == stamp
        assert 'voice_learning_state' not in third[0]
    assert len(db.scans) == 1


@pytest.mark.parametrize('write', ['dismiss', 'rename'])
def test_alias_write_invalidates_all_uid_variants(db, monkeypatch, write):
    monkeypatch.setattr(people, 'dismiss_person_transaction', people.dismiss_person_transaction.to_wrap)
    monkeypatch.setattr(people, 'update_person_name_transaction', people.update_person_name_transaction.to_wrap)
    with people.people_scan_attempt():
        hint(db)
        hint(db, limit=1)
        if write == 'dismiss':
            assert people.dismiss_person_soft(db, 'u1', 'p1')
            assert hint(db) == hint(db, limit=1) == []
        else:
            assert people.rename_person_retaining_aliases(db, 'u1', 'p1', 'Alicia')
            assert hint(db)[0]['name'] == hint(db, limit=1)[0]['name'] == 'Alicia'
    assert len(db.scans) == 4


@pytest.mark.parametrize('write', ['dismiss', 'rename'])
def test_uncertain_write_clears_inflight_snapshot_and_propagates(db, monkeypatch, write):
    def failed_commit(*args):
        # Read while the wrapper's write fence is held: no stale hit or new fill.
        hint(db)
        assert people._people_scan_memo.get().entries == {}
        raise RuntimeError('uncertain commit')

    name = 'dismiss_person_transaction' if write == 'dismiss' else 'update_person_name_transaction'
    monkeypatch.setattr(people, name, failed_commit)
    with people.people_scan_attempt():
        hint(db)
        with pytest.raises(RuntimeError, match='uncertain commit'):
            if write == 'dismiss':
                people.dismiss_person_soft(db, 'u1', 'p1')
            else:
                people.rename_person_retaining_aliases(db, 'u1', 'p1', 'Alicia')
        hint(db)
        assert people._people_scan_memo.get().writers == 0
    assert len(db.scans) == 3


def test_write_during_stream_fences_old_fill(db, monkeypatch):
    monkeypatch.setattr(people, 'dismiss_person_transaction', people.dismiss_person_transaction.to_wrap)
    db.after_snapshot = lambda: people.dismiss_person_soft(db, 'u1', 'p1')
    with people.people_scan_attempt():
        assert hint(db)[0]['name'] == 'Alice'  # Original read completed before the write.
        assert hint(db) == []  # Must not reuse that pre-write snapshot.
        assert hint(db) == []
    assert len(db.scans) == 2


def test_failed_stream_never_leaves_partial_memo(db):
    with people.people_scan_attempt():
        db.failure = RuntimeError('Firestore unavailable')
        with pytest.raises(RuntimeError, match='Firestore unavailable'):
            hint(db)
        assert people._people_scan_memo.get().entries == {}
        db.failure = None
        hint(db)
        hint(db)
    assert len(db.scans) == 2


@pytest.mark.parametrize('setting,value', [('MAX_ENTRIES', '0'), ('MAX_BYTES', '0'), ('MAX_BYTES', '1')])
def test_admission_bounds_fail_open_to_live_reads(db, monkeypatch, setting, value):
    monkeypatch.setenv('FIRESTORE_PEOPLE_SCAN_MEMO_' + setting, value)
    with people.people_scan_attempt():
        assert hint(db) == hint(db)
        memo = people._people_scan_memo.get()
        assert memo.entries == {} and memo.bytes_used == 0
    assert len(db.scans) == 2


def test_entry_limit_and_byte_budget_are_enforced_across_uids(db, monkeypatch):
    monkeypatch.setenv('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_ENTRIES', '1')
    with people.people_scan_attempt():
        hint(db)
        hint(db, 'u2')
        hint(db, 'u2')
        hint(db)
        memo = people._people_scan_memo.get()
        assert len(memo.entries) == 1 and memo.bytes_used <= memo.max_bytes
    assert len(db.scans) == 3
    monkeypatch.setenv('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_ENTRIES', '256')
    with people.people_scan_attempt():
        hint(db)
        memo = people._people_scan_memo.get()
        memo.max_bytes = memo.bytes_used
        hint(db, 'u2')
        hint(db, 'u2')
        assert len(memo.entries) == 1 and memo.bytes_used == memo.max_bytes
    assert len(db.scans) == 6


def test_invalid_tunables_use_defaults(db, monkeypatch):
    monkeypatch.setenv('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_ENTRIES', 'invalid')
    monkeypatch.setenv('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_BYTES', 'invalid')
    with people.people_scan_attempt():
        memo = people._people_scan_memo.get()
        assert memo.max_entries == 256 and memo.max_bytes == 2 * 1024 * 1024
        hint(db)
        hint(db)
    assert len(db.scans) == 1


def test_serialization_failure_preserves_live_result(db, monkeypatch):
    def fail(*args, **kwargs):
        raise TypeError('unsupported Firestore value')

    monkeypatch.setattr(people.pickle, 'dumps', fail)
    with people.people_scan_attempt():
        assert hint(db) == hint(db)
        assert people._people_scan_memo.get().entries == {}
    assert len(db.scans) == 2


def test_known_spellings_hint_reader_reuses_attempt_scan(db, monkeypatch):
    from utils.llm import known_spellings

    monkeypatch.setattr(known_spellings, 'get_firestore_client', lambda: db)
    with people.people_scan_attempt():
        first = known_spellings._people_spellings('u1')
        assert first == known_spellings._people_spellings('u1') == [{'name': 'Alice'}]
    assert db.scans == [('u1', 200)]


@pytest.mark.parametrize('raw', ['', '{"people_scan_dedupe":0}'])
def test_known_spellings_off_path_keeps_live_reads(db, monkeypatch, raw):
    from utils.llm import known_spellings

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
    monkeypatch.setattr(known_spellings, 'get_firestore_client', lambda: db)
    with people.people_scan_attempt():
        assert known_spellings._people_spellings('u1') == [{'name': 'Alice'}]
        db.rows['u1']['p1']['name'] = 'Renamed live'
        assert known_spellings._people_spellings('u1') == [{'name': 'Renamed live'}]
    assert db.scans == [('u1', 200), ('u1', 200)]


@pytest.mark.parametrize('write', ['dismiss', 'rename'])
def test_generation_invalidates_across_fresh_request_context(db, monkeypatch, write):
    monkeypatch.setattr(people, 'dismiss_person_transaction', people.dismiss_person_transaction.to_wrap)
    monkeypatch.setattr(people, 'update_person_name_transaction', people.update_person_name_transaction.to_wrap)
    with people.people_scan_attempt():
        assert hint(db)[0]['name'] == 'Alice'
        assert len(db.generation_reads) == 1
        if write == 'dismiss':
            Context().run(people.dismiss_person_soft, db, 'u1', 'p1')
        else:
            Context().run(people.rename_person_retaining_aliases, db, 'u1', 'p1', 'Alicia')
        # A fresh Context cannot invalidate the memo's in-process counter.
        assert len(people._people_scan_memo.get().entries) == 1
        result = hint(db)
        if write == 'dismiss':
            assert result == []
        else:
            assert result[0]['name'] == 'Alicia'
            assert result[0]['aliases'] == ['Ally', 'Alice']
        assert len(db.generation_reads) == 2
        assert hint(db) == result
        assert len(db.generation_reads) == 3
    assert len(db.scans) == 2


def test_unchanged_hit_costs_exactly_one_generation_read(db):
    with people.people_scan_attempt():
        hint(db)
        before = len(db.generation_reads)
        assert hint(db)[0]['name'] == 'Alice'
        assert len(db.generation_reads) - before == 1
    assert len(db.scans) == 1


def test_cross_request_write_during_fill_does_not_stamp_old_result_current(db, monkeypatch):
    monkeypatch.setattr(people, 'dismiss_person_transaction', people.dismiss_person_transaction.to_wrap)
    db.after_snapshot = lambda: Context().run(people.dismiss_person_soft, db, 'u1', 'p1')
    with people.people_scan_attempt():
        assert hint(db)[0]['name'] == 'Alice'
        assert hint(db) == []
        assert hint(db) == []
    assert len(db.scans) == 2 and len(db.generation_reads) == 3


@pytest.mark.parametrize('mode', ['missing', 'malformed', 'unavailable'])
def test_untrusted_generation_cannot_serve_or_admit_memo(db, mode):
    with people.people_scan_attempt():
        hint(db)
        db.rows['u1']['p1']['is_dismissed'] = True
        if mode == 'missing':
            del db.generations['u1']
        elif mode == 'malformed':
            db.generations['u1'] = 'invalid'
        else:
            db.generation_failure = RuntimeError('metadata unavailable')
        assert hint(db) == hint(db) == []
        assert not people._people_scan_memo.get().entries
    assert len(db.scans) == 3


def test_hint_reader_cross_request_dismissal_is_fenced(db, monkeypatch):
    from utils.llm import known_spellings

    monkeypatch.setattr(known_spellings, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(people, 'dismiss_person_transaction', people.dismiss_person_transaction.to_wrap)
    with people.people_scan_attempt():
        assert known_spellings._people_spellings('u1') == [{'name': 'Alice'}]
        Context().run(people.dismiss_person_soft, db, 'u1', 'p1')
        assert known_spellings._people_spellings('u1') == []
    assert db.scans == [('u1', 200), ('u1', 200)]


@pytest.mark.parametrize('enabled,expected_reads', [(False, 1000), (True, 110)])
def test_billed_document_read_reduction_includes_generation_lookups(db, monkeypatch, enabled, expected_reads):
    db.rows['u1'] = {f'p{i}': {'name': f'Person {i}'} for i in range(100)}
    if not enabled:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"people_scan_dedupe":0}')
    with people.people_scan_attempt():
        for _ in range(10):
            assert len(hint(db)) == 100
    # 10 x 100 off; 100 people + 10 generation lookups on (includes the fill).
    assert db.document_reads + len(db.generation_reads) == expected_reads
    assert len(db.generation_reads) == (10 if enabled else 0)
