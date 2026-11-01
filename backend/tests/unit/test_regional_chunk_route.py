"""Pusher PCM chunk batches ramp to BUCKET_AUDIO_DERIVED behind their own percent.

Live PCM chunks are a rendition of the canonical raw-live packs (which stay in the
multi-region bucket). New batches for a regional-cohort owner go to the regional
bucket; nothing existing moves, and every chunk path stays readable, collision-
checked and deletable in either bucket.
"""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from google.cloud.exceptions import NotFound

from config import audio_archive
from utils.other import audio_chunk_replay
from utils.other import storage

UID = 'owner'
PRIVATE = storage.private_cloud_sync_bucket
DERIVED = 'derived-uc1'


class _Blob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.metadata = bucket, name, None

    def exists(self):
        return self.name in self.bucket.objects

    def download_as_bytes(self, **kwargs):
        if self.name not in self.bucket.objects:
            raise NotFound('missing')
        return self.bucket.objects[self.name]

    def delete(self, **kwargs):
        self.bucket.objects.pop(self.name)
        self.bucket.deleted.append(self.name)

    def open(self, mode, **kwargs):
        blob = self

        class _Writer:
            def __init__(self):
                self.parts = []

            def __enter__(self):
                return self

            def write(self, data):
                self.parts.append(data)

            def __exit__(self, *exc):
                blob.bucket.objects[blob.name] = b''.join(self.parts)
                blob.bucket.writes.append((blob.name, kwargs.get('if_generation_match')))

        return _Writer()


class _Bucket:
    def __init__(self, name, objects=None):
        self.name, self.objects, self.writes, self.deleted = name, dict(objects or {}), [], []

    def blob(self, name):
        return _Blob(self, name)

    def list_blobs(self, prefix=''):
        return [_Blob(self, name) for name in list(self.objects) if name.startswith(prefix)]


@pytest.fixture
def buckets(monkeypatch):
    by_name = {PRIVATE: _Bucket(PRIVATE), DERIVED: _Bucket(DERIVED)}
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: by_name[name]))
    monkeypatch.setattr(storage, 'owner_storage_write_gate', lambda uid, bucket=None: nullcontext())
    monkeypatch.setattr(storage, '_archive_pusher_capture', lambda *args, **kwargs: None)
    for name in (
        'AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED',
        'AUDIO_ARCHIVE_REGIONAL_CHUNKS_PERCENT',
        'AUDIO_ARCHIVE_STOP_PCM_ENABLED',
        'AUDIO_ARCHIVE_UID_ALLOWLIST',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', DERIVED)
    return by_name


def _admit(monkeypatch, percent='100'):
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CHUNKS_PERCENT', percent)


def _chunks(data=b'\x01\x02' * 8, start=100.0):
    return [
        {'data': data, 'timestamp': start, 'span': {'start': start, 'samples': len(data) // 2, 'sample_rate': 16000}}
    ]


def _upload(chunks):
    return storage.upload_audio_chunks_batch(
        chunks, UID, 'conv', data_protection_level='standard', sample_rate=16000, reconcile_prefix=False
    )


@pytest.mark.parametrize(
    'enabled,percent,bucket_env,expected',
    [
        (None, None, DERIVED, PRIVATE),  # defaults: percent 0
        ('true', None, DERIVED, PRIVATE),  # cache enable alone never moves chunks
        ('false', '100', DERIVED, PRIVATE),  # REGIONAL_CACHE kill switch wins
        ('true', '100', '', PRIVATE),  # no destination configured
        ('true', 'bogus', DERIVED, PRIVATE),  # malformed means 0
        ('true', '150', DERIVED, PRIVATE),  # out of range means 0
        ('true', '100', DERIVED, DERIVED),
    ],
)
def test_regional_chunk_bucket_is_dark_unless_every_knob_admits(monkeypatch, enabled, percent, bucket_env, expected):
    for name, value in (
        ('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', enabled),
        ('AUDIO_ARCHIVE_REGIONAL_CHUNKS_PERCENT', percent),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', bucket_env)
    monkeypatch.delenv('AUDIO_ARCHIVE_UID_ALLOWLIST', raising=False)
    assert audio_archive.regional_chunk_bucket(UID, PRIVATE) == expected


def test_regional_cache_percent_does_not_admit_chunks(monkeypatch):
    # Step 1 (derived caches/staging) and step 2 (chunks) ramp independently.
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CACHE_PERCENT', '100')
    monkeypatch.delenv('AUDIO_ARCHIVE_REGIONAL_CHUNKS_PERCENT', raising=False)
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', DERIVED)
    assert audio_archive.regional_bucket(UID, PRIVATE) == DERIVED
    assert audio_archive.regional_chunk_bucket(UID, PRIVATE) == PRIVATE


def test_non_admitted_owner_writes_the_private_bucket(buckets):
    paths = _upload(_chunks())
    assert buckets[PRIVATE].writes == [(paths[0], 0)]
    assert buckets[DERIVED].writes == []


def test_admitted_owner_writes_the_derived_bucket_create_only(buckets, monkeypatch):
    _admit(monkeypatch)
    paths = _upload(_chunks())
    assert buckets[DERIVED].writes == [(paths[0], 0)]
    assert buckets[PRIVATE].writes == []


def test_identical_batch_already_in_the_other_bucket_is_not_rewritten(buckets, monkeypatch):
    data = b'\x01\x02' * 8
    path = 'chunks/owner/conv/100.000.batch.bin'
    buckets[PRIVATE].objects[path] = data
    _admit(monkeypatch)

    assert _upload(_chunks(data)) == [path]
    assert buckets[DERIVED].writes == [] and buckets[PRIVATE].writes == []


def test_different_bytes_under_the_same_key_in_the_other_bucket_conflict(buckets, monkeypatch):
    path = 'chunks/owner/conv/100.000.batch.bin'
    buckets[DERIVED].objects[path] = b'\x09\x09' * 8
    # Rolled back to 0: the owner writes the private bucket again, but the
    # derived bucket still holds that key.
    with pytest.raises(storage.AudioChunkContentConflict):
        _upload(_chunks())
    assert buckets[PRIVATE].writes == []


def test_identical_copy_in_one_bucket_never_hides_a_divergent_copy_in_the_other(buckets):
    # Rolled back to 0: the private copy matches this retry, but the derived copy (which
    # the listing prefers) differs. Accepting the upload would let readers serve other bytes.
    data = b'\x01\x02' * 8
    path = 'chunks/owner/conv/100.000.batch.bin'
    buckets[PRIVATE].objects[path] = data
    buckets[DERIVED].objects[path] = b'\x09\x09' * 8
    with pytest.raises(storage.AudioChunkContentConflict):
        _upload(_chunks(data))
    assert buckets[PRIVATE].writes == [] and buckets[DERIVED].writes == []


def test_rollout_allowlist_member_is_not_admitted_at_percent_zero(monkeypatch):
    # Percent 0 is the rollback: allowlist membership for the other archive phases must not
    # keep routing chunks regional.
    monkeypatch.setattr(audio_archive, 'in_rollout_cohort', lambda uid, name: True)
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', 'true')
    monkeypatch.setenv('AUDIO_ARCHIVE_REGIONAL_CHUNKS_PERCENT', '0')
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', DERIVED)
    assert audio_archive.regional_bucket(UID, PRIVATE) == DERIVED  # step 1 allowlist canary unchanged
    assert audio_archive.regional_chunk_bucket(UID, PRIVATE) == PRIVATE


def test_delete_audio_chunks_sweeps_both_buckets(buckets):
    for name in (PRIVATE, DERIVED):
        buckets[name].objects['chunks/owner/conv/100.000-101.000.batch.bin'] = b'x'
        buckets[name].objects['chunks/owner/conv/200.000.bin'] = b'y'
    storage.delete_audio_chunks(UID, 'conv', [100.0, 200.0])
    assert buckets[PRIVATE].objects == {} and buckets[DERIVED].objects == {}


def test_delete_audio_chunks_without_derived_bucket_touches_only_private(buckets, monkeypatch):
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', '')
    buckets[DERIVED].objects['chunks/owner/conv/200.000.bin'] = b'y'
    buckets[PRIVATE].objects['chunks/owner/conv/200.000.bin'] = b'y'
    storage.delete_audio_chunks(UID, 'conv', [200.0])
    assert buckets[PRIVATE].objects == {}
    assert buckets[DERIVED].deleted == []


def test_replay_reconcile_reads_a_listed_derived_generation_from_its_bucket():
    pcm = b'\x01\x02' * 8
    path = 'chunks/owner/conv/100.000.batch.bin'
    reads = []

    class _Source:
        def __init__(self, name):
            self.name = name

        def blob(self, blob_path):
            source = self

            class _B:
                def download_as_bytes(self, **kwargs):
                    reads.append(source.name)
                    if source.name != DERIVED:
                        raise NotFound('only in derived')
                    return pcm

            return _B()

    listed = [
        {
            'path': path,
            'size': len(pcm),
            'generation': 7,
            'bucket': DERIVED,
            'span': {'start': 100.0, 'samples': len(pcm) // 2, 'sample_rate': 16000},
        }
    ]
    verified, proven = audio_chunk_replay.reconcile_committed_prefix(
        UID,
        'conv',
        100.0,
        pcm,
        16000,
        require_spans=True,
        bucket=_Source(PRIVATE),
        list_chunks=lambda *args, **kwargs: listed,
        bucket_for=_Source,
    )
    assert reads == [DERIVED]
    assert verified == len(pcm) and proven == [path]
