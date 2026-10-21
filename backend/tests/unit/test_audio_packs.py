import json
from copy import deepcopy

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from utils.other import audio_packs as packs


class Bucket:
    """Generation enforcing fake: uploads replace live content atomically."""

    def __init__(self):
        self.objects = {}
        self.counter = 0
        self.fail_delete = False
        self.fail_verified = False

    def blob(self, name, generation=None):
        return Blob(self, name, generation)

    def get_blob(self, name):
        if name not in self.objects:
            return None
        blob = self.blob(name)
        blob.reload()
        return blob

    def list_blobs(self, prefix):
        return [self.get_blob(n) for n in sorted(self.objects) if n.startswith(prefix)]


class Blob:
    def __init__(self, bucket, name, generation=None):
        self.bucket, self.name, self.generation = bucket, name, generation
        self.metadata = None
        self.size = 0

    def exists(self):
        return self.name in self.bucket.objects

    def reload(self):
        if not self.exists():
            raise NotFound('missing')
        record = self.bucket.objects[self.name]
        self.generation, self.metadata, self.size = record['gen'], deepcopy(record['metadata']), len(record['data'])

    def _check(self, match):
        current = self.bucket.objects.get(self.name)
        if match is not None and (current['gen'] if current else 0) != match:
            raise PreconditionFailed('generation mismatch')

    def download_as_bytes(self, if_generation_match=None):
        if not self.exists():
            raise NotFound('missing')
        self._check(if_generation_match)
        return self.bucket.objects[self.name]['data']

    def upload_from_string(self, data, content_type=None, if_generation_match=None):
        self._check(if_generation_match)
        if (
            self.bucket.fail_verified
            and self.name.startswith(packs.INDEX_PREFIX)
            and (b'"state":"verified"' in data or b'"state":"complete"' in data)
        ):
            self.bucket.fail_verified = False
            raise RuntimeError('index publication failure')
        self.bucket.counter += 1
        self.generation = self.bucket.counter
        self.bucket.objects[self.name] = {'data': data, 'metadata': deepcopy(self.metadata), 'gen': self.generation}
        self.size = len(data)

    def patch(self, if_generation_match=None):
        self._check(if_generation_match)
        self.bucket.objects[self.name]['metadata'] = deepcopy(self.metadata)

    def delete(self, if_generation_match=None):
        if not self.exists():
            raise NotFound('missing')
        self._check(if_generation_match)
        if self.bucket.fail_delete:
            self.bucket.fail_delete = False
            raise RuntimeError('interrupted delete')
        del self.bucket.objects[self.name]


@pytest.fixture
def bucket(monkeypatch):
    monkeypatch.setenv('AUDIO_CANONICAL_PACKING_ENABLED', 'true')
    return Bucket()


def capture(bucket, owner='alice', data=b'encoded-opus', conv='one', day='2020-10-14'):
    return packs.archive_capture(
        bucket,
        owner,
        data,
        format='opus',
        provenance={'capture_day': day, 'device': 'test'},
        conversation_ranges=[{'conversation_id': conv, 'start': 1, 'end': 2}],
        identity=packs._sha(data),
    )


def manifests(bucket, owner='alice'):
    return [
        json.loads(b.download_as_bytes())
        for b in bucket.list_blobs(packs.owner_prefix(packs.INDEX_PREFIX, owner))
        if b.name.removeprefix(packs.owner_prefix(packs.INDEX_PREFIX, owner)).split('/', 1)[0]
        not in {'captures', 'links', 'deletions'}
    ]


def test_default_off(monkeypatch):
    monkeypatch.delenv('AUDIO_CANONICAL_PACKING_ENABLED', raising=False)
    bucket = Bucket()
    assert capture(bucket) is None
    assert packs.pack_owner_day(bucket, 'alice', '2020-10-14') == 0
    assert bucket.objects == {}


def test_byte_roundtrip_and_owner_isolation(bucket):
    source = capture(bucket)
    other = capture(bucket, owner='bob')
    legacy = bucket.blob('raw-mobile-batch/alice/old')
    legacy.upload_from_string(b'old')
    assert packs.pack_owner_day(bucket, 'alice', '2020-10-14') == 1
    assert source not in bucket.objects
    assert other in bucket.objects
    assert legacy.name in bucket.objects
    manifest = manifests(bucket)[0]
    packs.verify_pack(bucket.blob(manifest['pack']).download_as_bytes(), manifest)
    assert manifest['entries'][0]['provenance']['device'] == 'test'
    assert packs.pack_owner_day(bucket, 'alice', '2020-10-14') == 0
    capture(bucket)
    assert source not in bucket.objects  # receipt prevents retry resurrection


def test_resume_after_partial_delete(bucket):
    first = capture(bucket, data=b'first')
    second = capture(bucket, data=b'second')
    bucket.fail_delete = True
    with pytest.raises(RuntimeError):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert manifests(bucket)[0]['state'] == 'verified'
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert first not in bucket.objects and second not in bucket.objects
    assert len(manifests(bucket)) == 1


def test_no_source_deletion_until_verified_index(bucket):
    source = capture(bucket)
    bucket.fail_verified = True
    with pytest.raises(RuntimeError):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert source in bucket.objects
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert source not in bucket.objects


def test_corrupt_pack_never_deletes_source(bucket):
    source = capture(bucket)
    bucket.fail_verified = True
    with pytest.raises(RuntimeError):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    manifest = manifests(bucket)[0]
    bucket.blob(manifest['pack']).upload_from_string(b'corrupt')
    with pytest.raises(ValueError, match='hash mismatch'):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert source in bucket.objects


def test_conversation_rewrite_resumes_after_pack_replaced(bucket):
    capture(bucket, data=b'one', conv='one')
    capture(bucket, data=b'two', conv='two')
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    bucket.fail_verified = True
    with pytest.raises(RuntimeError):
        packs.delete_conversation(bucket, 'alice', 'one')
    assert manifests(bucket)[0]['state'] == 'rewriting'
    packs.delete_conversation(bucket, 'alice', 'one')
    manifest = manifests(bucket)[0]
    assert [e['conversation_ranges'][0]['conversation_id'] for e in manifest['entries']] == ['two']
    packs.verify_pack(bucket.blob(manifest['pack']).download_as_bytes(), manifest)
    with pytest.raises(ValueError, match='blocked'):
        capture(bucket, data=b'one', conv='one')
    assert not bucket.list_blobs(packs.owner_prefix(packs.SOURCE_PREFIX, 'alice'))


def test_day_and_size_boundaries(bucket, monkeypatch):
    monkeypatch.setattr(packs, 'TARGET_BYTES', 6)
    capture(bucket, data=b'1111')
    capture(bucket, data=b'2222')
    next_day = capture(bucket, data=b'3333', day='2020-10-13')
    assert packs.pack_owner_day(bucket, 'alice', '2020-10-14') == 1
    assert packs.pack_owner_day(bucket, 'alice', '2020-10-14') == 1
    assert next_day in bucket.objects


def test_generation_conflict_blocks_cleanup(bucket):
    source = capture(bucket)
    bucket.fail_verified = True
    with pytest.raises(RuntimeError):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    bucket.blob(source).upload_from_string(b'new generation')
    with pytest.raises(PreconditionFailed):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert source in bucket.objects


def test_cross_owner_index_fails_closed(bucket):
    capture(bucket)
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    index = next(
        b
        for b in bucket.list_blobs(packs.owner_prefix(packs.INDEX_PREFIX, 'alice'))
        if b.name.removeprefix(packs.owner_prefix(packs.INDEX_PREFIX, 'alice')).split('/', 1)[0]
        not in {'captures', 'links', 'deletions'}
    )
    manifest = json.loads(index.download_as_bytes())
    manifest['owner'] = 'bob'
    index.upload_from_string(packs._json(manifest))
    with pytest.raises(ValueError, match='cross-owner'):
        packs.delete_conversation(bucket, 'alice', 'one')


def test_merged_capture_survives_and_can_be_erased_via_survivor(bucket):
    capture(bucket, conv='one')
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    before = manifests(bucket)[0]
    old_bytes = bucket.blob(before['pack']).download_as_bytes()
    packs.link_conversations(bucket, 'alice', ['one'], 'merged')
    packs.link_conversations(bucket, 'alice', ['merged'], 'merged-again')
    after = manifests(bucket)[0]
    assert after['entries'][0]['conversation_ranges'][0]['conversation_id'] == 'merged-again'
    assert after['entries'][0]['sha256'] == before['entries'][0]['sha256']
    packs.verify_pack(bucket.blob(before['pack']).download_as_bytes(), after)
    assert bucket.blob(before['pack']).download_as_bytes() != old_bytes
    packs.delete_conversation(bucket, 'alice', 'merged-again')
    assert manifests(bucket)[0]['entries'] == []
    with pytest.raises(ValueError, match='blocked'):
        capture(bucket, data=b'late', conv='one')


@pytest.mark.parametrize('phase', ['source', 'receipt'])
def test_deletion_racing_intake_leaves_no_capture(bucket, monkeypatch, phase):
    original = Blob.upload_from_string
    triggered = False

    def racing_upload(blob, data, **kwargs):
        nonlocal triggered
        result = original(blob, data, **kwargs)
        is_source = blob.name.startswith(packs.SOURCE_PREFIX)
        is_receipt = '/captures/' in blob.name
        if not triggered and ((phase == 'source' and is_source) or (phase == 'receipt' and is_receipt)):
            triggered = True
            packs.delete_conversation(bucket, 'alice', 'one')
        return result

    monkeypatch.setattr(Blob, 'upload_from_string', racing_upload)
    with pytest.raises(ValueError, match='blocked'):
        capture(bucket)
    assert bucket.list_blobs(packs.owner_prefix(packs.SOURCE_PREFIX, 'alice')) == []
    assert bucket.list_blobs(packs.owner_prefix(packs.PACK_PREFIX, 'alice')) == []
    with pytest.raises(ValueError, match='blocked'):
        capture(bucket, data=b'new retry')


def test_pcm_capture_range_uses_full_tail_and_authoritative_span():
    result = packs.pcm_capture_ranges([{'timestamp': 100, 'data': bytes(32000)}], 'c', 16000)
    assert result[0]['end'] == 101
    assert result[0]['samples'] == 16000
    result = packs.pcm_capture_ranges(
        [
            {'timestamp': 100, 'data': bytes(32000)},
            {'timestamp': 102, 'data': bytes(16000), 'span': {'start': 102, 'samples': 8000, 'sample_rate': 16000}},
        ],
        'c',
        16000,
    )
    assert result[1]['end'] == 102.5
    assert result[1]['plaintext_byte_start'] == 32000


def test_post_upload_authority_failure_never_accepts_or_discards_capture(bucket, monkeypatch):
    calls = 0

    def authority(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('authority unavailable')

    monkeypatch.setattr(packs, 'assert_capture_allowed', authority)
    with pytest.raises(RuntimeError, match='authority unavailable'):
        capture(bucket)
    assert bucket.list_blobs(packs.owner_prefix(packs.SOURCE_PREFIX, 'alice'))
    assert bucket.list_blobs(packs.owner_prefix(packs.INDEX_PREFIX, 'alice')) == []


def test_packer_refuses_a_pending_privacy_erasure(bucket):
    capture(bucket)
    bucket.blob(packs.control_path('alice', 'deletions', 'one')).upload_from_string(b'{}')
    with pytest.raises(ValueError, match='blocked'):
        packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert bucket.list_blobs(packs.owner_prefix(packs.PACK_PREFIX, 'alice')) == []


def test_competing_merge_cannot_orphan_the_first_survivor(bucket):
    packs.link_conversations(bucket, 'alice', ['one'], 'first')
    packs.link_conversations(bucket, 'alice', ['one'], 'first')
    with pytest.raises(ValueError, match='another merge'):
        packs.link_conversations(bucket, 'alice', ['one'], 'second')
    assert packs.conversation_chain(bucket, 'alice', 'one') == ['one', 'first']


def test_merge_retargets_unpacked_and_late_capture_without_erasing_bytes(bucket):
    source = capture(bucket)
    packs.link_conversations(bucket, 'alice', ['one'], 'merged')
    blob = bucket.get_blob(source)
    assert blob.download_as_bytes() == b'encoded-opus'
    assert json.loads(blob.metadata['capture'])['conversation_ranges'][0]['conversation_id'] == 'merged'
    late = capture(bucket, data=b'late', conv='one')
    assert (
        json.loads(bucket.get_blob(late).metadata['capture'])['conversation_ranges'][0]['conversation_id'] == 'merged'
    )
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    assert {e['conversation_ranges'][0]['conversation_id'] for e in manifests(bucket)[0]['entries']} == {'merged'}


def test_merge_retarget_resumes_interrupted_manifest_publication(bucket):
    capture(bucket)
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    bucket.fail_verified = True
    with pytest.raises(RuntimeError, match='publication'):
        packs.link_conversations(bucket, 'alice', ['one'], 'merged')
    packs.link_conversations(bucket, 'alice', ['one'], 'merged')
    result = manifests(bucket)[0]
    assert result['state'] == 'complete'
    assert result['entries'][0]['conversation_ranges'][0]['conversation_id'] == 'merged'
    packs.verify_pack(bucket.blob(result['pack']).download_as_bytes(), result)


def test_privacy_erasure_relists_and_refuses_remaining_source(bucket, monkeypatch):
    capture(bucket)
    original = Blob.delete

    def incomplete_delete(blob, **kwargs):
        if blob.name.startswith(packs.SOURCE_PREFIX):
            return
        original(blob, **kwargs)

    monkeypatch.setattr(Blob, 'delete', incomplete_delete)
    with pytest.raises(RuntimeError, match='affected source'):
        packs.delete_conversation(bucket, 'alice', 'one')


def test_privacy_erasure_refuses_unindexed_pack(bucket):
    bucket.blob(packs.owner_prefix(packs.PACK_PREFIX, 'alice') + 'orphan.tar').upload_from_string(b'unknown')
    with pytest.raises(RuntimeError, match='unindexed pack'):
        packs.delete_conversation(bucket, 'alice', 'one')


def test_privacy_relist_does_not_retrieve_unaffected_archive_pack(bucket, monkeypatch):
    capture(bucket, conv='keep', day='2020-10-13')
    packs.pack_owner_day(bucket, 'alice', '2020-10-13')
    unaffected = manifests(bucket)[0]['pack']
    capture(bucket, conv='erase', data=b'erase')
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    original = Blob.download_as_bytes

    def download(blob, **kwargs):
        if blob.name == unaffected:
            raise AssertionError('unnecessary Archive retrieval')
        return original(blob, **kwargs)

    monkeypatch.setattr(Blob, 'download_as_bytes', download)
    packs.delete_conversation(bucket, 'alice', 'erase')
    assert bucket.blob(unaffected).exists()


def test_privacy_relist_refuses_changed_pack_generation(bucket, monkeypatch):
    capture(bucket, conv='keep')
    packs.pack_owner_day(bucket, 'alice', '2020-10-14')
    name = manifests(bucket)[0]['pack']
    bucket.blob(name).upload_from_string(bucket.blob(name).download_as_bytes())
    with pytest.raises(RuntimeError, match='changed pack generation'):
        packs.delete_conversation(bucket, 'alice', 'erase')
