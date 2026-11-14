"""Closed-record gap fill: gates, clip, create-only custody, pusher race, marker, logs."""

import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import os
import threading
import time
from types import SimpleNamespace
import wave

import pytest
from google.api_core.exceptions import PreconditionFailed

from config.policy import BatchUnitPolicy
from database import sync_record_wait_cache
from database.audio_chunk_metadata import audio_chunk_entry
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils import encryption
from utils.batch_pipeline import live, live_upload, record_gap_fill, record_retained_ack
from utils.batch_pipeline.audio import audio_unit
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.batch_pipeline.source_audio import MAGIC, decode_source, materialize
from utils.other import storage

UID, CID = 'synthetic-owner', 'synthetic-conversation'
REAL_SOURCE_UNITS = record_gap_fill.source_units
RATE = 16000
NOW = 10_000.0
PRIMARY = storage.private_cloud_sync_bucket


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name, self.metadata = bucket, name, None

    def upload_from_string(self, payload, content_type=None, if_generation_match=None, timeout=None, retry=None):
        self.bucket.calls.append({'timeout': timeout, 'retry': retry})
        if if_generation_match == 0 and self.name in self.bucket.objects:
            raise PreconditionFailed('exists')
        self.bucket.generation += 1
        self.bucket.objects[self.name] = {
            'data': bytes(payload),
            'metadata': dict(self.metadata or {}),
            'generation': self.bucket.generation,
        }


class FakeBucket:
    def __init__(self):
        self.name = PRIMARY
        self.objects = {}
        self.generation = 0
        self.calls = []

    def blob(self, name, generation=None):
        return FakeBlob(self, name)

    def put(self, path, data, metadata=None):
        self.generation += 1
        self.objects[path] = {'data': data, 'metadata': metadata or {}, 'generation': self.generation}

    def listing(self):
        # GCS lists lexicographically; the walk's sort by start is stable.
        entries = []
        for path, value in sorted(self.objects.items()):
            blob = SimpleNamespace(
                name=path,
                size=len(value['data']),
                generation=value['generation'],
                metadata=value['metadata'],
                bucket=SimpleNamespace(name=PRIMARY),
            )
            entry = audio_chunk_entry(blob, source_identity=False, primary_bucket=PRIMARY)
            if entry is not None:
                entries.append(entry)
        return sorted(entries, key=lambda item: item['timestamp'])


def tone(seconds, value):
    return int(value).to_bytes(2, 'little', signed=True) * round(seconds * RATE)


def ramp(seconds, offset=0):
    return b''.join(((offset + i) % 30000).to_bytes(2, 'little', signed=True) for i in range(round(seconds * RATE)))


def closed_row(**overrides):
    row = {
        'record_lane_owner': live.OWNER,
        'status': 'completed',
        'record_audio_closed': True,
        'private_cloud_sync_enabled': True,
        'source': 'omi',
        'client_device_id': 'synthetic-device',
        'started_at': datetime.fromtimestamp(100, timezone.utc),
        'finished_at': datetime.fromtimestamp(110, timezone.utc),
        'updated_at': datetime.fromtimestamp(200, timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('RECORD_GAP_FILL', 'on')
    monkeypatch.setenv('RECORD_GAP_FILL_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    bucket = FakeBucket()
    markers = set()
    wal = {'units': []}

    def claim(record, wal_key, ttl):
        if (record, wal_key) in markers:
            return False
        markers.add((record, wal_key))
        return True

    def read(client, ref, uid, cid, allowed, key, **kwargs):
        stored = bucket.objects[ref['path']]
        return decode_source(stored['data'], {**ref, 'metadata': stored['metadata']}, key)

    monkeypatch.setattr(record_gap_fill, 'claim_gap_fill_marker', claim)
    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', lambda *a, **kw: bucket.listing())
    monkeypatch.setattr(record_gap_fill, 'source_units', lambda paths: iter(wal['units']))
    monkeypatch.setattr(live, 'read_reference', read)
    store = MemoryStore()
    content, segment = live.record_identity(UID, CID)
    store.rows['jobs', segment] = {
        'segment_id': segment,
        'state': 'record_pending',
        'record_content_id': content,
        'owner_id': UID,
        'conversation_id': CID,
    }
    return SimpleNamespace(bucket=bucket, markers=markers, wal=wal, store=store, segment=segment)


def fill(world, row=None, **kwargs):
    options = {
        'uid': UID,
        'conversation_id': CID,
        'row': closed_row() if row is None else row,
        'paths': ['synthetic-wal.bin'],
        'wal_content_id': 'synthetic-content',
        'store': world.store,
        'now': NOW,
        'storage_client': object(),
        'bucket': world.bucket,
        'protection_level': 'standard',
    }
    options.update(kwargs)
    return record_gap_fill.fill_closed_record_gap(**options)


def fills(world):
    return {
        path: value for path, value in world.bucket.objects.items() if value['metadata'].get('source') == 'phone_wal'
    }


def admitted_units(world):
    """Admission's own retained walk over everything now in the bucket."""
    chunks = world.bucket.listing()
    return chunks, list(live.retained_record_units(UID, CID, chunks, None, encryption.derive_key(UID)))


def materialized(world, unit):
    start, duration, refs = unit
    item = SimpleNamespace(owner_id=UID, conversation_id=CID, capture_at=start, duration_seconds=duration)
    body = (
        MAGIC
        + json.dumps(
            {'owner_id': UID, 'conversation_id': CID, 'capture_at': start, 'references': refs, 'context': {}}
        ).encode()
    )

    def fetch(ref):
        stored = world.bucket.objects[ref['path']]
        return decode_source(stored['data'], {**ref, 'metadata': stored['metadata']}, encryption.derive_key(UID))

    with wave.open(io.BytesIO(materialize(body, item, fetch)), 'rb') as stream:
        return stream.readframes(stream.getnframes())


def test_switch_off_or_zero_cohort_is_a_silent_no_op(world, monkeypatch, caplog):
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    with caplog.at_level(logging.INFO, logger=record_gap_fill.__name__):
        monkeypatch.setenv('RECORD_GAP_FILL', 'off')
        assert fill(world) is None
        monkeypatch.setenv('RECORD_GAP_FILL', 'on')
        monkeypatch.setenv('RECORD_GAP_FILL_PERCENT', '0')
        assert fill(world) is None
    assert world.bucket.objects == {} and world.markers == set()
    assert not [r for r in caplog.records if 'sync_record_gap_fill' in r.getMessage()]


@pytest.mark.parametrize(
    'overrides,expected',
    [
        ({'status': 'in_progress'}, 'skipped_gate'),
        ({'record_audio_closed': False}, 'skipped_gate'),
        ({'record_upload_sessions': {'live-producer': True}}, 'skipped_gate'),
        ({'record_upload_failed': True}, 'skipped_gate'),
        ({'record_audio_partial': {'mark': 1}}, 'skipped_gate'),
        ({'record_lane_owner': 'legacy_final_pass_v1'}, 'skipped_gate'),
        ({'deleted': True}, 'skipped_gate'),
        ({'private_cloud_sync_enabled': False}, 'skipped_gate'),
        ({'finished_at': None}, 'skipped_gate'),
        # (a) closed for at least five minutes, by finish and by last row write.
        ({'finished_at': datetime.fromtimestamp(NOW - 60, timezone.utc), 'updated_at': None}, 'skipped_recent'),
        ({'updated_at': datetime.fromtimestamp(NOW - 299, timezone.utc)}, 'skipped_recent'),
    ],
)
def test_each_gate_refuses_without_writing(world, overrides, expected):
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world, closed_row(**overrides)) == expected
    assert world.bucket.objects == {}


def test_privacy_block_refuses_without_writing(world, monkeypatch):
    world.wal['units'] = [audio_unit(100.0, ramp(10))]

    def blocked(body):
        raise BatchPrivacyBlocked('synthetic block')

    monkeypatch.setattr(world.store, 'run', blocked)
    assert fill(world) == 'skipped_gate'
    assert world.bucket.objects == {}


@pytest.mark.parametrize(
    'job',
    [None, {'state': 'admitted'}, {'state': 'record_pending', 'record_content_id': 'other'}],
)
def test_record_without_a_pending_obligation_is_never_filled(world, job):
    # Registration refused or never ran (for example server-batch-only with no
    # server audio): the drain has nothing to admit, so audio would not help.
    content, segment = live.record_identity(UID, CID)
    if job is None:
        world.store.rows.pop(('jobs', segment))
    else:
        world.store.rows['jobs', segment] = {
            'owner_id': UID,
            'conversation_id': CID,
            'record_content_id': content,
            **job,
        }
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world) == 'skipped_no_pending'
    assert world.bucket.objects == {} and world.markers == set()


def test_privacy_is_checked_before_any_retained_read(world, monkeypatch):
    world.wal['units'] = [audio_unit(100.0, ramp(10))]

    def blocked(body):
        raise BatchPrivacyBlocked('synthetic block')

    def never(*a, **kw):
        raise AssertionError('retained audio listed past a privacy block')

    monkeypatch.setattr(world.store, 'run', blocked)
    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', never)
    assert fill(world) == 'skipped_gate'
    assert world.markers == set()


def test_no_gap_when_retained_audio_reaches_finish(world):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(10, 7))
    world.wal['units'] = [audio_unit(100.0, ramp(12))]
    assert fill(world) == 'skipped_no_gap'
    assert list(world.bucket.objects) == [f'chunks/{UID}/{CID}/100.000.bin']


def test_retained_refusal_is_left_to_admission(world):
    # Divergent objects claiming the same instant without trimming cannot be
    # ordered; admission keeps refusing for that reason, so nothing is added.
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(2, 1))
    world.bucket.put(f'chunks/{UID}/{CID}/99.999.bin', tone(0.5, 2))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'false')
        assert fill(world) == 'skipped_retained'
    assert not fills(world)


def test_tail_clip_writes_exactly_the_missing_span_and_admission_passes(world):
    retained = tone(5, 7)
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', retained)
    wal_pcm = ramp(20)  # 100..120 on the phone clock
    world.wal['units'] = [audio_unit(100.0, wal_pcm)]
    with pytest.raises(ValueError, match='tail not durable'):
        validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])

    assert fill(world) == 'written'

    written = fills(world)
    assert list(written) == [f'chunks/{UID}/{CID}/105.000000.bin']
    stored = written[f'chunks/{UID}/{CID}/105.000000.bin']
    # Nothing before the retained end, nothing past finish + 1 s.
    assert stored['data'] == wal_pcm[5 * RATE * 2 : 11 * RATE * 2]
    assert stored['metadata']['source'] == 'phone_wal'
    assert stored['metadata']['rendition'] == 'gap-fill-v1'
    assert stored['metadata']['record'] == live.record_identity(UID, CID)[0][:16]
    assert stored['metadata']['v2_start'] == repr(105.0)
    # The retained object is untouched.
    assert world.bucket.objects[f'chunks/{UID}/{CID}/100.000.bin']['data'] == retained

    chunks, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])
    assert len(units) == 1 and units[0][:2] == (100.0, 11.0)
    assert materialized(world, units[0]) == retained + wal_pcm[5 * RATE * 2 : 11 * RATE * 2]


def test_empty_retained_set_fills_from_capture_start_and_wal_proves_coverage(world, monkeypatch):
    wal_pcm = ramp(14)  # 98..112: two seconds before the capture's start
    world.wal['units'] = [audio_unit(98.0, wal_pcm)]
    assert fill(world) == 'written'
    assert list(fills(world)) == [f'chunks/{UID}/{CID}/99.000000.bin']

    _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])
    # The next upload of the same WAL clipped to the admitted record proves
    # byte-exact coverage through the unchanged ``_covered`` check.
    start, duration, _ = units[0]
    jobs = [
        {
            'segment_id': 'synthetic-segment',
            'owner_id': UID,
            'capture_at': start,
            'audio_uri': 'record:pending',
            'duration_seconds': duration,
            'priority': 1,
        }
    ]
    artifacts = SimpleNamespace(fetch_audio=lambda item: audio_unit(start, materialized(world, units[0])).wav)
    clipped = [audio_unit(99.0, wal_pcm[RATE * 2 : 13 * RATE * 2])]
    monkeypatch.setattr(live_upload, 'decode_units', lambda paths: iter(clipped))
    assert live_upload._covered(['synthetic-wal.bin'], jobs, artifacts) is True
    # A WAL that differs from what was written is never released.
    other = [audio_unit(99.0, tone(12, 3))]
    monkeypatch.setattr(live_upload, 'decode_units', lambda paths: iter(other))
    assert live_upload._covered(['synthetic-wal.bin'], jobs, artifacts) is False


def test_a_wal_that_skips_ahead_of_held_audio_writes_nothing(world):
    # Newest-first uploads: the last minutes arrive before the earlier ones.
    # Writing them would let admission pass on the final end with a hole.
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(107.0, ramp(5))]
    assert fill(world) == 'skipped_not_contiguous'
    assert not fills(world)
    world.bucket.objects.clear()
    world.wal['units'] = [audio_unit(103.0, ramp(9))]
    assert fill(world, wal_content_id='later-wal') == 'skipped_not_contiguous'
    assert not fills(world)


def test_fill_stops_at_a_hole_inside_the_wal_and_resumes_on_a_later_upload(world):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    early, late = ramp(2), ramp(3, offset=7)
    world.wal['units'] = [audio_unit(105.0, early), audio_unit(108.0, late)]
    assert fill(world) == 'written'
    assert list(fills(world)) == [f'chunks/{UID}/{CID}/105.000000.bin']
    with pytest.raises(ValueError, match='tail not durable'):
        validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])
    # The phone's next WAL fills from the new held end.
    world.wal['units'] = [audio_unit(107.0, ramp(4, offset=3))]
    assert fill(world, wal_content_id='next-wal') == 'written'
    _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])


def wal_file(tmp_path, capture, pcm):
    path = tmp_path / f'audio_omi_pcm16_16000_{capture}.bin'
    path.write_bytes(
        b''.join(len(pcm[i : i + 320]).to_bytes(4, 'little') + pcm[i : i + 320] for i in range(0, len(pcm), 320))
    )
    return str(path)


def test_real_decoder_keeps_a_hole_between_wal_files(world, tmp_path, monkeypatch):
    # decode_units joins files up to 30 s apart with silence; the fill must
    # still see the 107..108 hole and stop there, not admit across it.
    monkeypatch.setattr(record_gap_fill, 'source_units', REAL_SOURCE_UNITS)
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    early, late = ramp(2), ramp(3, offset=7)
    paths = [wal_file(tmp_path, 108, late), wal_file(tmp_path, 105, early)]
    assert fill(world, paths=paths) == 'written'
    written = fills(world)
    assert list(written) == [f'chunks/{UID}/{CID}/105.000000.bin']
    assert written[f'chunks/{UID}/{CID}/105.000000.bin']['data'] == early
    with pytest.raises(ValueError, match='tail not durable'):
        validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])
    # A later upload carrying the real 107..108 file completes the record.
    later = [wal_file(tmp_path, 107, ramp(1, offset=3)), wal_file(tmp_path, 108, late)]
    assert fill(world, paths=later, wal_content_id='next-wal') == 'written'
    validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])


def test_real_decoder_fills_contiguous_wal_files(world, tmp_path, monkeypatch):
    monkeypatch.setattr(record_gap_fill, 'source_units', REAL_SOURCE_UNITS)
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    paths = [wal_file(tmp_path, 105, ramp(2)), wal_file(tmp_path, 107, ramp(4, offset=5))]
    assert fill(world, paths=paths) == 'written'
    validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])


def test_overlapping_wal_units_in_one_upload_never_overlap_each_other(world):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    first, second = ramp(5), ramp(6, offset=11)  # 105..110 and 108..114
    world.wal['units'] = [audio_unit(105.0, first), audio_unit(108.0, second)]
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'false')
        assert fill(world) == 'written'
        written = fills(world)
        assert sorted(written) == [f'chunks/{UID}/{CID}/105.000000.bin', f'chunks/{UID}/{CID}/110.000000.bin']
        assert written[f'chunks/{UID}/{CID}/110.000000.bin']['data'] == second[2 * RATE * 2 : 3 * RATE * 2]
        _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])


def test_empty_retained_set_without_a_start_is_never_filled(world):
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world, closed_row(started_at=None)) == 'skipped_gate'
    assert not fills(world)


def test_enhanced_protection_writes_an_encrypted_object_admission_decrypts(world):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    wal_pcm = ramp(12)
    world.wal['units'] = [audio_unit(100.0, wal_pcm)]
    assert fill(world, protection_level='enhanced') == 'written'
    path = f'chunks/{UID}/{CID}/105.000000.enc'
    assert list(fills(world)) == [path]
    assert world.bucket.objects[path]['data'] != wal_pcm[5 * RATE * 2 : 11 * RATE * 2]
    _, units = admitted_units(world)
    assert materialized(world, units[0])[5 * RATE * 2 :] == wal_pcm[5 * RATE * 2 : 11 * RATE * 2]


def test_long_gap_splits_into_bounded_pieces(world, monkeypatch):
    monkeypatch.setattr(record_gap_fill, 'PIECE_SECONDS', 4)
    wal_pcm = ramp(12)
    world.wal['units'] = [audio_unit(100.0, wal_pcm)]
    assert fill(world) == 'written'
    assert sorted(fills(world)) == [f'chunks/{UID}/{CID}/{ts:.6f}.bin' for ts in (100.0, 104.0, 108.0)]
    _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])
    assert materialized(world, units[0]) == wal_pcm[: 11 * RATE * 2]


def test_racing_writer_at_the_key_wins_and_is_never_overwritten(world, monkeypatch):
    # Another fill for the same record commits between this request's
    # retained listing (empty) and its create: that object owns the key and
    # this write is skipped, leaving its bytes and generation unchanged.
    path = f'chunks/{UID}/{CID}/100.000000.bin'
    racing = {}

    def listing_then_race(*a, **kw):
        listed = world.bucket.listing()
        world.bucket.put(path, tone(11, 9))
        racing.update(world.bucket.objects[path])
        return listed

    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', listing_then_race)
    world.wal['units'] = [audio_unit(100.0, ramp(11))]
    assert fill(world) == 'skipped_collision'
    assert world.bucket.objects == {path: racing}


def test_a_collision_with_a_shorter_object_stops_the_fill(world, monkeypatch):
    # A concurrent fill (another WAL) wins key 100 with only 100..101. Writing
    # on from 104 would let the tail pass with 101..104 missing.
    monkeypatch.setattr(record_gap_fill, 'PIECE_SECONDS', 4)
    path = f'chunks/{UID}/{CID}/100.000000.bin'

    def listing_then_race(*a, **kw):
        listed = world.bucket.listing()
        world.bucket.put(path, tone(1, 9))
        return listed

    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', listing_then_race)
    world.wal['units'] = [audio_unit(100.0, ramp(11))]
    assert fill(world) == 'skipped_collision'
    assert list(world.bucket.objects) == [path]
    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', lambda *a, **kw: world.bucket.listing())
    # The next upload resumes from the winner's real end.
    assert fill(world, wal_content_id='next-wal') == 'written'
    assert sorted(fills(world)) == [f'chunks/{UID}/{CID}/{ts:.6f}.bin' for ts in (101.0, 105.0, 109.0)]
    validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])


def test_pusher_commit_between_listing_and_create_is_untouched(world, monkeypatch):
    """(b) lead2's race: a pusher object lands after the retained listing.

    The fill was planned from the earlier listing, so its window overlaps the
    late pusher object. Keys never collide (3 vs 6 decimals): both objects
    exist afterwards, the pusher's bytes and generation are unchanged, and the
    walk gives the overlap to whichever object lists first.
    """
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    pusher_path = f'chunks/{UID}/{CID}/105.000.bin'
    late = {}

    def listing_then_pusher(*a, **kw):
        listed = world.bucket.listing()
        world.bucket.put(pusher_path, tone(3, 5))
        late.update(world.bucket.objects[pusher_path])
        return listed

    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', listing_then_pusher)
    wal_pcm = ramp(12)
    world.wal['units'] = [audio_unit(100.0, wal_pcm)]
    assert fill(world) == 'written'
    assert world.bucket.objects[pusher_path] == late
    assert list(fills(world)) == [f'chunks/{UID}/{CID}/105.000000.bin']
    _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])
    pcm = materialized(world, units[0])
    # The server's late object owns the frames it carries; the fill the rest.
    assert pcm[5 * RATE * 2 :] == tone(3, 5) + wal_pcm[8 * RATE * 2 : 11 * RATE * 2]


@pytest.mark.parametrize('started', [None, float('nan'), 'not-a-time'])
def test_empty_retained_set_needs_a_valid_start(world, started):
    world.wal['units'] = [audio_unit(0.0, ramp(120))]
    assert fill(world, closed_row(started_at=started)) == 'skipped_gate'
    assert not fills(world)


def test_create_only_writer_has_no_overwrite_fallback():
    bucket = FakeBucket()
    first = record_gap_fill.create_gap_fill_chunk(
        tone(1, 1), UID, CID, 105.0, 'standard', {'source': 'phone_wal'}, bucket=bucket
    )
    stored = dict(bucket.objects[first])
    again = record_gap_fill.create_gap_fill_chunk(
        tone(1, 2), UID, CID, 105.0, 'standard', {'source': 'phone_wal'}, bucket=bucket
    )
    assert again is None
    assert bucket.objects[first] == stored


@pytest.mark.parametrize('timestamp', [105.0, 105.123, 1730000000.5, 1730000000.123456])
def test_gap_fill_keys_never_equal_another_writers_keys(timestamp):
    """(b) Who wins: no other writer can ever address a gap-fill object."""
    gap = {record_gap_fill.gap_fill_chunk_path(UID, CID, timestamp, level) for level in ('standard', 'enhanced')}
    others = {f'chunks/{UID}/{CID}/{timestamp:.3f}.{ext}' for ext in ('opus', 'opus.enc', 'bin', 'enc')} | {
        f'chunks/{UID}/{CID}/{timestamp:.3f}-{timestamp + 1:.3f}.batch.{ext}' for ext in ('bin', 'enc')
    }
    assert not gap & others
    for path in gap:
        entry = audio_chunk_entry(
            SimpleNamespace(name=path, size=2, generation=1, metadata=None), source_identity=False, primary_bucket='b'
        )
        assert entry is not None and entry['timestamp'] == pytest.approx(timestamp, abs=5e-7)


@pytest.mark.parametrize('late_start', [107.0, 105.0])
def test_late_pusher_write_cannot_replace_or_corrupt_the_phone_chunk(world, monkeypatch, late_start):
    """(b) A late pusher write after a fill: a new object, the fill object intact.

    The pusher's create-or-update writer (``upload_audio_chunk``) addresses only
    3-decimal keys, so it creates its own object beside the fill and never
    replaces it. Admission's walk then gives each overlapping frame to the
    object listed first: a later-starting pusher object only adds frames past
    the fill's end; one starting at the same instant lists first
    (``105.000.opus`` < ``105.000000.bin``), so the server's own audio stays
    authoritative for the frames it carries and the fill supplies the rest.
    Either way the fill object's bytes and generation never change.
    """
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    wal_pcm = ramp(12)
    world.wal['units'] = [audio_unit(100.0, wal_pcm)]
    assert fill(world) == 'written'
    fill_path = f'chunks/{UID}/{CID}/105.000000.bin'
    fill_object = dict(world.bucket.objects[fill_path])

    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: world.bucket))
    monkeypatch.setattr(storage.audio_archive, 'admitted', lambda *a, **kw: False)
    monkeypatch.setattr(storage, 'encode_pcm_to_opus', lambda pcm: pcm)
    late = tone(3, 5)
    path = storage.upload_audio_chunk(late, UID, CID, late_start, data_protection_level='standard')
    assert path == f'chunks/{UID}/{CID}/{late_start:.3f}.opus' != fill_path
    # A retry of the late write with different bytes takes upload_audio_chunk's
    # overwrite fallback, which still only ever addresses its own key.
    assert storage.upload_audio_chunk(tone(3, 6), UID, CID, late_start, data_protection_level='standard') == path
    assert world.bucket.objects[fill_path] == fill_object

    # Decode the late object as PCM for the walk (the codec is not under test).
    opus = world.bucket.objects.pop(path)
    world.bucket.objects[path.replace('.opus', '.bin')] = {**opus, 'metadata': {}}
    _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])
    pcm = materialized(world, units[0])
    tail = wal_pcm[5 * RATE * 2 : 11 * RATE * 2]
    if late_start == 107.0:
        assert pcm[5 * RATE * 2 :] == tail
    else:
        assert pcm[5 * RATE * 2 :] == tone(3, 6) + tail[3 * RATE * 2 :]
    assert world.bucket.objects[fill_path] == fill_object


def test_marker_skips_a_repeat_and_redis_errors_fall_through(world, monkeypatch):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(100.0, ramp(12))]
    assert fill(world) == 'written'
    assert fill(world) == 'skipped_marker'
    world.markers.clear()
    # Past the marker, the create-only write makes a repeat harmless.
    before = dict(world.bucket.objects)
    assert fill(world) == 'skipped_no_gap'
    assert world.bucket.objects == before

    calls = []

    def broken(*args, **kwargs):
        calls.append((args, kwargs))
        raise ConnectionError('synthetic redis outage')

    fallbacks = []
    monkeypatch.setattr(sync_record_wait_cache, '_marker_client', lambda: SimpleNamespace(set=broken))
    monkeypatch.setattr(sync_record_wait_cache, 'record_fallback', lambda **kw: fallbacks.append(kw))
    assert sync_record_wait_cache.claim_gap_fill_marker('a' * 64, 'b' * 64, 600) is True
    assert calls and calls[0][1] == {'ex': 600, 'nx': True}
    assert fallbacks == [
        {
            'component': 'sync_dispatch',
            'from_mode': 'gap_fill_marker',
            'to_mode': 'create_only_write',
            'reason': 'unavailable',
            'outcome': 'degraded',
        }
    ]
    assert UID not in calls[0][0][0] and CID not in calls[0][0][0]


def test_log_and_counter_carry_only_hashed_keys(world, caplog):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(100.0, ramp(12))]
    before = record_gap_fill.GAP_FILL_TOTAL.labels(outcome='written')._value.get()
    with caplog.at_level(logging.INFO, logger=record_gap_fill.__name__):
        assert fill(world) == 'written'
    assert record_gap_fill.GAP_FILL_TOTAL.labels(outcome='written')._value.get() == before + 1
    messages = [r.getMessage() for r in caplog.records if 'sync_record_gap_fill' in r.getMessage()]
    assert messages == [
        'event=sync_record_gap_fill outcome=written record=%s seconds_bucket=0-10'
        % live.record_identity(UID, CID)[0][:16]
    ]
    for message in messages:
        assert UID not in message and CID not in message and 'synthetic-content' not in message


def test_unexpected_failure_is_counted_and_never_raises(world, monkeypatch, caplog):
    def boom(*a, **kw):
        raise RuntimeError('sensitive@example.test users/0123456789012345678901234567')

    monkeypatch.setattr(record_gap_fill, 'list_audio_chunks', boom)
    with caplog.at_level(logging.INFO, logger=record_gap_fill.__name__):
        assert fill(world) == 'failed'
    assert 'sensitive' not in caplog.text and UID not in caplog.text


@pytest.mark.parametrize('enabled', [False, True])
async def test_jobs_missing_upload_runs_the_fill_and_keeps_the_same_503(monkeypatch, enabled):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_GAP_FILL', 'on' if enabled else 'off')
    monkeypatch.setenv('RECORD_GAP_FILL_PERCENT', '100')
    store = MemoryStore()
    content, _ = live_upload.record_identity(UID, CID)
    store.rows['intakes', 'bp_' + content] = {'segment_ids': []}
    calls = []
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(live_upload, 'remember_record_wait', lambda *a: None)

    async def run(**kw):
        calls.append(kw)
        return 'written', False

    monkeypatch.setattr(record_gap_fill, 'run_gap_fill', run)
    response = await live_upload.registered_record_response(
        uid=UID,
        conversation_id=CID,
        content_id='synthetic-content',
        paths=['synthetic-wal.bin'],
        source='omi',
        client_device_id='synthetic-device',
        loaded_conversation=closed_row(),
        policy=BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=True),
    )
    assert response.status_code == 503
    assert json.loads(response.body)['code'] == 'record_capture_pending'
    assert len(calls) == (1 if enabled else 0)
    if enabled:
        assert calls[0]['paths'] == ['synthetic-wal.bin'] and calls[0]['wal_content_id'] == 'synthetic-content'
        assert calls[0]['store'] is store


async def test_serving_entry_runs_both_phases(world, monkeypatch):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(100.0, ramp(12))]
    monkeypatch.setattr(
        record_gap_fill, 'create_storage_client', lambda: SimpleNamespace(bucket=lambda name: world.bucket)
    )
    monkeypatch.setattr(record_gap_fill, 'users_db', SimpleNamespace(get_data_protection_level=lambda uid: 'standard'))
    monkeypatch.setattr(record_gap_fill.audio_archive, 'admitted', lambda *a, **kw: False)
    monkeypatch.setattr(record_gap_fill, '_fresh_row', lambda store, uid, cid: closed_row())
    outcome = await record_gap_fill.run_gap_fill(
        uid=UID,
        conversation_id=CID,
        paths=['synthetic-wal.bin'],
        wal_content_id='c',
        store=world.store,
    )
    assert outcome == ('written', False)
    assert list(fills(world)) == [f'chunks/{UID}/{CID}/105.000000.bin']


def test_fresh_row_carries_the_firestore_revision_for_the_settle_gate(world):
    # A raw to_dict() row has no updated_at; a just-released upload session
    # must still count as a recent write.
    stored = closed_row(updated_at=None)
    revision = datetime.fromtimestamp(NOW - 10, timezone.utc)
    snapshot = SimpleNamespace(to_dict=lambda: dict(stored), update_time=revision)
    doc = SimpleNamespace(get=lambda: snapshot)
    node = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: doc))
    world.store.client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: node))
    row = record_gap_fill._fresh_row(world.store, UID, CID)
    assert record_gap_fill._epoch(row['updated_at']) == NOW - 10
    assert fill(world, row=row) == 'skipped_recent'


async def test_serving_entry_skips_a_missing_conversation(world, monkeypatch):
    monkeypatch.setattr(record_gap_fill, '_fresh_row', lambda store, uid, cid: None)
    outcome = await record_gap_fill.run_gap_fill(
        uid=UID, conversation_id=CID, paths=['synthetic-wal.bin'], wal_content_id='c', store=world.store
    )
    assert outcome == ('skipped_gate', False)
    assert not world.markers


def test_playback_merge_reads_six_decimal_gap_fill_keys(world, monkeypatch):
    # The non-strict reader rebuilds keys at 3 decimals; it must resolve the
    # listed 6-decimal gap-fill path (strict playback already did).
    monkeypatch.setattr(storage, '_get_storage_client', lambda: SimpleNamespace(bucket=lambda name: world.bucket))
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(100.0, ramp(12))]
    assert fill(world) == 'written'
    listed = world.bucket.listing()
    requested = []

    def loader(path):
        requested.append(path)
        return world.bucket.objects[path]['data'] if path in world.bucket.objects else None

    pcm = storage.download_audio_chunks_and_merge(
        UID, CID, [c['timestamp'] for c in listed], listed_chunks=listed, chunk_loader=loader
    )
    assert f'chunks/{UID}/{CID}/105.000000.bin' in requested
    assert pcm[5 * RATE * 2 :] == ramp(12)[5 * RATE * 2 : 11 * RATE * 2]


def test_marker_client_is_bounded(monkeypatch):
    made = []
    monkeypatch.setattr(sync_record_wait_cache, '_marker_redis', None)
    monkeypatch.setattr(sync_record_wait_cache, 'create_bounded_redis_client', lambda t: made.append(t) or object())
    first = sync_record_wait_cache._marker_client()
    assert sync_record_wait_cache._marker_client() is first
    assert made == [0.5]


# --- Admission-race fence: the fill holds the drain's lease ------------------


def job(world):
    return world.store.rows['jobs', world.segment]


def test_fill_takes_the_drain_lease_and_releases_it_on_the_claim_clock(world):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(105.0, ramp(5))]
    held = []
    assert fill(world, on_written=lambda: held.append(job(world)['available_at'])) == 'written'
    assert held == [NOW + record_gap_fill.FILL_LEASE_SECONDS]
    assert job(world)['available_at'] == NOW


def test_a_live_lease_means_admission_is_in_flight_and_nothing_is_written(world):
    job(world)['available_at'] = NOW + 1
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world) == 'skipped_busy'
    assert world.bucket.objects == {} and world.markers == set()
    assert job(world)['available_at'] == NOW + 1


def test_drain_skips_the_record_while_the_fill_holds_its_lease(world, monkeypatch):
    admitted = []

    async def admit(store, pending):
        admitted.append(pending['segment_id'])

    monkeypatch.setattr(live, 'admit_recording', admit)
    job(world)['available_at'] = 0
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(105.0, ramp(5))]
    mid = []

    def drain():
        asyncio.run(live.drain_recordings(world.store))
        mid.append(list(admitted))

    assert fill(world, now=time.time(), on_written=drain) == 'written'
    assert mid == [[]]
    asyncio.run(live.drain_recordings(world.store))
    assert admitted == [world.segment]


@pytest.mark.parametrize(
    'move',
    [
        lambda row: {**row, 'state': 'admitted'},
        lambda row: {**row, 'available_at': row['available_at'] + 1},
    ],
)
def test_a_job_moved_mid_fill_is_counted_raced_and_never_acked(world, monkeypatch, move):
    monkeypatch.setenv('RECORD_RETAINED_ACK', 'on')
    monkeypatch.setenv('RECORD_RETAINED_ACK_PERCENT', '100')
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    before = record_gap_fill.GAP_FILL_TOTAL.labels(outcome='raced')._value.get()

    moved = []

    def mover():
        moved.append(move(job(world)))
        world.store.rows['jobs', world.segment] = dict(moved[0])

    assert fill(world, on_written=mover) == 'raced'
    assert record_gap_fill.GAP_FILL_TOTAL.labels(outcome='raced')._value.get() == before + 1
    # Whoever moved the job keeps it; the fill does not release their lease.
    assert job(world) == moved[0]


def test_a_privacy_block_at_the_recheck_is_raced(world, monkeypatch):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(105.0, ramp(5))]
    real, calls = world.store.run, []

    def run(body):
        calls.append(body)
        if len(calls) == 2:
            raise BatchPrivacyBlocked('synthetic block')
        return real(body)

    monkeypatch.setattr(world.store, 'run', run)
    assert fill(world) == 'raced'


# --- Option A: covered 200 once a byte-exact durable copy is held -------------


@pytest.fixture
def ack(world, monkeypatch):
    monkeypatch.setenv('RECORD_RETAINED_ACK', 'on')
    monkeypatch.setenv('RECORD_RETAINED_ACK_PERCENT', '100')
    reads = []

    def read(client, ref, uid, cid, allowed, key, **kwargs):
        stored = world.bucket.objects[ref['path']]
        # The real reader pins the listed generation and fails closed if it moved.
        if ref['generation'] != stored['generation']:
            raise ValueError('generation moved')
        reads.append(ref['path'])
        return decode_source(stored['data'], {**ref, 'metadata': stored['metadata']}, key)

    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', lambda *a, **kw: world.bucket.listing())
    monkeypatch.setattr(record_retained_ack, 'read_reference', read)
    return SimpleNamespace(reads=reads)


def acks(outcome):
    return record_retained_ack.RETAINED_ACK_TOTAL.labels(outcome=outcome)._value.get()


def test_ack_after_a_full_fill(world, ack, caplog):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    before = acks('acked')
    with caplog.at_level(logging.INFO, logger=record_retained_ack.__name__):
        assert fill(world) == 'acked'
    assert acks('acked') == before + 1
    assert sorted(ack.reads) == [f'chunks/{UID}/{CID}/100.000.bin', f'chunks/{UID}/{CID}/105.000000.bin']
    validate_record_tail(admitted_units(world)[1], closed_row()['finished_at'])
    messages = [r.getMessage() for r in caplog.records if 'sync_record_retained_ack' in r.getMessage()]
    assert messages == [
        'event=sync_record_retained_ack outcome=acked record=%s' % live.record_identity(UID, CID)[0][:16]
    ]
    assert UID not in caplog.text and CID not in caplog.text and 'synthetic-content' not in caplog.text


def test_a_retry_of_an_acked_wal_gets_the_same_answer(world, ack):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world) == 'acked'
    stored = dict(world.bucket.objects)
    assert fill(world) == 'acked'
    assert world.bucket.objects == stored


@pytest.mark.parametrize('env', [{'RECORD_RETAINED_ACK': 'off'}, {'RECORD_RETAINED_ACK_PERCENT': '0'}])
def test_ack_switch_off_or_zero_keeps_the_fill_outcome(world, ack, monkeypatch, env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world) == 'written'
    assert ack.reads == []


def test_one_differing_sample_is_never_acked(world, ack):
    held = bytearray(ramp(5))
    held[2 * RATE : 2 * RATE + 2] = (12345).to_bytes(2, 'little', signed=True)
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', bytes(held))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    before = acks('skipped_bytes_differ')
    assert fill(world) == 'written'
    assert acks('skipped_bytes_differ') == before + 1


def test_a_wal_hole_the_fill_stopped_at_is_never_acked(world, ack):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    whole = ramp(10)
    world.wal['units'] = [audio_unit(100.0, whole[: 7 * RATE * 2]), audio_unit(108.0, whole[8 * RATE * 2 :])]
    before = acks('skipped_uncovered')
    assert fill(world) == 'written'
    assert acks('skipped_uncovered') == before + 1


def test_a_collision_or_gate_refusal_is_never_proven(world, ack, monkeypatch):
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world, row=closed_row(status='in_progress')) == 'skipped_gate'
    assert 'skipped_collision' not in record_gap_fill.ACKABLE and 'raced' not in record_gap_fill.ACKABLE
    assert ack.reads == []


def test_a_privacy_block_at_the_ack_recheck_is_never_acked(world, ack, monkeypatch):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    real, calls = world.store.run, []

    def run(body):
        calls.append(body)
        if len(calls) == 3:
            raise BatchPrivacyBlocked('synthetic block')
        return real(body)

    monkeypatch.setattr(world.store, 'run', run)
    before = acks('skipped_privacy')
    assert fill(world) == 'written'
    assert acks('skipped_privacy') == before + 1


def test_a_replaced_object_fails_the_pinned_read_closed(world, ack, monkeypatch):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]

    def stale(*a, **kw):
        listed = world.bucket.listing()
        world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
        return listed

    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', stale)
    before = acks('failed')
    assert fill(world) == 'written'
    assert acks('failed') == before + 1


def test_enhanced_fill_objects_count_as_lossless(world, ack):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    assert fill(world, protection_level='enhanced') == 'acked'
    assert any(path.endswith('.enc') for path in fills(world))


def test_multi_batch_walk_acks_each_batch_and_admission_passes(world, ack):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    whole = ramp(10)
    # Batch 1 is already held byte for byte; the phone may release it.
    world.wal['units'] = [audio_unit(100.0, whole[: 5 * RATE * 2])]
    assert fill(world, wal_content_id='batch-1') == 'acked'
    assert fills(world) == {}
    # Batch 2 is the missing span: filled, then acked.
    world.wal['units'] = [audio_unit(105.0, whole[5 * RATE * 2 :])]
    assert fill(world, wal_content_id='batch-2') == 'acked'
    _, units = admitted_units(world)
    validate_record_tail(units, closed_row()['finished_at'])
    assert materialized(world, units[0])[: 5 * RATE * 2] == whole[: 5 * RATE * 2]


def test_real_decoder_wal_is_proven_against_the_fill(world, ack, tmp_path, monkeypatch):
    monkeypatch.setattr(record_gap_fill, 'source_units', REAL_SOURCE_UNITS)
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    whole = ramp(10)
    paths = [wal_file(tmp_path, 105, whole[5 * RATE * 2 :])]
    assert fill(world, paths=paths) == 'acked'
    # The fill consumed the uploaded files; the proof used the one decode.
    assert not any(os.path.exists(path) for path in paths)


def held_listing(*entries):
    return [{'path': path, 'timestamp': start, 'generation': 1, **extra} for path, start, extra in entries]


@pytest.mark.parametrize(
    'name,extra',
    [
        ('100.000.opus', {}),
        ('100.000.opus.enc', {}),
        ('100.000.batch.bin', {}),
        ('100.000.bin', {'is_batch': True}),
        ('100.000.bin', {'raw_offset_samples': 0}),
    ],
)
def test_lossy_or_packed_sources_never_count(world, monkeypatch, name, extra):
    path = f'chunks/{UID}/{CID}/{name}'
    assert not record_retained_ack.lossless_source({'path': path, **extra})
    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', lambda *a, **kw: held_listing((path, 100.0, extra)))
    monkeypatch.setattr(record_retained_ack, 'read_reference', lambda *a, **kw: pytest.fail('a lossy source was read'))
    wal = [audio_unit(100.0, ramp(5))]
    outcome = record_retained_ack.prove(UID, CID, wal, object(), finish=110.0, started=100.0)
    assert outcome == 'skipped_lossy_source'


@pytest.mark.parametrize(
    'units,started,expected',
    [
        ([audio_unit(100.0, ramp(12))], 100.0, 'skipped_outside_record'),
        ([audio_unit(98.0, ramp(3))], 100.0, 'skipped_outside_record'),
        ([audio_unit(100.0, ramp(5))], None, 'skipped_outside_record'),
        ([], 100.0, 'skipped_uncovered'),
    ],
)
def test_wal_outside_the_record_window_is_refused_before_any_read(monkeypatch, units, started, expected):
    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', lambda *a, **kw: pytest.fail('listed'))
    assert record_retained_ack.prove(UID, CID, units, object(), finish=110.0, started=started) == expected


async def test_acked_upload_answers_the_covered_200(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('RECORD_GAP_FILL', 'on')
    monkeypatch.setenv('RECORD_GAP_FILL_PERCENT', '100')
    store = MemoryStore()
    content, _ = live_upload.record_identity(UID, CID)
    store.rows['intakes', 'bp_' + content] = {'segment_ids': []}
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(live_upload, 'remember_record_wait', lambda *a: pytest.fail('an acked upload waits'))

    async def run(**kw):
        return 'written', True

    monkeypatch.setattr(record_gap_fill, 'run_gap_fill', run)
    response = await live_upload.registered_record_response(
        uid=UID,
        conversation_id=CID,
        content_id='synthetic-content',
        paths=['synthetic-wal.bin'],
        source='omi',
        client_device_id='synthetic-device',
        loaded_conversation=closed_row(),
        policy=BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=True),
    )
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body['new_memories'] == [] and body['updated_memories'] == []


def test_objects_outside_the_archive_buckets_never_count(monkeypatch):
    monkeypatch.setenv('BUCKET_AUDIO_DERIVED', 'synthetic-derived')
    listing = held_listing((f'chunks/{UID}/{CID}/100.000.bin', 100.0, {'bucket': 'synthetic-batch-staging'}))
    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', lambda *a, **kw: listing)
    monkeypatch.setattr(record_retained_ack, 'read_reference', lambda *a, **kw: pytest.fail('staging read'))
    wal = [audio_unit(100.0, ramp(5))]
    assert record_retained_ack.prove(UID, CID, wal, object(), finish=110.0, started=100.0) == 'skipped_uncovered'


def test_slow_gates_shorten_the_write_window_never_the_lease(world, ack, monkeypatch):
    # The write deadline is measured before the gates take the lease, so time
    # spent there comes out of the write window; here none is left.
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', ramp(5))
    world.wal['units'] = [audio_unit(100.0, ramp(10))]
    clock = iter([0.0, record_gap_fill.FILL_LEASE_SECONDS])
    monkeypatch.setattr(record_gap_fill.time, 'monotonic', lambda: next(clock, record_gap_fill.FILL_LEASE_SECONDS))
    before = acks('acked')
    assert fill(world) == 'skipped_no_audio'
    assert fills(world) == {} and acks('acked') == before


def test_each_piece_upload_is_bounded_inside_the_lease_margin(world):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(105.0, ramp(5))]
    assert fill(world) == 'written'
    (call,) = world.bucket.calls
    margin = record_gap_fill.LEASE_MARGIN_SECONDS
    assert call['timeout'] + call['retry'].timeout < margin


async def test_a_cancelled_upload_never_releases_the_lease_under_a_running_write(world, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow_write(*args):
        started.set()
        release.wait(5)
        return 'written', 1.0

    monkeypatch.setattr(record_gap_fill, '_write', slow_write)
    monkeypatch.setattr(record_gap_fill, '_fresh_row', lambda store, uid, cid: closed_row())
    job(world)['available_at'] = 0
    task = asyncio.ensure_future(
        record_gap_fill.run_gap_fill(
            uid=UID, conversation_id=CID, paths=['synthetic-wal.bin'], wal_content_id='c', store=world.store
        )
    )
    while not started.is_set():
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # The storage thread is still writing: the drain must keep skipping the row.
    assert job(world)['available_at'] > time.time()
    release.set()


def test_the_listed_span_rate_is_authoritative(monkeypatch):
    path = f'chunks/{UID}/{CID}/100.000.bin'
    listing = held_listing((path, 100.0, {'span': {'sample_rate': 8000}}))
    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', lambda *a, **kw: listing)
    monkeypatch.setattr(record_retained_ack, 'read_reference', lambda client, ref, *a, **kw: ramp(5))
    wal = [audio_unit(100.0, ramp(5))]
    assert record_retained_ack.prove(UID, CID, wal, object(), finish=110.0, started=100.0) == 'skipped_lossy_source'


def test_a_stalled_storage_gate_past_the_deadline_never_uploads(world, monkeypatch):
    world.bucket.put(f'chunks/{UID}/{CID}/100.000.bin', tone(5, 7))
    world.wal['units'] = [audio_unit(105.0, ramp(5))]
    gate = record_gap_fill.owner_storage_write_gate

    class Stalled:
        def __init__(self, *a):
            self.inner = gate(*a)

        def __enter__(self):
            monkeypatch.setattr(record_gap_fill.time, 'monotonic', lambda: 1e12)
            return self.inner.__enter__()

        def __exit__(self, *exc):
            return self.inner.__exit__(*exc)

    monkeypatch.setattr(record_gap_fill, 'owner_storage_write_gate', Stalled)
    assert fill(world) == 'skipped_no_audio'
    assert fills(world) == {} and world.bucket.calls == []


def test_overlapping_objects_that_together_hold_every_sample_are_acked(monkeypatch):
    whole = ramp(10)
    first = bytearray(whole)
    first[6 * RATE * 2 : 6 * RATE * 2 + 2] = (12345).to_bytes(2, 'little', signed=True)
    objects = {
        f'chunks/{UID}/{CID}/100.000.bin': bytes(first),
        f'chunks/{UID}/{CID}/105.000000.bin': whole[5 * RATE * 2 :],
    }
    listing = held_listing(*[(path, float(path.rsplit('/', 1)[1][:-4]), {}) for path in objects])
    monkeypatch.setattr(record_retained_ack, 'list_audio_chunks', lambda *a, **kw: listing)
    monkeypatch.setattr(record_retained_ack, 'read_reference', lambda client, ref, *a, **kw: objects[ref['path']])
    wal = [audio_unit(100.0, whole)]
    assert record_retained_ack.prove(UID, CID, wal, object(), finish=110.0, started=100.0) == 'acked'
    # Without the second object the differing sample is unproven.
    listing.pop()
    assert record_retained_ack.prove(UID, CID, wal, object(), finish=110.0, started=100.0) == 'skipped_bytes_differ'
