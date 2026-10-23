"""Sync-bridge audio copies are idempotent per object and back off on GCS 429.

finish_sync_bridges re-copies a donor's whole chunk set on every late append to it, and
concurrent fresh jobs for one conversation did the same copy at the same time. GCS allows
about one mutation per second per object name, so the repeats surfaced as 429 on
CloneObject and failed the job's finalize. The bridge now skips a destination that already
holds the same bytes, writes only under a generation precondition, and retries 429 with
bounded backoff.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import PreconditionFailed, TooManyRequests
from prometheus_client import REGISTRY

from utils.conversations import merge_conversations as merge

UID = 'u1'
DONOR_CHUNKS = {'chunks/u1/donor/100.0.bin': ('crc-a', 10), 'chunks/u1/donor/200.0.bin': ('crc-b', 20)}


class _Bucket:
    """In-memory bucket with GCS generation-precondition semantics."""

    def __init__(self, objects=None, rate_limited=0):
        self.objects = dict(objects or {})  # name -> SimpleNamespace(crc32c, size, generation)
        self.rate_limited = rate_limited
        self.copies = []
        self._generation = 100

    def blob(self, name):
        return SimpleNamespace(name=name)

    def list_blobs(self, prefix=''):
        return [
            SimpleNamespace(name=name, **vars(obj)) for name, obj in self.objects.items() if name.startswith(prefix)
        ]

    def get_blob(self, name, retry='default'):
        assert retry is None
        obj = self.objects.get(name)
        return None if obj is None else SimpleNamespace(name=name, **vars(obj))

    def copy_blob(self, source_blob, _bucket, new_path, if_generation_match=None, retry='default'):
        if self.rate_limited:
            self.rate_limited -= 1
            raise TooManyRequests('per-object mutation rate exceeded')
        current = self.objects.get(new_path)
        if if_generation_match is not None:
            assert retry is None
            if (current.generation if current else 0) != if_generation_match:
                raise PreconditionFailed('generation mismatch')
        crc32c, size = DONOR_CHUNKS[source_blob.name]
        self._generation += 1
        self.objects[new_path] = SimpleNamespace(crc32c=crc32c, size=size, generation=self._generation)
        self.copies.append((new_path, if_generation_match))


@pytest.fixture
def install(monkeypatch):
    def _install(bucket):
        monkeypatch.setattr(merge, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: bucket))
        monkeypatch.setattr(merge, 'owner_storage_write_gate', lambda uid, bucket=None: nullcontext())
        monkeypatch.setattr(merge.conversations_db, 'create_audio_files_from_chunks', lambda uid, cid: ['audio'])
        sleeps = []
        monkeypatch.setattr(merge.time, 'sleep', sleeps.append)

        def list_chunks(uid, cid, **kwargs):
            assert kwargs == {'require_archive': True, 'source_identity': True}
            return [
                {'path': path, 'crc32c': crc32c, 'size': size}
                for path, (crc32c, size) in DONOR_CHUNKS.items()
                if path.startswith(f'chunks/{uid}/{cid}/')
            ]

        monkeypatch.setattr(merge, 'list_audio_chunks', list_chunks)
        return sleeps

    return _install


def _copies(outcome):
    return REGISTRY.get_sample_value('omi_sync_bridge_audio_copy_total', {'outcome': outcome}) or 0.0


def _dest(name):
    return name.replace('/donor/', '/target/')


def test_first_bridge_creates_every_object_create_only(install):
    bucket = _Bucket()
    install(bucket)

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert sorted(bucket.copies) == [(_dest(path), 0) for path in sorted(DONOR_CHUNKS)]


def test_rerun_bridge_skips_objects_that_already_hold_the_same_bytes(install):
    bucket = _Bucket()
    install(bucket)
    merge.copy_sync_bridge_audio(UID, 'donor', 'target')
    skipped = _copies('skipped')

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert len(bucket.copies) == len(DONOR_CHUNKS)
    assert _copies('skipped') == skipped + len(DONOR_CHUNKS)


def test_mismatched_destination_is_replaced_at_its_listed_generation(install):
    stale = _dest('chunks/u1/donor/100.0.bin')
    bucket = _Bucket({stale: SimpleNamespace(crc32c='old', size=10, generation=7)})
    install(bucket)

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert (stale, 7) in bucket.copies
    assert bucket.objects[stale].crc32c == 'crc-a'


def test_rate_limit_backs_off_with_jitter_then_succeeds(install):
    bucket = _Bucket(rate_limited=2)
    sleeps = install(bucket)
    limited = _copies('rate_limited')

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert len(bucket.copies) == len(DONOR_CHUNKS)
    assert _copies('rate_limited') == limited + 2
    assert len(sleeps) == 2 and 0.5 <= sleeps[0] <= 1.0 and 1.0 <= sleeps[1] <= 2.0


def test_rate_limit_exhaustion_still_fails_the_copy(install):
    bucket = _Bucket(rate_limited=merge._COPY_RATE_LIMIT_ATTEMPTS)
    sleeps = install(bucket)

    with pytest.raises(TooManyRequests):
        merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert len(sleeps) == merge._COPY_RATE_LIMIT_ATTEMPTS - 1
    assert bucket.copies == []


def test_concurrent_bridge_that_already_wrote_the_same_bytes_wins_quietly(install, monkeypatch):
    bucket = _Bucket()
    install(bucket)
    racer = _dest('chunks/u1/donor/100.0.bin')
    real_list = bucket.list_blobs

    def list_then_race(prefix=''):
        listed = real_list(prefix)
        # Another job's bridge lands between this job's listing and its copy.
        bucket.objects[racer] = SimpleNamespace(crc32c='crc-a', size=10, generation=55)
        return listed

    monkeypatch.setattr(bucket, 'list_blobs', list_then_race)
    raced = _copies('raced')

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert bucket.objects[racer].generation == 55
    assert _copies('raced') == raced + 1


def test_concurrent_writer_with_different_bytes_still_fails(install, monkeypatch):
    bucket = _Bucket()
    install(bucket)
    racer = _dest('chunks/u1/donor/100.0.bin')
    real_list = bucket.list_blobs

    def list_then_race(prefix=''):
        listed = real_list(prefix)
        bucket.objects[racer] = SimpleNamespace(crc32c='other', size=10, generation=55)
        return listed

    monkeypatch.setattr(bucket, 'list_blobs', list_then_race)

    with pytest.raises(PreconditionFailed):
        merge.copy_sync_bridge_audio(UID, 'donor', 'target')


def test_derived_listing_checksum_never_certifies_the_private_copy(install, monkeypatch):
    # list_audio_chunks keeps the BUCKET_AUDIO_DERIVED entry for a path in both buckets,
    # but copy_blob reads the private object. Compare against what is actually copied.
    source = 'chunks/u1/donor/100.0.bin'
    dest = _dest(source)
    bucket = _Bucket(
        {
            source: SimpleNamespace(crc32c='crc-a', size=10, generation=1),
            dest: SimpleNamespace(crc32c='derived-crc', size=10, generation=9),
        }
    )
    install(bucket)
    monkeypatch.setattr(
        merge,
        'list_audio_chunks',
        lambda uid, cid, **kwargs: [{'path': source, 'crc32c': 'derived-crc', 'size': 10, 'bucket': 'derived'}],
    )

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert bucket.copies == [(dest, 9)]
    assert bucket.objects[dest].crc32c == 'crc-a'
    # A second bridge now sees the private bytes in place and skips.
    merge.copy_sync_bridge_audio(UID, 'donor', 'target')
    assert len(bucket.copies) == 1


def test_unchecksummed_pack_raced_by_a_same_size_copy_is_not_a_failure(install, monkeypatch):
    bucket = _Bucket()
    install(bucket)
    racer = _dest('chunks/u1/donor/100.0.bin')
    real_list = bucket.list_blobs
    monkeypatch.setattr(
        merge,
        'list_audio_chunks',
        lambda uid, cid, **kwargs: [{'path': 'chunks/u1/donor/100.0.bin', 'crc32c': None, 'size': 10}],
    )

    def list_then_race(prefix=''):
        listed = real_list(prefix)
        bucket.objects[racer] = SimpleNamespace(crc32c='crc-a', size=10, generation=55)
        return listed

    monkeypatch.setattr(bucket, 'list_blobs', list_then_race)

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert bucket.objects[racer].generation == 55


def test_unknown_source_checksum_is_copied_not_skipped(install, monkeypatch):
    dest = _dest('chunks/u1/donor/100.0.bin')
    bucket = _Bucket({dest: SimpleNamespace(crc32c=None, size=10, generation=3)})
    install(bucket)
    monkeypatch.setattr(
        merge,
        'list_audio_chunks',
        lambda uid, cid, **kwargs: [{'path': 'chunks/u1/donor/100.0.bin', 'crc32c': None, 'size': 10}],
    )

    merge.copy_sync_bridge_audio(UID, 'donor', 'target')

    assert bucket.copies == [(dest, 3)]


def test_user_merge_copy_keeps_its_unconditional_shape_but_backs_off(monkeypatch):
    calls = []

    class _MergeBucket:
        rate_limited = 1

        def blob(self, name):
            return SimpleNamespace(name=name)

        def copy_blob(self, source_blob, bucket, new_path):
            if self.rate_limited:
                self.rate_limited -= 1
                raise TooManyRequests('429')
            calls.append(new_path)

    monkeypatch.setattr(merge, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: _MergeBucket()))
    monkeypatch.setattr(merge, 'owner_storage_write_gate', lambda uid, bucket=None: nullcontext())
    monkeypatch.setattr(merge.conversations_db, 'create_audio_files_from_chunks', lambda uid, cid: ['audio'])
    monkeypatch.setattr(merge.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(merge, 'list_audio_chunks', lambda uid, cid, **kwargs: [{'path': f'chunks/u1/{cid}/1.bin'}])

    copied, limited = _copies('copied'), _copies('rate_limited')
    assert merge._copy_audio_chunks_for_merge(UID, [{'id': 'a'}], 'merged') == ['audio']
    assert calls == ['chunks/u1/merged/1.bin']
    # User merges are not sync bridges and stay out of the bridge copy metric.
    assert (_copies('copied'), _copies('rate_limited')) == (copied, limited)
