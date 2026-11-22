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
    return Bucket()


def capture(bucket, owner='alice', data=b'encoded-opus', conv='one', day='2020-10-14'):
    # Synthetic pre-existing captures: no production writer is exercised here.
    packs.assert_capture_allowed(bucket, owner, [{'conversation_id': conv}])
    target = packs.conversation_chain(bucket, owner, conv)[-1]
    key = packs._sha(data + conv.encode())
    path = f'{packs.owner_prefix(packs.SOURCE_PREFIX, owner)}{day}/{key}'
    blob = bucket.blob(path)
    blob.metadata = {
        'capture': json.dumps(
            {
                'format': 'opus',
                'provenance': {'capture_day': day, 'device': 'test'},
                'conversation_ranges': [{'conversation_id': target, 'start': 1, 'end': 2}],
            }
        )
    }
    blob.upload_from_string(data)
    return path


def seed_existing_pack(bucket, owner, day):
    """Fixture for already-packed bytes that privacy/merge readers must still serve."""
    sources = bucket.list_blobs(f'{packs.owner_prefix(packs.SOURCE_PREFIX, owner)}{day}/')
    entries, payloads = [], []
    for index, blob in enumerate(sources):
        data = blob.download_as_bytes()
        entries.append(
            {
                **json.loads(blob.metadata['capture']),
                'source': blob.name,
                'generation': str(blob.generation),
                'member': f'{index:06d}.audio',
                'sha256': packs._sha(data),
                'size': len(data),
            }
        )
        payloads.append(data)
    data = packs._tar(entries, payloads)
    pack = f'{packs.owner_prefix(packs.PACK_PREFIX, owner)}{day}/fixture.tar'
    blob = bucket.blob(pack)
    blob.upload_from_string(data)
    manifest = {
        'version': 1,
        'owner': owner,
        'day': day,
        'state': 'complete',
        'pack': pack,
        'pack_generation': str(blob.generation),
        'sha256': packs._sha(data),
        'entries': entries,
    }
    bucket.blob(f'{packs.owner_prefix(packs.INDEX_PREFIX, owner)}{day}/fixture.json').upload_from_string(
        packs._json(manifest)
    )
    for source in sources:
        source.delete()
    return 1


def manifests(bucket, owner='alice'):
    return [
        json.loads(b.download_as_bytes())
        for b in bucket.list_blobs(packs.owner_prefix(packs.INDEX_PREFIX, owner))
        if b.name.removeprefix(packs.owner_prefix(packs.INDEX_PREFIX, owner)).split('/', 1)[0]
        not in {'captures', 'links', 'deletions'}
    ]


def test_conversation_rewrite_resumes_after_pack_replaced(bucket):
    capture(bucket, data=b'one', conv='one')
    capture(bucket, data=b'two', conv='two')
    seed_existing_pack(bucket, 'alice', '2020-10-14')
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


def test_cross_owner_index_fails_closed(bucket):
    capture(bucket)
    seed_existing_pack(bucket, 'alice', '2020-10-14')
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
    seed_existing_pack(bucket, 'alice', '2020-10-14')
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
    seed_existing_pack(bucket, 'alice', '2020-10-14')
    assert {e['conversation_ranges'][0]['conversation_id'] for e in manifests(bucket)[0]['entries']} == {'merged'}


def test_merge_retarget_resumes_interrupted_manifest_publication(bucket):
    capture(bucket)
    seed_existing_pack(bucket, 'alice', '2020-10-14')
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
    seed_existing_pack(bucket, 'alice', '2020-10-13')
    unaffected = manifests(bucket)[0]['pack']
    capture(bucket, conv='erase', data=b'erase')
    seed_existing_pack(bucket, 'alice', '2020-10-14')
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
    seed_existing_pack(bucket, 'alice', '2020-10-14')
    name = manifests(bucket)[0]['pack']
    bucket.blob(name).upload_from_string(bucket.blob(name).download_as_bytes())
    with pytest.raises(RuntimeError, match='changed pack generation'):
        packs.delete_conversation(bucket, 'alice', 'erase')
