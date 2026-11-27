"""SCA-3376: the pre-fence shadow gate never reaches settlement and keeps 480 proofs in 4 h."""

import hashlib
import time
from unittest.mock import Mock

import pytest

from config import record_wal_sample as sampler
from config.record_wal_duplicate import SHADOW_CONTENT_MODULUS, SHADOW_SLOT_SECONDS, SHADOW_WINDOW_SECONDS, mode
from database import record_wal_duplicate as ledger
from utils.batch_pipeline import record_wal_duplicate as duplicate
from utils.batch_pipeline import record_wal_sample as sample

EPOCH = 1_800_000_000
END = EPOCH + 14_400 - sampler.ATTEMPT_SECONDS
UIDS = [f'owner-{n}' for n in range(400)]
CONTROLS = (
    'RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED',
    'RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE',
    'RECORD_WAL_DUPLICATE_SHADOW_EPOCH',
    'RECORD_WAL_DUPLICATE_PERCENT',
    'RECORD_WAL_HANDOFF_ENABLED',
)


@pytest.fixture
def env(monkeypatch):
    for name in CONTROLS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('K_SERVICE', 'backend-sync')

    def apply(**values):
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return apply


def test_gate_without_fence_runs_shadow_only_inside_the_window(env):
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true', RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH))
    assert mode('owner', EPOCH) == ('shadow', EPOCH // 30)
    assert mode('owner', EPOCH + 29.9) == ('shadow', EPOCH // 30)
    assert mode('owner', EPOCH + 30) == ('shadow', EPOCH // 30 + 1)
    assert mode('owner', END - 0.001) == ('shadow', (END - 1) // 30)
    for outside in (EPOCH - 1, END, END + 1, EPOCH + 14_400, EPOCH + 86_400 - 2):
        assert mode('owner', outside) == ('off', None)


def test_window_closes_attempt_seconds_before_four_hours(env):
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true', RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH))
    assert END == EPOCH + 4 * 3600 - 2
    assert mode('owner', END - 1)[0] == 'shadow'
    assert mode('owner', END) == ('off', None)


def test_window_has_exactly_480_distinct_slots(env):
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true', RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH))
    slots = {mode('owner', t)[1] for t in range(EPOCH - 60, EPOCH + 14_460)} - {None}
    assert len(slots) == 480
    assert slots == set(range(EPOCH // 30, EPOCH // 30 + 480))


@pytest.mark.parametrize('percent', ('1', '10', '50', '100', '5'))
@pytest.mark.parametrize('fence', (None, 'true'))
def test_shadow_and_percent_stay_mutually_exclusive(env, percent, fence):
    env(
        RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true',
        RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH),
        RECORD_WAL_DUPLICATE_PERCENT=percent,
    )
    if fence:
        env(RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED=fence)
    assert {mode(uid, EPOCH + 60) for uid in UIDS} == {('off', None)}


@pytest.mark.parametrize('percent', ('1', '10', '50', '100'))
def test_gate_never_reaches_settle_without_the_fence(env, percent):
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true', RECORD_WAL_DUPLICATE_PERCENT=percent)
    for fence in (None, 'false', 'TRUE', '1'):
        if fence is not None:
            env(RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED=fence)
        assert {mode(uid, time.time()) for uid in UIDS} == {('off', None)}


@pytest.mark.parametrize('value', ('false', 'TRUE', '1', 'yes', ''))
def test_gate_is_fail_closed_on_anything_but_true(env, value):
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE=value, RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH))
    assert mode('owner', EPOCH) == ('off', None)


def _bucket(uid):
    return int.from_bytes(hashlib.sha256(uid.encode()).digest()[:8], 'big') % 100


@pytest.mark.parametrize('percent', (1, 10, 50, 100))
def test_fence_without_gate_settles_the_same_owner_cohort(env, percent):
    env(RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED='true', RECORD_WAL_DUPLICATE_PERCENT=str(percent))
    decisions = {uid: mode(uid, time.time()) for uid in UIDS}
    assert decisions == {uid: ('settle', None) if _bucket(uid) < percent else ('off', None) for uid in UIDS}
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true')
    assert {uid: mode(uid, time.time()) for uid in UIDS} == decisions


def test_fence_without_gate_keeps_shadow_and_invalid_controls_off(env):
    env(RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED='true')
    assert mode('owner', EPOCH) == ('off', None)
    env(RECORD_WAL_DUPLICATE_PERCENT='5')
    assert mode('owner', EPOCH) == ('off', None)
    env(RECORD_WAL_DUPLICATE_PERCENT='0', RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH))
    assert mode('owner', EPOCH) == ('shadow', EPOCH // 30)
    env(RECORD_WAL_DUPLICATE_PERCENT='ten')
    assert mode('owner', EPOCH) == ('off', None)


@pytest.mark.parametrize('service', (None, 'backend', 'backend-sync-backfill', 'pusher'))
def test_other_services_stay_off(env, monkeypatch, service):
    env(
        RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED='true',
        RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true',
        RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH),
    )
    if service is None:
        monkeypatch.delenv('K_SERVICE')
    else:
        env(K_SERVICE=service)
    assert mode('owner', EPOCH) == ('off', None)
    monkeypatch.delenv('RECORD_WAL_DUPLICATE_SHADOW_EPOCH')
    env(RECORD_WAL_DUPLICATE_PERCENT='100')
    assert mode('owner', EPOCH) == ('off', None)


@pytest.mark.parametrize('fence', (None, 'true'))
def test_handoff_forces_off(env, fence):
    env(
        RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true',
        RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH),
        RECORD_WAL_HANDOFF_ENABLED='true',
    )
    if fence:
        env(RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED=fence)
    assert mode('owner', EPOCH) == ('off', None)


@pytest.mark.parametrize('epoch', (EPOCH + 1, EPOCH + 15, EPOCH + 29, -EPOCH, 'not-a-number'))
def test_unaligned_or_invalid_epoch_is_off(env, epoch):
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true', RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(epoch))
    start = epoch if isinstance(epoch, int) else EPOCH
    for now in (start, start + 30, EPOCH + 60):
        assert mode('owner', now) == ('off', None)


def test_shadow_constants_are_separate_and_keep_the_proof_cap():
    assert (sampler.SLOT_SECONDS, sampler.WINDOW_SECONDS, sampler.ATTEMPT_SECONDS) == (180, 86_400, 2)
    assert (SHADOW_SLOT_SECONDS, SHADOW_WINDOW_SECONDS) == (30, 14_400)
    proofs = SHADOW_WINDOW_SECONDS // SHADOW_SLOT_SECONDS
    assert proofs == 480
    # One claimed slot runs at most one ATTEMPT_SECONDS-bounded proof.
    assert sampler.ATTEMPT_SECONDS < SHADOW_SLOT_SECONDS
    prepare, finish = duplicate._views(duplicate._budget(), 'shadow')
    assert proofs * (prepare.limit + finish.limit) == 49_920
    budget = duplicate._budget()
    assert proofs * budget.max_objects == 9_600
    assert proofs * budget.max_bytes == proofs * sample.MAX_MANIFEST_TOTAL == int(7.5 * 1024**3)
    assert ledger.MAX_VIEW_READS == 52


def _content(hit_shadow, hit_sampler):
    def digest(n):
        return int(hashlib.sha256(str(n).encode()).hexdigest()[:12], 16)

    return next(
        str(n)
        for n in range(1_000_000)
        if (digest(n) % SHADOW_CONTENT_MODULUS == 0) is hit_shadow and (digest(n) % 1000 == 0) is hit_sampler
    )


def test_shadow_content_filter_scales_with_slot_length(env, monkeypatch):
    # 1000 content IDs per candidate at 180 s slots -> about 167 at 30 s, so a slot sees as many candidates.
    assert SHADOW_CONTENT_MODULUS == 167
    assert SHADOW_CONTENT_MODULUS == round(1000 * SHADOW_SLOT_SECONDS / sampler.SLOT_SECONDS)
    env(RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE='true', RECORD_WAL_DUPLICATE_SHADOW_EPOCH=str(EPOCH))
    monkeypatch.setattr(duplicate.time, 'time', lambda: EPOCH)
    assert duplicate.select('owner', _content(True, False)) == ('shadow', EPOCH // 30)
    assert duplicate.select('owner', _content(False, False)) == ('off', None)


@pytest.mark.parametrize('content', (_content(True, False), _content(False, False)))
def test_settle_ignores_the_content_filter(env, monkeypatch, content):
    env(RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED='true', RECORD_WAL_DUPLICATE_PERCENT='100')
    assert duplicate.select('owner', content) == ('settle', None)


@pytest.mark.parametrize(('shadow_hit', 'sampled'), ((True, False), (False, True)))
@pytest.mark.asyncio
async def test_sampler_keeps_its_one_in_1000_filter(monkeypatch, shadow_hit, sampled):
    monkeypatch.setattr(sample, 'slot_at', lambda now: 1)
    local = Mock(return_value=False)
    monkeypatch.setattr(sample, '_try_process_slot', local)
    monkeypatch.setattr(sample, 'attempts', Mock())
    await sample.observe(
        store=object(),
        uid='owner',
        cid='record',
        source='device',
        device='model',
        paths=[],
        content_id=_content(shadow_hit, sampled),
        claims={},
        status_code=503,
        has_jobs=True,
    )
    assert local.called is sampled
