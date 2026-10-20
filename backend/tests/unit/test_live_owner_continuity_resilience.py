"""Unit tests for the live owner-continuity hardening.

Verifies:
- Owner, device and conversation identifiers that cannot address a document raise a
  stable ``ValueError`` before any Redis or Firestore call happens.
- Projected snapshots that are missing, raise, or return a non-dict payload are treated
  as absent instead of raising ``AttributeError`` from a field read.
- Revisions reject booleans, non-integers and negatives; payloads must be dicts.
- Store failures fail closed: reads return ``None`` and writes never raise.
"""

import os

import pytest

# ``utils.encryption`` refuses to import without a key; the doubles below replace the
# framing helpers, so the value only has to satisfy the length check.
os.environ.setdefault('ENCRYPTION_SECRET', 'omi-unit-test-key-0123456789abcdef')

import database.live_owner_continuity as continuity

BAD_IDENTIFIERS = [
    '',
    '   ',
    None,
    True,
    False,
    7,
    3.5,
    '.',
    '..',
    '__reserved__',
    'a/b',
    'a\\b',
    'a..b',
    'u' * 129,
    'a\x00b',
    'a\x1fb',
    'a\x7fb',
]


class _Snap:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _RaisingSnap:
    def __init__(self, error):
        self.exists = True
        self._error = error

    def to_dict(self):
        raise self._error


class _NoToDict:
    exists = True


class _Doc:
    def __init__(self, client, path, doc_id):
        self._client = client
        self._path = path
        self.id = doc_id

    def collection(self, name):
        return _Collection(self._client, (*self._path, self.id, name))

    def get(self, field_paths=None, transaction=None):
        self._client.gets.append(
            {'path': (*self._path, self.id), 'field_paths': field_paths, 'transaction': transaction}
        )
        entry = self._client.snaps.get(self.id)
        if isinstance(entry, Exception):
            raise entry
        if callable(entry):
            return entry()
        return entry if entry is not None else _Snap(None, exists=False)


class _Collection:
    def __init__(self, client, path):
        self._client = client
        self.path = path

    def document(self, doc_id):
        self._client.paths.append((*self.path, doc_id))
        return _Doc(self._client, self.path, doc_id)


class _Client:
    def __init__(self, snaps=None):
        self.snaps = snaps or {}
        self.paths = []
        self.gets = []
        self.transactions = 0

    def collection(self, name):
        return _Collection(self, (name,))

    def transaction(self):
        self.transactions += 1
        return _Tx()


class _Redis:
    def __init__(self, result=None, raises=False):
        self.result = result
        self.raises = raises
        self.calls = []

    def eval(self, script, numkeys, *args):
        self.calls.append({'script': script, 'numkeys': numkeys, 'args': args})
        if self.raises:
            raise RuntimeError('redis down')
        return self.result


PREFIX = b'enc:'


class _Tx:
    """The only attribute ``@firestore.transactional`` inspects before dispatch."""

    _read_only = False


def _fake_decrypt(blob, uid):
    if not isinstance(blob, (bytes, bytearray)) or not bytes(blob).startswith(PREFIX):
        raise ValueError('owner_reconnect_undecryptable')
    return bytes(blob)[len(PREFIX):]


def _fake_decode(uid, assignments, compressed):
    if not isinstance(assignments, (dict, str)):
        raise ValueError('owner_reconnect_undecodable')
    return {'uid': uid, 'assignments': assignments, 'compressed': bool(compressed)}


@pytest.fixture(autouse=True)
def _hermetic_framing(monkeypatch):
    """Keep framing and decoding local so the tests target this module only."""
    monkeypatch.setattr(continuity, 'encrypt_audio_chunk', lambda data, uid: PREFIX + data)
    monkeypatch.setattr(continuity, 'decrypt_audio_file', _fake_decrypt)
    monkeypatch.setattr(continuity, 'decode_manual_speaker_assignments', _fake_decode)
    # ``authority_snapshot`` applies ``@firestore.transactional`` to its inner reader at
    # call time; the fake transaction below cannot satisfy the wrapper's retry contract,
    # so the decorator becomes the identity for these tests.
    monkeypatch.setattr(continuity.firestore, 'transactional', lambda fn: fn)


@pytest.fixture
def redis_(monkeypatch):
    fake = _Redis()
    monkeypatch.setattr(continuity, '_client', lambda: fake)
    return fake


def _payload_doc(device='dev-1', version=1, extra=None):
    data = {'device': device, 'v': version}
    data.update(extra or {})
    return _Snap(data)


def test_keys_share_a_hash_tag():
    generation, evidence = continuity._keys('u1', 'dev-1')
    assert generation.endswith(':generation')
    assert evidence.endswith(':evidence')
    tag = generation[len('owner-reconnect:') : generation.index(':v1')]
    assert tag == evidence[len('owner-reconnect:') : evidence.index(':v1')]


def test_keys_differ_per_device():
    assert continuity._keys('u1', 'dev-1')[0] != continuity._keys('u1', 'dev-2')[0]


@pytest.mark.parametrize('uid', BAD_IDENTIFIERS)
def test_begin_rejects_unusable_owners(uid, redis_):
    with pytest.raises(ValueError):
        continuity.begin(uid, 'dev-1', 'token-1')
    assert redis_.calls == []


@pytest.mark.parametrize('device', BAD_IDENTIFIERS)
def test_begin_rejects_unusable_devices(device, redis_):
    with pytest.raises(ValueError):
        continuity.begin('u1', device, 'token-1')
    assert redis_.calls == []


@pytest.mark.parametrize('token', ['', '   ', None, True, 5, 't' * 257, 'a\x00b'])
def test_begin_rejects_unusable_tokens(token, redis_):
    with pytest.raises(ValueError):
        continuity.begin('u1', 'dev-1', token)
    assert redis_.calls == []


def test_begin_fails_closed_when_redis_raises(monkeypatch):
    monkeypatch.setattr(continuity, '_client', lambda: _Redis(raises=True))
    assert continuity.begin('u1', 'dev-1', 'token-1') == (None, 'unavailable')


def test_begin_reports_absent_without_evidence(redis_):
    redis_.result = None
    assert continuity.begin('u1', 'dev-1', 'token-1') == (None, 'absent')


def test_begin_uses_three_keys_and_the_token(redis_):
    redis_.result = None
    continuity.begin('u1', 'dev-1', 'token-9')
    call = redis_.calls[0]
    assert call['numkeys'] == 3
    assert len(call['args']) == 4
    assert call['args'][-1] == 'token-9'
    assert call['args'][2].endswith(':revision')


@pytest.mark.parametrize(
    'raw', ['not-bytes', b'x' * (continuity.MAX_PAYLOAD_BYTES + 1), b'\xff\xfe', b'enc:{']
)
def test_begin_treats_unusable_evidence_as_corrupt(raw, redis_):
    redis_.result = raw
    assert continuity.begin('u1', 'dev-1', 'token-1') == (None, 'corrupt')


def test_begin_returns_a_valid_payload(redis_):
    import json

    body = json.dumps({'device': 'dev-1', 'v': 1, 'segments': 2}).encode()
    redis_.result = b'enc:' + body
    payload, status = continuity.begin('u1', 'dev-1', 'token-1')
    assert status == 'loaded'
    assert payload == {'device': 'dev-1', 'v': 1, 'segments': 2}


def test_begin_rejects_a_foreign_device(redis_):
    import json

    redis_.result = json.dumps({'device': 'dev-2', 'v': 1}).encode()
    assert continuity.begin('u1', 'dev-1', 'token-1') == (None, 'corrupt')


def test_begin_rejects_a_foreign_version(redis_):
    import json

    redis_.result = json.dumps({'device': 'dev-1', 'v': 2}).encode()
    assert continuity.begin('u1', 'dev-1', 'token-1') == (None, 'corrupt')


def test_begin_rejects_a_non_dict_payload(redis_):
    import json

    redis_.result = json.dumps(['dev-1', 1]).encode()
    assert continuity.begin('u1', 'dev-1', 'token-1') == (None, 'corrupt')


@pytest.mark.parametrize('payload', [None, {'x': 1}])
def test_payload_normalizes_snapshot_shapes(payload):
    assert continuity._payload(None) is None
    assert continuity._payload(_Snap(None, exists=False)) is None
    assert continuity._payload(_RaisingSnap(ValueError('bad'))) is None
    assert continuity._payload(_NoToDict()) is None
    assert continuity._payload(_Snap(payload)) == payload


def test_payload_rejects_a_list_payload():
    assert continuity._payload(_Snap([1, 2, 3])) is None


@pytest.mark.parametrize(
    'data, expected',
    [
        (None, False),
        ({}, True),
        ({'deleted': True}, False),
        ({'discarded': 1}, False),
        ({'is_locked': True}, False),
    ],
)
def test_eligibility(data, expected):
    assert continuity._eligible(data) is expected


@pytest.mark.parametrize('uid', BAD_IDENTIFIERS)
def test_donor_authority_rejects_unusable_owners(uid):
    with pytest.raises(ValueError):
        continuity.donor_authority(uid, 'conv-1', firestore_client=_Client())


@pytest.mark.parametrize('conversation', BAD_IDENTIFIERS)
def test_donor_authority_rejects_unusable_conversations(conversation):
    with pytest.raises(ValueError):
        continuity.donor_authority('u1', conversation, firestore_client=_Client())


def test_donor_authority_reads_only_projected_fields():
    client = _Client({'conv-1': _Snap({'manual_speaker_assignments': {'a': 1}})})
    result = continuity.donor_authority('u1', 'conv-1', firestore_client=client)
    assert result == {'uid': 'u1', 'assignments': {'a': 1}, 'compressed': False}
    get = client.gets[0]
    assert get['path'] == ('users', 'u1', 'conversations', 'conv-1')
    assert set(get['field_paths']) == set(continuity._PROJECTION)


def test_donor_authority_returns_none_for_a_missing_document():
    assert continuity.donor_authority('u1', 'conv-1', firestore_client=_Client()) is None


@pytest.mark.parametrize(
    'snapshot',
    [
        _Snap(None, exists=True),
        _Snap([('manual_speaker_assignments', {})], exists=True),
        _RaisingSnap(AttributeError('boom')),
        _NoToDict(),
    ],
)
def test_donor_authority_fails_closed_on_unusable_payloads(snapshot):
    client = _Client({'conv-1': snapshot})
    assert continuity.donor_authority('u1', 'conv-1', firestore_client=client) is None


@pytest.mark.parametrize('flag', continuity._ELIGIBLE_FIELDS)
def test_donor_authority_returns_none_for_ineligible_receipts(flag):
    client = _Client({'conv-1': _Snap({flag: True, 'manual_speaker_assignments': {'a': 1}})})
    assert continuity.donor_authority('u1', 'conv-1', firestore_client=client) is None


def test_donor_authority_fails_closed_when_the_store_raises():
    client = _Client({'conv-1': PermissionError('denied')})
    assert continuity.donor_authority('u1', 'conv-1', firestore_client=client) is None


def test_donor_authority_returns_none_when_decoding_raises(monkeypatch):
    def explode(*args, **kwargs):
        raise ValueError('undecodable')

    monkeypatch.setattr(continuity, 'decode_manual_speaker_assignments', explode)
    client = _Client({'conv-1': _Snap({'manual_speaker_assignments': {'a': 1}})})
    assert continuity.donor_authority('u1', 'conv-1', firestore_client=client) is None


def test_donor_authority_flags_compressed_assignments():
    client = _Client(
        {'conv-1': _Snap({'manual_speaker_assignments': 'blob', 'manual_speaker_assignments_compressed': 1})}
    )
    assert continuity.donor_authority('u1', 'conv-1', firestore_client=client)['compressed'] is True


@pytest.mark.parametrize('conversations', [(), ('a', 'b', 'c', 'd'), 'conv-1', None, 5])
def test_authority_snapshot_rejects_unusable_arity_or_shape(conversations):
    with pytest.raises(ValueError):
        continuity.authority_snapshot('u1', conversations, firestore_client=_Client())


@pytest.mark.parametrize('uid', BAD_IDENTIFIERS)
def test_authority_snapshot_rejects_unusable_owners(uid):
    with pytest.raises(ValueError):
        continuity.authority_snapshot(uid, ('conv-1',), firestore_client=_Client())


def test_authority_snapshot_reads_each_conversation_once():
    client = _Client({'conv-1': _Snap({'manual_speaker_assignments': {'a': 1}}), 'conv-2': _Snap({})})
    result = continuity.authority_snapshot('u1', ('conv-1', 'conv-1', 'conv-2'), firestore_client=client)
    assert set(result) == {'conv-1', 'conv-2'}
    assert len(client.gets) == 2
    assert client.transactions == 1
    assert all(get['transaction'] is not None for get in client.gets)


def test_authority_snapshot_maps_unusable_payloads_to_none():
    client = _Client({'conv-1': _Snap(None, exists=True), 'conv-2': _Snap([1])})
    assert continuity.authority_snapshot('u1', ('conv-1', 'conv-2'), firestore_client=client) == {
        'conv-1': None,
        'conv-2': None,
    }


def test_authority_snapshot_skips_ineligible_receipts():
    client = _Client({'conv-1': _Snap({'is_locked': True, 'manual_speaker_assignments': {'a': 1}})})
    assert continuity.authority_snapshot('u1', ('conv-1',), firestore_client=client) == {'conv-1': None}


def test_authority_snapshot_decodes_eligible_receipts():
    client = _Client({'conv-1': _Snap({'manual_speaker_assignments': {'a': 1}})})
    result = continuity.authority_snapshot('u1', ('conv-1',), firestore_client=client)
    assert result['conv-1'] == {'uid': 'u1', 'assignments': {'a': 1}, 'compressed': False}


@pytest.mark.parametrize('revision', [True, False, -1, 1.0, '1', None, [1]])
def test_publish_rejects_unusable_revisions(revision, redis_):
    with pytest.raises(ValueError):
        continuity.publish('u1', 'dev-1', 'token-1', {'v': 1}, revision)
    assert redis_.calls == []


@pytest.mark.parametrize('payload', [[1, 2], 'text', 5, True])
def test_publish_rejects_non_dict_payloads(payload, redis_):
    with pytest.raises(ValueError):
        continuity.publish('u1', 'dev-1', 'token-1', payload, 1)
    assert redis_.calls == []


@pytest.mark.parametrize('uid', BAD_IDENTIFIERS)
def test_publish_rejects_unusable_owners(uid, redis_):
    with pytest.raises(ValueError):
        continuity.publish(uid, 'dev-1', 'token-1', None, 1)
    assert redis_.calls == []


def test_publish_skips_oversized_payloads(monkeypatch, redis_):
    monkeypatch.setattr(
        continuity, 'encrypt_audio_chunk', lambda data, uid: b'x' * (continuity.MAX_PAYLOAD_BYTES + 1)
    )
    assert continuity.publish('u1', 'dev-1', 'token-1', {'v': 1}, 1) is None
    assert redis_.calls == []


def test_publish_issues_a_cas_write(redis_):
    continuity.publish('u1', 'dev-1', 'token-1', {'v': 1}, 4)
    call = redis_.calls[0]
    assert call['numkeys'] == 3
    assert call['args'][3] == 'token-1'
    assert call['args'][5] == continuity.GAP_SECONDS
    assert call['args'][6] == 4
    assert call['args'][4].startswith(b'enc:')


def test_publish_withdraws_with_an_empty_evidence_value(redis_):
    continuity.publish('u1', 'dev-1', 'token-1', None, 2)
    assert redis_.calls[0]['args'][4] == b''


def test_publish_never_raises_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(continuity, '_client', lambda: _Redis(raises=True))
    assert continuity.publish('u1', 'dev-1', 'token-1', {'v': 1}, 1) is None


def test_publish_never_raises_when_encryption_fails(monkeypatch, redis_):
    def explode(data, uid):
        raise ValueError('bad key')

    monkeypatch.setattr(continuity, 'encrypt_audio_chunk', explode)
    assert continuity.publish('u1', 'dev-1', 'token-1', {'v': 1}, 1) is None