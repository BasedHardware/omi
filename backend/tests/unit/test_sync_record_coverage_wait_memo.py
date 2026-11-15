"""WAL-scoped negative coverage memo: real response and byte comparison path."""

import io
from types import SimpleNamespace
import wave

import pytest

from config.policy import BatchUnitPolicy
from database import sync_record_wait_cache as cache
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import live_upload
from utils.sync.content_id import compute_sync_content_id


class ExpiringRedis:
    def __init__(self):
        self.now = 0
        self.rows = {}
        self.reads = 0
        self.writes = 0
        self.expiries = []

    def get(self, key):
        self.reads += 1
        value, deadline = self.rows.get(key, (None, 0))
        return value if self.now < deadline else None

    def set(self, key, value, *, ex, nx):
        assert nx and ex in (30, 300)
        if key in self.rows and self.now < self.rows[key][1]:
            return False
        self.rows[key] = (value, self.now + ex)
        self.expiries.append(ex)
        self.writes += 1
        return True


def wav(pcm):
    result = io.BytesIO()
    with wave.open(result, 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(pcm)
    return result.getvalue()


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('SYNC_RECORD_COVERAGE_WAIT_MEMO', raising=False)
    monkeypatch.setenv('ENCRYPTION_SECRET', 'synthetic-test-content-secret')
    redis = ExpiringRedis()
    monkeypatch.setattr(cache, '_marker_redis', redis)
    store = MemoryStore()
    uid, cid = 'synthetic-owner', 'synthetic-conversation'
    content, _ = live_upload.record_identity(uid, cid)
    job = dict(
        segment_id='segment-1',
        owner_id=uid,
        capture_at=100.0,
        audio_uri='gs://synthetic/record-1',
        duration_seconds=1.0,
        priority=0,
    )
    store.rows['intakes', 'bp_' + content] = {'segment_ids': ['segment-1']}
    store.rows['jobs', 'segment-1'] = job
    store.rows['content', f'{uid}/{content}'] = dict(dispatch_protocol='batch_v1', job_id='bp_' + content)
    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    counts = {'decode': 0, 'fetch': 0, 'artifacts': 0}
    record_pcm = b'\x01\x00' * 16000

    def decode(paths):
        counts['decode'] += 1
        for path in paths:
            yield SimpleNamespace(wav=wav(path.read_bytes()), capture_at=100.0, duration_seconds=1.0)

    def fetch(item):
        counts['fetch'] += 1
        return wav(record_pcm)

    def artifacts(*_):
        counts['artifacts'] += 1
        return SimpleNamespace(fetch_audio=fetch)

    monkeypatch.setattr(live_upload, 'decode_units', decode)
    monkeypatch.setattr(live_upload, 'artifacts_for', artifacts)
    monkeypatch.setattr(live_upload, 'durable_status', lambda *_: {'status': 'processing'})
    monkeypatch.setattr(live_upload, 'start_response', lambda *_: live_upload.covered_response())
    bad = tmp_path / '100.0_pcm16_16000_1.bin'
    bad.write_bytes(b'\x02\x00' * 16000)
    good = tmp_path / 'good' / bad.name
    good.parent.mkdir()
    good.write_bytes(record_pcm)

    async def upload(path=bad):
        return await live_upload.registered_record_response(
            uid=uid,
            conversation_id=cid,
            content_id=compute_sync_content_id(uid, [path]),
            paths=[path],
            source='omi',
            client_device_id='synthetic-device',
            loaded_conversation=dict(
                record_lane_owner=live_upload.OWNER, source='omi', client_device_id='synthetic-device'
            ),
            policy=BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=True),
        )

    return SimpleNamespace(redis=redis, store=store, job=job, counts=counts, bad=bad, good=good, upload=upload)


async def test_same_wal_repeats_identical_503_before_decode_or_artifact_lookup(world):
    first = await world.upload()
    repeat = await world.upload()
    assert first.status_code == repeat.status_code == 503
    assert first.body == repeat.body
    assert dict(first.headers) == dict(repeat.headers)
    assert 'retry-after' not in repeat.headers
    assert world.counts == {'decode': 1, 'fetch': 1, 'artifacts': 1}
    assert world.redis.reads == 2 and world.redis.writes == 1


async def test_different_wal_same_filename_and_conversation_can_prove_coverage(world):
    assert (await world.upload()).status_code == 503
    assert (await world.upload(world.good)).status_code == 200
    assert world.counts['decode'] == 2
    assert world.redis.writes == 1  # Positive coverage is never memoized.


@pytest.mark.parametrize('change', ['unit_added', 'artifact_changed', 'duration_changed'])
async def test_record_job_change_invalidates(world, change):
    assert (await world.upload()).status_code == 503
    if change == 'unit_added':
        intake = next(row for (kind, _), row in world.store.rows.items() if kind == 'intakes')
        intake['segment_ids'].append('segment-2')
        world.store.rows['jobs', 'segment-2'] = dict(world.job, segment_id='segment-2', capture_at=101.0)
    elif change == 'artifact_changed':
        world.store.rows['jobs', 'segment-1']['audio_uri'] = 'gs://synthetic/record-2'
    else:
        world.store.rows['jobs', 'segment-1']['duration_seconds'] = 2.0
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2
    assert world.redis.writes == 2


@pytest.mark.parametrize('value', ['false', '0', 'off', ' OFF '])
async def test_kill_switch_off_runs_original_path_without_memo_io(world, monkeypatch, value):
    assert (await world.upload()).status_code == 503  # Existing entries are bypassed too.
    monkeypatch.setenv('SYNC_RECORD_COVERAGE_WAIT_MEMO', value)
    for _ in range(2):
        assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 3
    assert world.redis.reads == world.redis.writes == 1


@pytest.mark.parametrize('where', ['artifacts_for', 'decode_units', 'fetch_audio'])
async def test_errors_are_never_memoized(world, monkeypatch, where):
    def fail(*_):
        raise RuntimeError('synthetic failure')

    with monkeypatch.context() as patch:
        if where == 'fetch_audio':
            patch.setattr(live_upload, 'artifacts_for', lambda *_: SimpleNamespace(fetch_audio=fail))
        else:
            patch.setattr(live_upload, where, fail)
        for _ in range(2):
            assert (await world.upload()).status_code == 503
    assert world.redis.writes == 0
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == (3 if where == 'fetch_audio' else 1)
    assert world.redis.writes == 1


async def test_ttl_boundary_and_hits_never_extend_expiry(world):
    assert (await world.upload()).status_code == 503
    world.redis.now = 299.999
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 1
    assert world.redis.writes == 1
    world.redis.now = 300
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2
    assert world.redis.writes == 2
    # The coverage memo owns its 300 s window; the conversation memo keeps 30 s.
    assert world.redis.expiries == [300, 300]


def test_concurrent_negative_writes_keep_first_expiry(world):
    cache.remember_coverage_wait('synthetic-key')
    world.redis.now = 5
    cache.remember_coverage_wait('synthetic-key')
    assert world.redis.writes == 1
    world.redis.now = 300
    assert not cache.cached_coverage_wait('synthetic-key')


async def test_cache_outage_falls_through_to_original_response(world, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError('synthetic Redis outage')

    monkeypatch.setattr(world.redis, 'get', fail)
    monkeypatch.setattr(world.redis, 'set', fail)
    for _ in range(2):
        assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2


def test_key_isolates_owner_conversation_upload_and_wal_and_tracks_jobs():
    key = live_upload._coverage_wait_key
    identity = (1, 32000)
    baseline = key('u', 'c', 'wal', [{'segment_id': 's'}], identity)
    assert (
        len(
            {
                baseline,
                key('v', 'c', 'wal', [{'segment_id': 's'}], identity),
                key('u', 'd', 'wal', [{'segment_id': 's'}], identity),
                key('u', 'c', 'other', [{'segment_id': 's'}], identity),
                key('u', 'c', 'wal', [{'segment_id': 't'}], identity),
                # A different upload for the same record and jobs must not share a miss.
                key('u', 'c', 'wal', [{'segment_id': 's'}], (1, 32001)),
                key('u', 'c', 'wal', [{'segment_id': 's'}], (2, 32000)),
            }
        )
        == 7
    )


def spy_lease(monkeypatch):
    """Count retained copies and partial wakes without touching storage."""
    from utils.batch_pipeline import record_lease_append

    calls = {'retain': 0, 'rearm': 0}

    async def retain(uid, cid, row, paths, store):
        calls['retain'] += 1

    async def rearm(uid, cid, row, store):
        calls['rearm'] += 1

    monkeypatch.setattr(record_lease_append, 'retain_upload', retain)
    monkeypatch.setattr(record_lease_append, 'rearm_partial', rearm)
    return calls


async def test_memo_hit_answers_before_the_retained_copy_and_keeps_the_partial_wake(world, monkeypatch):
    calls = spy_lease(monkeypatch)
    assert (await world.upload()).status_code == 503
    assert calls == {'retain': 1, 'rearm': 0}

    repeat = await world.upload()
    assert repeat.status_code == 503
    # The copy that the memo stands in for is skipped; the wake that moves the
    # record forward still runs.
    assert calls == {'retain': 1, 'rearm': 1}
    assert world.counts == {'decode': 1, 'fetch': 1, 'artifacts': 1}
    assert world.redis.writes == 1


async def test_a_different_wal_for_the_same_record_is_still_retained(world, monkeypatch):
    calls = spy_lease(monkeypatch)
    other = world.bad.parent / '101.0_pcm16_16000_1.bin'
    other.write_bytes(b'\x03\x00' * 16000)
    assert (await world.upload()).status_code == 503
    assert (await world.upload(other)).status_code == 503
    # Same record, same jobs, same owner: the upload identity is what keeps the
    # second file from inheriting the first one's negative result.
    assert calls['retain'] == 2
    assert world.counts['decode'] == 2
    assert world.redis.writes == 2


async def test_memo_first_kill_switch_keeps_the_memo_after_the_copy(world, monkeypatch):
    calls = spy_lease(monkeypatch)
    assert (await world.upload()).status_code == 503
    monkeypatch.setenv('SYNC_RECORD_WAIT_MEMO_FIRST', 'off')
    assert (await world.upload()).status_code == 503
    # Off restores the pre-change order: the copy runs, then the memo answers.
    assert calls['retain'] == 2
    assert calls['rearm'] == 0
    assert world.counts['decode'] == 1
    assert world.redis.writes == 1


def test_upload_identity_is_the_count_and_total_bytes(world):
    assert live_upload._upload_identity([world.bad]) == (1, 32000)
    assert live_upload._upload_identity([world.bad, world.good]) == (2, 64000)


def test_missing_upload_file_has_no_identity(world, tmp_path):
    # An unreadable upload cannot carry a memo key: the caller checks in full
    # instead of trusting another upload's result.
    assert live_upload._upload_identity([tmp_path / 'gone.bin']) is None


async def test_a_content_receipt_is_answered_before_the_memo(world):
    assert (await world.upload()).status_code == 503  # Writes the negative memo.
    content_id = compute_sync_content_id('synthetic-owner', [world.bad])
    content, _ = live_upload.record_identity('synthetic-owner', 'synthetic-conversation')
    world.store.rows['content', f'synthetic-owner/{content_id}'] = {
        'dispatch_protocol': 'batch_v1',
        'job_id': 'bp_' + content,
    }
    response = await world.upload()
    # A receipt for this exact upload owns the answer; a cached negative for the
    # same record must never turn an admitted upload back into a wait.
    assert response.status_code == 200
    assert world.counts['decode'] == 1
