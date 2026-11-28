"""Archive heartbeats renew only the request's acquired custody."""

from copy import deepcopy

import pytest
from fastapi import HTTPException

from config import record_seal_rules as lease
from database import record_audio, record_custody_append as custody
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_record_token_lease import NOW, PATH, ROW, TOKEN
from utils.sync import record_token_lease as request


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE', raising=False)
    clock = [NOW]
    monkeypatch.setattr(custody.time, 'time', lambda: clock[0])
    old = {**TOKEN, 'pod': '', 'signal_source': 'custody_append'}
    store = StrictFirestore(
        {
            ('users', 'synthetic'): {'private_cloud_sync_enabled': True},
            PATH: {
                **ROW,
                'record_audio_closed': False,
                'record_upload_sessions': {'custody:other': old, 'frame': TOKEN},
            },
        }
    )
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(record_audio, 'get_firestore_client', lambda: store)
    return store, clock


@pytest.mark.parametrize('mode', ['off', 'serve'])
@pytest.mark.parametrize('acquire', [False, True])
async def test_archive_renews_only_owned_session_and_preserves_read_only_late_observation(
    world, monkeypatch, mode, acquire
):
    store, clock = world
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    # custody_upload starts every request unbound; a preset target means admission
    # already bound it (and begin found no fence to acquire, i.e. not owned).
    state = {} if acquire else {'uid': 'synthetic', 'cid': 'record'}
    context = request._upload.set(state)
    before = deepcopy(store.rows[PATH]['record_upload_sessions'])
    try:
        if acquire and mode == 'off':
            # Killed admission refuses before it can mint or renew any fence.
            with pytest.raises(HTTPException) as refused:
                await request.begin_upload('synthetic', 'record', 'own')
            assert refused.value.status_code == 503
            assert 'session' not in state
            assert store.rows[PATH]['record_upload_sessions'] == before
            assert not any(tx.has_written for tx in store.transactions)
            return
        if acquire:
            await request.begin_upload('synthetic', 'record', 'own')
        owned = acquire
        assert bool(state.get('session')) is owned
        clock[0] += lease.custody_token_lease_seconds() / 2 + 1
        archived = await request.archive(
            lambda uid, paths, metadata: ['synthetic-archive'], 'synthetic', ['synthetic-audio'], {}
        )
        assert archived == ['synthetic-archive']
        after = store.rows[PATH]['record_upload_sessions']
        assert after['custody:other'] == before['custody:other']
        assert after['frame'] == before['frame']
        if owned:
            assert after['custody:own']['last_signal_at'] == clock[0]
            assert after['custody:own']['lease_expires_at'] == clock[0] + lease.custody_token_lease_seconds()
        else:
            assert after == before
            assert not any(tx.has_written for tx in store.transactions)
        # The old lapsed producer still contributes the same late observation.
        assert state.get('late_observed') is True
    finally:
        request._upload.reset(context)


@pytest.mark.parametrize('session', [None, 'custody:missing'])
def test_custody_renewal_without_eligible_owned_target_is_read_only(world, session):
    store, _ = world
    before = deepcopy(store.rows)
    observed = {}
    assert not record_audio.renew_record_token_lease(
        'synthetic',
        'record',
        source='custody_append',
        session=session,
        late_observation=observed,
        firestore_client=store,
    )
    assert observed == {'late': True}
    assert store.rows == before
    assert not store.transactions[-1].has_written


async def test_kill_after_acquisition_keeps_renewing_only_the_owned_fence(world, monkeypatch):
    store, clock = world
    state = {}
    context = request._upload.set(state)
    try:
        await request.begin_upload('synthetic', 'record', 'owned')
        before = deepcopy(store.rows[PATH]['record_upload_sessions'])
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'off')
        clock[0] += 7200
        assert await request.archive(lambda *args: ['synthetic-archive'], 'synthetic', ['synthetic-audio'], {})
        # A fence acquired before the kill keeps holding the seal; it is
        # renewed by its own append and never released early.
        after = store.rows[PATH]['record_upload_sessions']
        assert after['custody:owned']['last_signal_at'] == clock[0]
        assert after['custody:other'] == before['custody:other']
        assert after['frame'] == before['frame']
        assert state['late_observed']
    finally:
        request._upload.reset(context)
