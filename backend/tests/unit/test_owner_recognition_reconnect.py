"""Encrypted same-install handoff exercises the production live matcher and Lua."""

import asyncio
import json
import time
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis
import numpy as np
import pytest

from database import live_owner_continuity as cache
from models.transcript_segment import TranscriptSegment
from tests.unit.test_speaker_match import _live_matcher, _segment
from utils.encryption import decrypt_audio_file, encrypt_audio_chunk
from utils.live_owner_continuity import OwnerContinuity
from utils.observability.owner_recognition import OWNER_RECONNECT
from utils.speaker_assignment import process_speaker_assigned_segments

OWNER = np.array([[1.0, 0.0]], dtype=np.float32)
DEVICE = 'ios_12345678'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def redis(monkeypatch):
    client = fakeredis.FakeRedis()
    monkeypatch.setattr(cache, '_client', lambda: client)
    return client


async def connect(monkeypatch, queries, *, uid='owner', device=DEVICE, profile=OWNER, people=None):
    matcher, host, emitted = _live_matcher(monkeypatch, queries)
    host.request.uid = uid
    host.client_device_context = SimpleNamespace(client_device_id=device)
    host.state.speaker_id_enabled = True

    async def read(fn, *args, **kwargs):
        if fn is cache.authority_snapshot:
            return {conversation: {} for conversation in args[1]}
        return {}

    host.persistence = SimpleNamespace(call=AsyncMock(side_effect=read))
    matcher.continuity = OwnerContinuity(matcher)

    async def load():
        matcher.person_embeddings = {'user': {'embedding': profile.copy(), 'name': 'Owner'}}
        matcher.person_embeddings.update(people or {})

    matcher._load_profiles = AsyncMock(side_effect=load)
    await matcher.refresh_for_conversation('conversation')
    return matcher, host, emitted


async def speak(matcher, voice, seconds, *, start=0, scope='new-socket'):
    await matcher.match(voice, dict(_segment(f'{voice}-{start}', start, seconds), speaker_id_scope=scope))


def visible_owner(matcher, voice):
    rows = [TranscriptSegment(id='reply', text='Okay', start=0, end=2, speaker_id=voice, is_user=False)]
    process_speaker_assigned_segments(rows, matcher.segment_assignments, matcher.speaker_to_person)
    return rows[0].model_dump()['is_user']


async def seed(monkeypatch, voice=10, query=OWNER):
    matcher, _, _ = await connect(monkeypatch, [query])
    await speak(matcher, voice, 5, scope='old-socket')
    assert visible_owner(matcher, voice)
    return matcher


@pytest.mark.anyio
async def test_same_install_reconnect_names_new_id_with_two_fresh_seconds(monkeypatch, redis):
    first = await seed(monkeypatch)
    raw = redis.get(cache._keys('owner', DEVICE)[1])
    assert raw and redis.ttl(cache._keys('owner', DEVICE)[1]) <= cache.GAP_SECONDS
    assert b'centroid' not in raw
    assert json.loads(decrypt_audio_file(raw, 'owner'))['seconds'] == 5
    with pytest.raises(Exception):
        decrypt_audio_file(raw, 'different-account')
    before = OWNER_RECONNECT.labels(outcome='accepted', reason='accepted')._value.get()
    second, _, _ = await connect(monkeypatch, [OWNER])
    assert not second.speaker_to_person and second.continuity.donor
    await speak(second, 0, 2)
    assert visible_owner(second, 0)
    assert sum(s for _, s in second.speaker_evidence[0]) == 2
    assert OWNER_RECONNECT.labels(outcome='accepted', reason='accepted')._value.get() == before + 1
    assert not redis.get(cache._keys('owner', DEVICE)[1]), 'short accepts cannot chain handoffs'
    # Late work on the first socket cannot republish into the newer generation.
    await first.continuity.update({}, force=True)
    assert not redis.get(cache._keys('owner', DEVICE)[1])


@pytest.mark.anyio
@pytest.mark.parametrize(
    'gap,device,uid,profile',
    [
        (121, DEVICE, 'owner', OWNER),
        (0, 'ios_87654321', 'owner', OWNER),
        (0, DEVICE, 'other-account', OWNER),
        (0, DEVICE, 'owner', np.array([[0.99, 0.1]], dtype=np.float32)),
        (0, None, 'owner', OWNER),
    ],
)
async def test_gap_device_account_and_enrollment_fences(monkeypatch, redis, gap, device, uid, profile):
    await seed(monkeypatch)
    clock = time.time()
    monkeypatch.setattr(time, 'time', lambda: clock + gap)
    matcher, _, _ = await connect(monkeypatch, [OWNER], device=device, uid=uid, profile=profile)
    await speak(matcher, 0, 2)
    assert not visible_owner(matcher, 0)


@pytest.mark.anyio
@pytest.mark.parametrize('payload', [None, b'broken', encrypt_audio_chunk(b'{"v": 9}', 'owner')])
async def test_absent_corrupt_cache_keeps_normal_evidence_floor(monkeypatch, redis, payload):
    if payload is not None:
        redis.set(cache._keys('owner', DEVICE)[1], payload, ex=120)
    matcher, _, _ = await connect(monkeypatch, [OWNER, OWNER])
    await speak(matcher, 0, 2)
    assert not visible_owner(matcher, 0)
    await speak(matcher, 0, 3, start=3)
    assert visible_owner(matcher, 0)


@pytest.mark.anyio
async def test_wrong_voice_that_passes_enrollment_does_not_inherit_owner(monkeypatch, redis):
    await seed(monkeypatch, query=np.array([[0.8, 0.6]], dtype=np.float32))
    matcher, _, _ = await connect(monkeypatch, [np.array([[0.8, -0.6]], dtype=np.float32)])
    await speak(matcher, 0, 2)
    assert matcher._voice_distances[0]['user'] < 0.65
    assert not visible_owner(matcher, 0)
    assert matcher._voice_decisions[0].person_id is None


@pytest.mark.anyio
async def test_short_reconnect_never_names_non_owner_or_relaxes_print_margin(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, _, _ = await connect(monkeypatch, [OWNER], people={'peer': {'embedding': OWNER, 'name': 'Peer'}})
    await speak(matcher, 0, 2)
    assert not matcher.speaker_to_person
    assert matcher._voice_decisions[0].person_id is None


@pytest.mark.anyio
async def test_short_reconnect_joint_arbitration_withdraws_owner(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, _, emitted = await connect(monkeypatch, [OWNER, OWNER])
    await speak(matcher, 0, 2)
    assert visible_owner(matcher, 0)
    await speak(matcher, 1, 2, start=3)
    assert not visible_owner(matcher, 0) and not visible_owner(matcher, 1)
    assert any(args[0] == 0 and args[1] == '' for args in emitted)


@pytest.mark.anyio
async def test_manual_owner_reservation_blocks_reconnect(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, host, _ = await connect(monkeypatch, [OWNER])
    host.persistence.call.side_effect = None
    host.persistence.call.return_value = {'segments': {'manual': {'is_user': True}}}
    await speak(matcher, 0, 2)
    assert not visible_owner(matcher, 0)


@pytest.mark.anyio
async def test_concurrent_sockets_consume_once_and_older_writers_lose(monkeypatch, redis):
    old = await seed(monkeypatch)
    # Both open while the original socket is still alive; only one gets its
    # encrypted donor, and neither inherits an integer speaker id.
    one, two = await asyncio.gather(connect(monkeypatch, []), connect(monkeypatch, []))
    matchers = [one[0], two[0]]
    assert sum(m.continuity.donor is not None for m in matchers) == 1
    assert all(not m.speaker_to_person for m in matchers)
    await old.continuity.update({}, force=True)
    assert not redis.get(cache._keys('owner', DEVICE)[1])


@pytest.mark.anyio
async def test_manual_rejection_withdraws_cached_donor(monkeypatch, redis):
    old = await seed(monkeypatch)
    assert redis.get(cache._keys('owner', DEVICE)[1])
    await old.continuity.update({'speakers': {'10': {'rejection': {'kind': 'not_me'}}}}, force=True)
    assert not redis.get(cache._keys('owner', DEVICE)[1])


@pytest.mark.anyio
async def test_redis_failure_is_unknown_not_owner(monkeypatch):
    class Unavailable:
        def eval(self, *args):
            raise ConnectionError('offline')

    monkeypatch.setattr(cache, '_client', lambda: Unavailable())
    matcher, _, _ = await connect(monkeypatch, [OWNER])
    await speak(matcher, 0, 2)
    assert not visible_owner(matcher, 0)


@pytest.mark.anyio
async def test_idle_tick_refreshes_handoff_for_recent_mapped_speech(monkeypatch, redis):
    old = await seed(monkeypatch)
    clock, monotonic = time.time(), time.monotonic()
    monkeypatch.setattr(time, 'time', lambda: clock + 180)
    monkeypatch.setattr(time, 'monotonic', lambda: monotonic + 180)
    # This is the production transcript observation seam; mapped voices are
    # intentionally not put through the embedding queue again.
    old.observe_segment(10, 'old-socket', 'new-short-reply')
    await old.continuity.refresh()
    raw = redis.get(cache._keys('owner', DEVICE)[1])
    assert json.loads(decrypt_audio_file(raw, 'owner'))['observed_at'] == clock + 180
    new, _, _ = await connect(monkeypatch, [OWNER])
    await speak(new, 0, 2)
    assert visible_owner(new, 0)


@pytest.mark.anyio
async def test_old_observation_and_old_generation_cannot_renew_handoff(monkeypatch, redis):
    old = await seed(monkeypatch)
    raw = redis.get(cache._keys('owner', DEVICE)[1])
    generation = old._generation
    old.clear()
    await old.continuity.update({}, force=True, generation=generation)
    assert redis.get(cache._keys('owner', DEVICE)[1]) == raw
    assert not old.speaker_to_person


@pytest.mark.anyio
async def test_changed_profile_and_manual_receipt_after_open_block_short_reuse(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, _, _ = await connect(monkeypatch, [OWNER])
    matcher.person_embeddings['user']['embedding'] = np.array([[0.99, 0.1]], dtype=np.float32)
    await speak(matcher, 0, 2)
    assert not visible_owner(matcher, 0)
    assert matcher.continuity.donor is None


@pytest.mark.anyio
async def test_handoff_uses_active_owner_not_historical_epoch_maps(monkeypatch, redis):
    old = await seed(monkeypatch)
    old.host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='old-socket'))
    # Acoustically reconciled historical epochs can remain in the transcript map.
    old.speaker_to_person[11] = ('user', 'Owner')
    old._mapping_origin[11] = 'automatic'
    old._voice_scopes[11] = 'archived-socket'
    old._voice_centroids[11] = np.array([[0.8, -0.6]], dtype=np.float32)
    old.speaker_evidence[11] = [(old._voice_centroids[11], 5.0)]
    await old.continuity.update({}, force=True)
    new, _, _ = await connect(monkeypatch, [OWNER])
    await speak(new, 0, 2)
    assert visible_owner(new, 0)
    np.testing.assert_array_equal(new.continuity.donor['centroid'], [1, 0])


@pytest.mark.anyio
async def test_accepted_reconnect_owner_survives_same_scope_rollover_after_hint_expiry(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, host, _ = await connect(monkeypatch, [OWNER])
    host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='new-socket'))
    await speak(matcher, 0, 2)
    assert visible_owner(matcher, 0)
    clock, monotonic = time.time(), time.monotonic()
    monkeypatch.setattr(time, 'time', lambda: clock + 121)
    monkeypatch.setattr(time, 'monotonic', lambda: monotonic + 121)
    assert not matcher.continuity.available()
    matcher.observe_segment(0, 'new-socket', 'after-expiry')
    await matcher.continuity.refresh()
    assert visible_owner(matcher, 0), 'accepted proof survives idle revalidation after capsule expiry'

    async def read(fn, *args, **kwargs):
        return (
            {conversation: {} for conversation in args[1]}
            if fn is cache.authority_snapshot
            else {'id': 'conversation'} if fn.__name__ == 'get_conversation' else {}
        )

    host.persistence.call = AsyncMock(side_effect=read)
    matcher.note_rollover_carry(set())
    await matcher.refresh_for_conversation(
        'next', owner_carry_scope='new-socket', owner_carry_donor={'id': 'conversation'}
    )
    assert visible_owner(matcher, 0), 'cache TTL limits new-socket hints, not an accepted same-stream identity'
    assert not redis.get(cache._keys('owner', DEVICE)[1]), 'two seconds still cannot seed another socket'


@pytest.mark.anyio
async def test_completed_roster_rechecks_short_accept_even_without_rollover_candidate(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, host, emitted = await connect(monkeypatch, [OWNER, OWNER])
    await speak(matcher, 0, 2)
    host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='next-epoch'))

    async def load():
        matcher.person_embeddings['user'] = {'embedding': OWNER, 'name': 'Owner'}
        await speak(matcher, 1, 2, start=3, scope='next-epoch')
        assert visible_owner(matcher, 1), 'owner-only stage initially accepts'
        matcher.person_embeddings['peer'] = {'embedding': OWNER, 'name': 'Peer'}

    async def read(fn, *args, **kwargs):
        return (
            {conversation: {} for conversation in args[1]}
            if fn is cache.authority_snapshot
            else {'id': 'conversation'} if fn.__name__ == 'get_conversation' else {}
        )

    matcher._load_profiles = AsyncMock(side_effect=load)
    host.persistence.call = AsyncMock(side_effect=read)
    await matcher.refresh_for_conversation(
        'next', owner_carry_scope='next-epoch', owner_carry_donor={'id': 'conversation'}
    )
    assert not visible_owner(matcher, 1)
    assert not matcher.speaker_to_person, 'neither owner nor peer gets a two-second label after margin rejection'
    assert any(args[0] == 1 and args[1] == '' for args in emitted)


@pytest.mark.anyio
@pytest.mark.parametrize('first_seconds', [1, 2])
async def test_failed_short_probe_falls_back_to_five_fresh_seconds(monkeypatch, redis, first_seconds):
    await seed(monkeypatch)
    noisy = np.array([[0.2, np.sqrt(1 - 0.2**2)]], dtype=np.float32)
    queries = [noisy, noisy, OWNER] if first_seconds == 1 else [noisy, OWNER]
    matcher, host, _ = await connect(monkeypatch, queries)
    host.limits.speaker_id_min_audio = 1.0
    await speak(matcher, 0, first_seconds)
    assert not visible_owner(matcher, 0)
    if first_seconds == 1:
        assert 0 not in matcher._voice_decisions, 'one second remains pending, never a terminal rejection'
        await speak(matcher, 0, 1, start=1)
    assert matcher._voice_decisions[0].best_distance >= 0.75
    assert not visible_owner(matcher, 0)
    await speak(matcher, 0, 3, start=3)
    assert sum(seconds for _, seconds in matcher.speaker_evidence[0]) == 5
    assert visible_owner(matcher, 0), 'failed shortcut must resume ordinary five-second recognition'


@pytest.mark.anyio
@pytest.mark.parametrize('withdrawal', ['manual', 'blocked', 'generation'])
async def test_cancelled_publication_cannot_resurrect_a_later_withdrawal(monkeypatch, redis, withdrawal):
    old = await seed(monkeypatch)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    publish = cache.publish

    def delayed(uid, device, token, payload, revision):
        if payload is not None:
            entered.set()
            assert release.wait(5)
        try:
            publish(uid, device, token, payload, revision)
        finally:
            if payload is not None:
                finished.set()

    monkeypatch.setattr(cache, 'publish', delayed)
    task = asyncio.create_task(old.continuity.update({}, force=True, generation=old._generation))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        receipt = {}
        if withdrawal == 'manual':
            receipt = {'speakers': {'10': {'rejection': {'kind': 'not_me'}}}}
        elif withdrawal == 'blocked':
            old.host.request.owner_persistence_blocked = asyncio.Event()
            old.host.request.owner_persistence_blocked.set()
        else:
            old.clear()
        await old.continuity.update(receipt, force=True, generation=old._generation)
        assert not redis.get(cache._keys('owner', DEVICE)[1])
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 5)
    assert not redis.get(cache._keys('owner', DEVICE)[1]), 'late same-socket worker must lose to withdrawal'


@pytest.mark.anyio
async def test_unavailable_donor_authority_falls_back_to_normal_recognition(monkeypatch, redis):
    await seed(monkeypatch)
    matcher, host, _ = await connect(monkeypatch, [OWNER, OWNER])

    async def read(fn, *args, **kwargs):
        if fn is cache.authority_snapshot:
            raise ConnectionError('offline')
        return {}

    host.persistence.call = read
    await speak(matcher, 0, 2)
    assert not visible_owner(matcher, 0)
    assert matcher.continuity.donor is None
    await speak(matcher, 0, 3, start=3)
    assert visible_owner(matcher, 0)


@pytest.mark.anyio
async def test_retained_peer_cannot_publish_owner_or_seed_a_reconnect(monkeypatch, redis):
    winner = np.array([[0.47, -np.sqrt(1 - 0.47**2)]], dtype=np.float32)
    peer = np.array([[0.6, 0.8]], dtype=np.float32)
    opposite = np.array([[-1.0, 0.0]], dtype=np.float32)
    matcher, host, _ = await connect(
        monkeypatch, [winner, peer, opposite, OWNER, OWNER], people={'peer': {'embedding': peer, 'name': 'Peer'}}
    )
    host.receiver = SimpleNamespace(speaker_provider_epoch=SimpleNamespace(current_scope='same-scope'))
    await speak(matcher, 0, 5, scope='same-scope')
    await speak(matcher, 1, 5, start=6, scope='same-scope')
    assert matcher.speaker_to_person == {0: ('user', 'Owner'), 1: ('peer', 'Peer')}

    async def load():
        matcher.person_embeddings = {'user': {'embedding': OWNER, 'name': 'Owner'}}

    async def read(fn, *args, **kwargs):
        return (
            {conversation: {} for conversation in args[1]}
            if fn is cache.authority_snapshot
            else {'id': 'conversation'} if fn.__name__ == 'get_conversation' else {}
        )

    matcher._load_profiles = AsyncMock(side_effect=load)
    host.persistence.call = read
    await matcher.refresh_for_conversation(
        'next', owner_carry_scope='same-scope', owner_carry_donor={'id': 'conversation'}
    )
    assert not visible_owner(matcher, 1)
    await speak(matcher, 2, 5, start=20, scope='same-scope')
    assert not visible_owner(matcher, 1)
    assert not matcher.speaker_to_person
    assert not redis.get(cache._keys('owner', DEVICE)[1]), 'retained peer cannot mint a donor capsule'
    await matcher._reevaluate_loaded_owner()
    assert not visible_owner(matcher, 1), 'profile recovery must preserve competition-only authority'
    host.limits.speaker_id_min_audio = 1.0
    await speak(matcher, 1, 1, start=30, scope='same-scope')
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 1
    await matcher._reevaluate_loaded_owner()
    assert matcher._voice_distances[1]['user'] == pytest.approx(0.4)
    assert not visible_owner(matcher, 1), 'one fresh second cannot borrow old peer clips for a label'
    await speak(matcher, 1, 4, start=31, scope='same-scope')
    assert sum(seconds for _, seconds in matcher.speaker_evidence[1]) == 5
    assert visible_owner(matcher, 1), 'five independent fresh seconds can authorize ordinary recognition'
