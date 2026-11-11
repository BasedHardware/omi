"""Archive heartbeats renew only the request's acquired serve-cohort custody."""

from copy import deepcopy

import pytest

from config import record_seal_rules as lease
from database import record_audio, record_custody_append as custody
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_record_token_lease import NOW, PATH, ROW, TOKEN
from utils.sync import record_token_lease as request


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('RECORD_TOKEN_LEASE_MODE_SERVE_UID_SHA256S', raising=False)
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


@pytest.mark.parametrize(
    'mode,percent,acquire',
    [
        ('off', '100', False),
        ('shadow', '100', True),
        ('serve', '0', True),
        ('serve', '100', False),
        ('serve', '100', True),
    ],
)
async def test_archive_renews_only_owned_session_and_preserves_read_only_late_observation(
    world, monkeypatch, mode, percent, acquire
):
    store, clock = world
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', percent)
    state = {'uid': 'synthetic', 'cid': 'record'}
    context = request._upload.set(state)
    before = deepcopy(store.rows[PATH]['record_upload_sessions'])
    try:
        if acquire:
            await request.begin_upload('synthetic', 'record', 'own')
        owned = acquire and lease.token_lease_serving('synthetic')
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
        # The old lapsed producer still contributes the same shadow diagnostic.
        assert bool(state.get('late_observed')) is (mode != 'off')
    finally:
        request._upload.reset(context)


@pytest.mark.parametrize(
    'mode,percent,session',
    [
        ('shadow', '100', 'custody:other'),
        ('serve', '0', 'custody:other'),
        ('serve', '100', None),
        ('serve', '100', 'custody:missing'),
    ],
)
def test_custody_renewal_without_eligible_owned_target_is_read_only(world, monkeypatch, mode, percent, session):
    store, _ = world
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', percent)
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


async def test_roll_back_after_acquisition_does_not_renew_any_custody_token(world, monkeypatch):
    store, clock = world
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    state = {}
    context = request._upload.set(state)
    try:
        await request.begin_upload('synthetic', 'record', 'owned')
        before = deepcopy(store.rows)
        monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'shadow')
        clock[0] += 7200
        assert await request.archive(lambda *args: ['synthetic-archive'], 'synthetic', ['synthetic-audio'], {})
        assert store.rows == before
        assert state['late_observed']
    finally:
        request._upload.reset(context)
