"""Deterministic decode failures: same 503, no second decode or staging."""

from types import SimpleNamespace

import json

import pytest

from config.policy import BatchUnitPolicy
from database import sync_record_wait_cache as cache
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import intake
from utils.sync.legacy_dark import LegacySyncMode


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
        assert nx and ex == 300
        if key in self.rows and self.now < self.rows[key][1]:
            return False
        self.rows[key] = (value, self.now + ex)
        self.expiries.append(ex)
        self.writes += 1
        return True


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('SYNC_RECORD_DECODE_FAILURE_MEMO', raising=False)
    redis = ExpiringRedis()
    monkeypatch.setattr(cache, '_marker_redis', redis)
    store = MemoryStore()
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda uid=None: LegacySyncMode.DARK)
    monkeypatch.setattr(
        intake,
        'batch_artifact_authorize',
        lambda _store, _seed, snapshots: _authorize(snapshots),
    )
    monkeypatch.setattr(intake, 'artifacts_for', lambda _store: SimpleNamespace(stage_audio=lambda *_: 'x'))
    counts = {'decode': 0, 'stage': 0}
    failure = {'error': ValueError('truncated sync audio frame')}

    def decode(*_args, **_kwargs):
        # A generator like the real decoder: the fault surfaces on iteration,
        # inside the decode phase, never at call time.
        counts['decode'] += 1
        raise failure['error']
        yield  # pragma: no cover

    monkeypatch.setattr(intake, 'decode_units', decode)
    path = tmp_path / '100.0_pcm16_16000_1.bin'
    path.write_bytes(b'\x00\x01' * 16000)

    async def upload():
        return await intake.accept_upload(
            uid='synthetic-owner',
            job_id='new',
            content_id='synthetic-content',
            paths=[str(path)],
            lane='fresh',
            recording_age_seconds=0,
            source='omi',
            should_lock=False,
            conversation_id=None,
            client_device_id='synthetic-device',
            client_platform='ios',
            policy=BatchUnitPolicy(batch_enabled=True, live_record_enabled=False),
        )

    return SimpleNamespace(redis=redis, store=store, counts=counts, failure=failure, upload=upload)


def _authorize(snapshots):
    from utils.batch_pipeline.artifacts import ProtectionContext

    snapshots['user'] = {'language': 'en', 'transcription_preferences': {'single_language_mode': True}}
    return ProtectionContext('standard', 0)


DETERMINISTIC = [
    ValueError('truncated sync audio frame'),
    ValueError('invalid sync audio frame'),
    ValueError('empty sync audio'),
    ValueError('unsupported sync PCM format'),
    ValueError('empty decoded sync audio'),
    ValueError('sync decode did not preserve every uploaded frame'),
    ValueError('capture bundle exceeds bounded conversation-unit limit'),
]


class Synthetic400(Exception):
    status_code = 400
    detail = 'Audio decode failed'


@pytest.mark.parametrize('error', DETERMINISTIC + [Synthetic400('Audio decode failed')])
async def test_deterministic_failure_keeps_the_503_and_stops_re_decoding(world, error):
    world.failure['error'] = error
    first = await world.upload()
    assert first.status_code == 503
    assert first.headers['retry-after'] == '30'
    assert world.counts['decode'] == 1
    assert world.redis.writes == 1
    assert world.redis.expiries == [300]

    repeat = await world.upload()
    assert repeat.status_code == 503
    # The exact pre-change answer, not merely hit == miss: the body is the
    # contract the phone parses.
    assert json.loads(repeat.body) == {
        'code': 'sync_batch_unavailable',
        'detail': 'Sync is temporarily unavailable; retain local audio',
    }
    assert repeat.body == first.body
    assert dict(repeat.headers) == dict(first.headers)
    # The proven failure answers the same retryable 503 with no decode at all.
    assert world.counts['decode'] == 1
    assert world.redis.reads == 2


async def test_the_memo_expires_and_the_check_runs_again(world):
    assert (await world.upload()).status_code == 503
    world.redis.now = 299.999
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 1
    world.redis.now = 300
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2


@pytest.mark.parametrize(
    'error',
    [
        ValueError('serving intake requires a dedicated batch GPU pool'),
        ValueError('synthetic unexpected parse failure'),
        RuntimeError('synthetic Firestore contention'),
        TimeoutError('synthetic lost reply'),
    ],
)
async def test_non_decoder_failures_are_never_memoized(world, error):
    world.failure['error'] = error
    assert (await world.upload()).status_code == 503
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2
    assert world.redis.writes == 0


@pytest.mark.parametrize('value', ['false', '0', 'off', ' OFF '])
async def test_kill_switch_off_restores_the_repeat_decode(world, monkeypatch, value):
    monkeypatch.setenv('SYNC_RECORD_DECODE_FAILURE_MEMO', value)
    assert (await world.upload()).status_code == 503
    assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2
    assert world.redis.reads == world.redis.writes == 0


async def test_redis_outage_falls_through_to_the_full_decode(world, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError('synthetic Redis outage')

    monkeypatch.setattr(world.redis, 'get', fail)
    monkeypatch.setattr(world.redis, 'set', fail)
    for _ in range(2):
        assert (await world.upload()).status_code == 503
    assert world.counts['decode'] == 2


def test_key_is_the_upload_identity_only(world, monkeypatch, tmp_path):
    key = intake._decode_failure_key
    path = tmp_path / 'a.bin'
    path.write_bytes(b'\x00' * 10)
    baseline = key('owner', 'content', [str(path)])
    assert baseline == key('owner', 'content', [str(path)])
    assert baseline != key('other-owner', 'content', [str(path)])
    assert baseline != key('owner', 'other-content', [str(path)])
    assert key('owner', 'content', [str(tmp_path / 'gone.bin')]) is None
    assert len(baseline) == 64 and '/' not in baseline
    assert 'a.bin' not in baseline and 'owner' not in baseline


def test_classifier_rejects_anything_outside_the_closed_vocabulary():
    from utils.batch_pipeline.capture_decode import is_deterministic_decode_failure

    assert is_deterministic_decode_failure(ValueError('empty sync audio'))
    assert is_deterministic_decode_failure(Synthetic400('Audio decode failed'))
    assert not is_deterministic_decode_failure(ValueError('serving intake requires a dedicated batch GPU pool'))
    assert not is_deterministic_decode_failure(RuntimeError('truncated sync audio frame'))
    assert not is_deterministic_decode_failure(ValueError('some other message'))


async def test_a_content_receipt_answers_before_the_decode_memo(world):
    # A durable receipt means this upload was already admitted; it must be
    # acknowledged on its own branch, never shadowed by a cached decode failure.
    world.store.rows['content', 'synthetic-owner/synthetic-content'] = {
        'dispatch_protocol': 'batch_v1',
        'job_id': 'bp_prior',
        'status': 'processing',
    }
    response = await world.upload()
    assert world.counts['decode'] == 0
    assert world.redis.reads == 0
    assert response is not None and response.status_code != 503
