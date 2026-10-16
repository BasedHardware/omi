"""``resolve_live_continuation`` subtracted a stored ``finished_at`` from the caller's
``now`` directly, so a naive datetime from Firestore and an aware ``now`` raised
``TypeError`` and the whole continuation lookup failed. Identifiers were never
validated (a '/' silently retargets the document path), the timeout was passed
through unclamped, a malformed proposal raised ``KeyError``, and a Firestore
transport failure propagated instead of degrading to "no continuation".

These tests are hermetic: the Firestore client is a dict-backed stand-in, so no
network and no credentials are involved.
"""

from datetime import datetime, timezone

import database.listen_continuations as listen_continuations

UID = 'user-1'
ORIGIN_ID = 'origin-1'
CONVERSATION_ID = 'conversation-1'
RECORDING_SESSION_ID = 'session-1'
CANDIDATE_CONVERSATION_ID = 'conversation-2'
CANDIDATE_SESSION_ID = 'session-2'
PROPOSAL = {'conversation_id': CANDIDATE_CONVERSATION_ID, 'recording_session_id': CANDIDATE_SESSION_ID}
POINTER_PATH = f'users/{UID}/recording_sessions/{ORIGIN_ID}'


class _FakeSnapshot:
    def __init__(self, row):
        self._row = row
        self.exists = row is not None

    def to_dict(self):
        return dict(self._row) if self._row is not None else None


class _FakeDocument:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def get(self, transaction=None):
        return _FakeSnapshot(self._store.get(self._path))

    def collection(self, name):
        return _FakeCollection(self._store, f'{self._path}/{name}')


class _FakeCollection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id):
        return _FakeDocument(self._store, f'{self._path}/{doc_id}')


class _FakeTransaction:
    """Just enough of ``google.cloud.firestore_v1.transaction.Transaction`` for the
    ``@firestore.transactional`` wrapper, which drives these hooks itself."""

    def __init__(self):
        self._max_attempts = 1
        self._read_only = False
        self._id = b'fake-transaction'
        self.updates = []

    def update(self, ref, data):
        self.updates.append((ref._path, data))

    def _begin(self, retry_id=None):
        pass

    def _commit(self):
        pass

    def _rollback(self):
        pass

    def _clean_up(self):
        pass


class _FakeClient:
    def __init__(self, store):
        self.store = store
        self.transactions = []

    def collection(self, name):
        return _FakeCollection(self.store, name)

    def transaction(self):
        transaction = _FakeTransaction()
        self.transactions.append(transaction)
        return transaction


class _BrokenClient:
    def collection(self, name):
        raise RuntimeError('firestore transport unavailable')


def _store(pointer_row, candidate_row=None):
    store = {
        POINTER_PATH: {
            'uid': UID,
            'recording_session_id': ORIGIN_ID,
            'live_continuation': {
                'conversation_id': CONVERSATION_ID,
                'recording_session_id': RECORDING_SESSION_ID,
            },
        },
        f'users/{UID}/conversations/{CONVERSATION_ID}': pointer_row,
    }
    if candidate_row is not None:
        store[f'users/{UID}/conversations/{CANDIDATE_CONVERSATION_ID}'] = candidate_row
    return store


def _patch_flow(monkeypatch):
    """Keep the resumability and gap decisions explicit so the flow is exercised."""
    monkeypatch.setattr(
        listen_continuations, 'resumable_continuation', lambda row, **kwargs: bool(row.get('resumable'))
    )
    monkeypatch.setattr(listen_continuations, 'gap_splits', lambda *args, **kwargs: True)
    monkeypatch.setattr(listen_continuations, 'continuation_timeout', lambda row, timeout: timeout)


def _resolve(client, **overrides):
    kwargs = {
        'source': 'phone',
        'device_id': 'device-1',
        'now': datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc),
        'timeout': 300,
        'firestore_client': client,
    }
    kwargs.update(overrides)
    return listen_continuations.resolve_live_continuation(UID, ORIGIN_ID, **kwargs)


def test_elapsed_seconds_aligns_naive_and_aware_values():
    now = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    naive_finish = datetime(2026, 10, 16, 11, 59, 30)
    aware_finish = datetime(2026, 10, 16, 11, 59, 30, tzinfo=timezone.utc)

    assert listen_continuations._elapsed_seconds(now, naive_finish) == 30.0
    assert listen_continuations._elapsed_seconds(now, aware_finish) == 30.0
    assert listen_continuations._elapsed_seconds(naive_finish, now) == -30.0


def test_clean_identifier_rejects_path_segments_and_blanks():
    for bad in ('', '   ', 'a/b', 'a\\b', 'a\x00b', None, 7, 'x' * 300):
        assert listen_continuations._clean_identifier(bad, 'uid') is None
    assert listen_continuations._clean_identifier('  user-1  ', 'uid') == 'user-1'


def test_clean_timeout_clamps_to_a_sane_window():
    assert listen_continuations._clean_timeout(0) == 1
    assert listen_continuations._clean_timeout(-10) == 1
    assert listen_continuations._clean_timeout(10**9) == listen_continuations.MAX_CONTINUATION_TIMEOUT
    assert listen_continuations._clean_timeout(60) == 60
    assert listen_continuations._clean_timeout('nonsense') == listen_continuations.DEFAULT_CONTINUATION_TIMEOUT
    assert listen_continuations._clean_timeout(None) == listen_continuations.DEFAULT_CONTINUATION_TIMEOUT


def test_clean_proposal_requires_both_binding_ids():
    assert listen_continuations._clean_proposal(None) is None
    assert listen_continuations._clean_proposal('nope') is None
    assert listen_continuations._clean_proposal({'conversation_id': CANDIDATE_CONVERSATION_ID}) is None
    assert (
        listen_continuations._clean_proposal(
            {'conversation_id': 'a/b', 'recording_session_id': CANDIDATE_SESSION_ID}
        )
        is None
    )
    assert listen_continuations._clean_proposal(PROPOSAL) == PROPOSAL


def test_invalid_identifiers_are_rejected_before_any_firestore_call():
    broken = _BrokenClient()
    assert _resolve(broken, source='') == (None, None)
    assert _resolve(broken, source='phone/../other') == (None, None)
    assert (
        listen_continuations.resolve_live_continuation(
            '',
            ORIGIN_ID,
            source='phone',
            device_id=None,
            now=datetime.now(timezone.utc),
            timeout=300,
            firestore_client=broken,
        )
        == (None, None)
    )
    assert (
        listen_continuations.resolve_live_continuation(
            UID,
            'a/b',
            source='phone',
            device_id=None,
            now=datetime.now(timezone.utc),
            timeout=300,
            firestore_client=broken,
        )
        == (None, None)
    )


def test_transport_failure_degrades_to_no_continuation():
    assert _resolve(_BrokenClient()) == (None, None)


def test_naive_stored_finish_does_not_break_the_gap_check(monkeypatch):
    _patch_flow(monkeypatch)
    client = _FakeClient(
        _store(
            {
                'source': 'phone',
                'client_device_id': 'device-1',
                'finished_at': datetime(2026, 10, 16, 11, 59, 30),  # naive, as Firestore returns it
                'resumable': False,
            },
            {'resumable': True},
        )
    )

    adopted, retired = _resolve(client, proposed=PROPOSAL)

    assert retired == {'conversation_id': CONVERSATION_ID, 'recording_session_id': RECORDING_SESSION_ID}
    assert adopted == PROPOSAL


def test_aware_stored_finish_still_retires_the_gap(monkeypatch):
    _patch_flow(monkeypatch)
    client = _FakeClient(
        _store(
            {
                'source': 'phone',
                'client_device_id': 'device-1',
                'finished_at': datetime(2026, 10, 16, 11, 59, 30, tzinfo=timezone.utc),
                'resumable': False,
            },
            {'resumable': True},
        )
    )

    adopted, retired = _resolve(client, proposed=PROPOSAL)

    assert retired == {'conversation_id': CONVERSATION_ID, 'recording_session_id': RECORDING_SESSION_ID}
    assert adopted == PROPOSAL


def test_adoptable_proposal_is_written_to_the_pointer(monkeypatch):
    _patch_flow(monkeypatch)
    client = _FakeClient(
        _store({'source': 'phone', 'client_device_id': 'device-1', 'resumable': False}, {'resumable': True})
    )

    adopted, retired = _resolve(client, proposed=PROPOSAL)

    assert adopted == PROPOSAL
    assert retired is None
    assert client.transactions[0].updates == [(POINTER_PATH, {'live_continuation': PROPOSAL})]


def test_malformed_proposal_is_ignored_instead_of_raising(monkeypatch):
    _patch_flow(monkeypatch)
    client = _FakeClient(_store({'source': 'phone', 'client_device_id': 'device-1', 'resumable': False}))

    assert _resolve(client, proposed={'recording_session_id': RECORDING_SESSION_ID}) == (None, None)
    assert _resolve(client, proposed={'conversation_id': 'a/b', 'recording_session_id': CANDIDATE_SESSION_ID}) == (
        None,
        None,
    )


def test_calendar_continuity_row_ignores_an_invalid_uid():
    row = {'external_data': {'calendar_event_id': 'event-1'}}
    assert listen_continuations.calendar_continuity_row('a/b', row, firestore_client=_BrokenClient()) is row
