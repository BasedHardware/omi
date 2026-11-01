"""Real HTTP/SQLite regressions for #20498 and #20213; provider network is denied.

Expected consent semantics come from #20213. Region/revocation expectations come
from docs.pcloud.com/methods/oauth_2.0/authorize.html and methods/auth/logout.html.
"""

import copy
import concurrent.futures
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
import requests
from cryptography.fernet import Fernet, MultiFernet, InvalidToken
from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2] / 'backend'))
from utils.plugin_transport import PluginTransport, authorize_app_setup

import main
import worker
from pcloud_client import PCloudClient
from provider_contract import BackupUploadResult
from store import Store

KEY = 'synthetic-test-key-at-least-32-bytes-long'
APP = 'synthetic-pcloud-app'
UID = 'synthetic-user-a'
TRANSPORT = PluginTransport(APP, 'https://pcloud.example.invalid', KEY)


def payload(identity='conversation-a', title='Same title'):
    return {
        'id': identity,
        'created_at': '2026-10-20T10:00:00Z',
        'finished_at': '2026-10-20T10:30:00Z',
        'structured': {
            'title': title,
            'overview': 'Synthetic summary',
            'category': 'work',
        },
        'transcript_segments': [
            {
                'text': 'Synthetic private transcript',
                'is_user': True,
                'start': 0,
                'end': 1,
            }
        ],
        'discarded': False,
        '_omi_backup_audio_token': TRANSPORT.token(UID, 'audio', conversation_id=identity, ttl=86400),
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('OMI_PLUGIN_SIGNING_KEY', KEY)
    monkeypatch.setenv('OMI_PLUGIN_APP_ID', APP)
    monkeypatch.setenv('PCLOUD_CLIENT_ID', 'synthetic-client')
    monkeypatch.setenv('PCLOUD_CLIENT_SECRET', 'synthetic-secret')
    monkeypatch.setenv('PCLOUD_REDIRECT_URI', 'https://pcloud.example.invalid/auth/pcloud/callback')
    key = Fernet.generate_key().decode()
    store = Store(str(tmp_path / 'pcloud.sqlite3'), [key])
    monkeypatch.setattr(main, '_store', store)
    monkeypatch.setattr(
        requests.sessions.Session,
        'request',
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Live network forbidden')),
    )
    monkeypatch.setattr(requests, 'head', lambda *args, **kwargs: SimpleNamespace(status_code=200))
    # No lifespan worker in route tests: drive its real production function explicitly.
    client = TestClient(main.app, base_url='https://pcloud.example.invalid')
    result = SimpleNamespace(store=store, client=client, monkeypatch=monkeypatch, key=key)
    yield result
    client.close()


def login(env, uid=UID, client=None):
    client = client or env.client
    result = client.get(
        '/setup/pcloud',
        params={'uid': uid, 'omi_token': TRANSPORT.token(uid, 'setup')},
        follow_redirects=False,
    )
    assert result.status_code == 303
    assert result.headers['location'] == '/setup/pcloud'
    cookie = client.cookies.get(main.COOKIE)
    principal = env.store.get('session', hashlib.sha256(cookie.encode()).hexdigest())
    return principal['csrf']


def connection(env, uid=UID):
    env.store.put(
        'connection',
        uid,
        uid,
        {
            'access_token': 'synthetic-provider-token',
            'status': 'active',
            'location_id': 1,
            'email': 'synthetic@example.invalid',
            'generation': 'generation-a',
        },
    )


def settings(env, **values):
    env.store.put(
        'settings',
        UID,
        UID,
        {
            'folder_name': 'Omi Conversations',
            'save_summary': True,
            'save_transcript': False,
            'save_audio': False,
            'consent_version': 1,
            **values,
        },
    )


def deliver(env, value=None, uid=UID, headers=None):
    value = value or payload()
    auth = (
        headers
        if headers is not None
        else TRANSPORT.delivery_headers(uid, 'https://pcloud.example.invalid/conversation', value)
    )
    return env.client.post('/conversation', params={'uid': uid}, json=value, headers=auth)


def success_provider(env):
    calls = []
    env.monkeypatch.setattr(PCloudClient, 'ensure_folder', lambda *a: (123, None))

    def upload(self, folder_ref, filename, content, overwrite=True):
        calls.append((filename, content if isinstance(content, bytes) else content.read()))
        return BackupUploadResult('id', filename, '/backup/' + filename, 1, 'now'), None

    env.monkeypatch.setattr(PCloudClient, 'upload_file', upload)
    return calls


@pytest.mark.parametrize(
    'path,method',
    [
        ('/setup/pcloud?uid=known-victim', 'get'),
        ('/auth/pcloud', 'post'),
        ('/settings', 'post'),
        ('/disconnect', 'post'),
    ],
)
def test_uid_does_not_authorize(env, path, method):
    response = (
        getattr(env.client, method)(
            path,
            data={'csrf': 'bogus', 'folder_name': 'x'} if method == 'post' else None,
        )
        if method == 'post'
        else env.client.get(path)
    )
    assert response.status_code == 401


def test_setup_grant_is_uid_bound_one_use_and_scrubbed(env):
    grant = TRANSPORT.token(UID, 'setup')
    assert env.client.get('/setup/pcloud', params={'uid': 'other', 'omi_token': grant}).status_code == 401
    response = env.client.get('/setup/pcloud', params={'uid': UID, 'omi_token': grant}, follow_redirects=False)
    assert response.status_code == 303
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    assert env.client.get('/setup/pcloud', params={'uid': UID, 'omi_token': grant}).status_code == 401
    assert env.client.get('/setup/pcloud?uid=other').status_code == 403


@pytest.mark.parametrize('scope', ['status', 'audio', 'delivery'])
def test_other_scopes_cannot_open_setup(env, scope):
    assert (
        env.client.get(
            '/setup/pcloud',
            params={'uid': UID, 'omi_token': TRANSPORT.token(UID, scope)},
        ).status_code
        == 401
    )


def test_expired_or_wrong_key_setup_denied(env):
    expired = TRANSPORT.token(UID, 'setup', ttl=-1)
    wrong = PluginTransport(APP, TRANSPORT.base_url, 'other-key-with-at-least-32-bytes!!').token(UID, 'setup')
    for token in (expired, wrong):
        assert env.client.get('/setup/pcloud', params={'uid': UID, 'omi_token': token}).status_code == 401


def test_csrf_and_account_are_bound_to_session(env):
    csrf = login(env)
    for wrong in ('bogus', '非ASCII'):
        assert env.client.post('/settings', data={'csrf': wrong, 'folder_name': 'x'}).status_code == 403
    result = env.client.post(
        '/settings?uid=victim',
        data={'csrf': csrf, 'folder_name': 'mine', 'save_summary': 'on'},
    )
    assert result.status_code == 200
    assert env.store.settings(UID)['folder_name'] == 'mine'
    assert env.store.settings('victim')['folder_name'] == 'Omi Conversations'


def test_setup_status_requires_grant_and_saved_preferences(env):
    connection(env)
    params = {'uid': UID, 'omi_token': TRANSPORT.token(UID, 'status')}
    assert env.client.get('/setup-completed', params=params).json() == {'is_setup_completed': False}
    settings(env)
    assert env.client.get('/setup-completed', params=params).json() == {'is_setup_completed': True}
    assert env.client.get('/setup-completed', params={**params, 'uid': 'other'}).status_code == 401


@pytest.mark.parametrize('region,host', [(1, 'api.pcloud.com'), (2, 'eapi.pcloud.com')])
def test_oauth_uses_documented_callback_region(env, region, host):
    csrf = login(env)
    initiation = env.client.post('/auth/pcloud', data={'csrf': csrf}, follow_redirects=False)
    state = parse_qs(urlsplit(initiation.headers['location']).query)['state'][0]
    response = SimpleNamespace(
        status_code=200,
        raise_for_status=lambda: None,
        json=lambda: {'result': 0, 'access_token': 'synthetic-oauth-token', 'uid': 123},
    )
    calls = []
    env.monkeypatch.setattr(requests, 'post', lambda url, **kw: calls.append(url) or response)
    env.monkeypatch.setattr(
        PCloudClient,
        'get_user_info',
        lambda self: ({'email': 'synthetic@example.invalid'}, None),
    )
    result = env.client.get(
        '/auth/pcloud/callback',
        params={
            'state': state,
            'code': 'synthetic-code',
            'locationid': region,
            'hostname': host,
        },
    )
    assert result.status_code == 200
    assert calls == [f'https://{host}/oauth2_token']
    saved = env.store.get('connection', UID)
    assert saved['location_id'] == region and saved['userid'] == 123
    assert env.client.get('/auth/pcloud/callback', params={'state': state, 'code': 'again'}).status_code == 400


def test_oauth_rejects_untrusted_host_and_stale_state(env):
    login(env)
    env.store.put('oauth', 'expired', UID, {'uid': UID, 'session_csrf': 'x'}, ttl=-1)
    assert env.client.get('/auth/pcloud/callback', params={'state': 'expired', 'code': 'x'}).status_code == 400
    csrf = env.store.get(
        'session',
        hashlib.sha256(env.client.cookies.get(main.COOKIE).encode()).hexdigest(),
    )['csrf']
    env.store.put('oauth', 'host', UID, {'uid': UID, 'session_csrf': csrf})
    assert (
        env.client.get(
            '/auth/pcloud/callback',
            params={
                'state': 'host',
                'code': 'x',
                'locationid': 2,
                'hostname': 'metadata.google.internal',
            },
        ).status_code
        == 400
    )


def begin_oauth(env, csrf, client=None):
    client = client or env.client
    initiation = client.post('/auth/pcloud', data={'csrf': csrf}, follow_redirects=False)
    assert initiation.status_code == 303
    return parse_qs(urlsplit(initiation.headers['location']).query)['state'][0]


def finish_oauth(env, state, client=None):
    client = client or env.client
    return client.get(
        '/auth/pcloud/callback',
        params={'state': state, 'code': f'code-{state[:6]}', 'locationid': 1, 'hostname': 'api.pcloud.com'},
    )


def synthetic_provider(env, before_exchange=None, revoke_ok=True):
    """Synthetic token endpoint: each exchange issues a distinct token; logouts are recorded."""
    issued, revoked = [], []

    def exchange(url, **kwargs):
        if before_exchange:
            before_exchange()
        issued.append(f'token-{len(issued) + 1}')
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda token=issued[-1]: {'result': 0, 'access_token': token, 'uid': 123},
        )

    env.monkeypatch.setattr(requests, 'post', exchange)
    env.monkeypatch.setattr(PCloudClient, 'get_user_info', lambda self: ({'email': 'synthetic@example.invalid'}, None))
    env.monkeypatch.setattr(
        PCloudClient, 'logout', lambda self: revoked.append(self.access_token) or ((True, None) if revoke_ok else (False, 'x'))
    )
    return issued, revoked


def test_disconnect_retires_an_older_pending_authorization(env):
    csrf = login(env)
    issued, revoked = synthetic_provider(env)
    first, second = begin_oauth(env, csrf), begin_oauth(env, csrf)
    assert finish_oauth(env, first).status_code == 200
    assert env.client.post('/disconnect', data={'csrf': csrf}).status_code == 200
    late = finish_oauth(env, second)
    assert late.status_code == 409 and 'disconnected' in late.text.lower()
    assert env.store.get('connection', UID) is None
    assert issued == ['token-1'] and revoked == ['token-1']  # the retired code is never exchanged


def test_disconnect_without_a_connection_still_retires_pending_authorization(env):
    csrf = login(env)
    issued, _ = synthetic_provider(env)
    pending = begin_oauth(env, csrf)
    assert env.client.post('/disconnect', data={'csrf': csrf}).status_code == 200
    assert finish_oauth(env, pending).status_code == 409
    assert env.store.get('connection', UID) is None and issued == []
    # A genuinely new Connect after Disconnect works.
    assert finish_oauth(env, begin_oauth(env, csrf)).status_code == 200
    assert env.store.get('connection', UID)['access_token'] == 'token-1'


@pytest.mark.parametrize('revoke_ok', [True, False])
def test_disconnect_during_token_exchange_cannot_revive_the_account(env, revoke_ok):
    csrf = login(env)
    exchanging, release = concurrent.futures.Future(), concurrent.futures.Future()

    def pause():
        if not exchanging.done():
            exchanging.set_result(True)
            release.result(timeout=10)

    issued, revoked = synthetic_provider(env, before_exchange=pause, revoke_ok=revoke_ok)
    state = begin_oauth(env, csrf)
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        pending = pool.submit(finish_oauth, env, state)
        exchanging.result(timeout=10)
        assert env.client.post('/disconnect', data={'csrf': csrf}).status_code == 200
        release.set_result(True)
        result = pending.result(timeout=10)
    assert result.status_code == 409 and 'disconnected' in result.text.lower()
    assert env.store.get('connection', UID) is None
    assert revoked == issued == ['token-1']  # the stale grant is revoked, not stored
    assert ('not confirmed' in result.text) is not revoke_ok


def test_stale_exchange_never_overwrites_a_newer_connection(env):
    csrf = login(env)
    exchanging, release = concurrent.futures.Future(), concurrent.futures.Future()

    def pause():
        if not exchanging.done():
            exchanging.set_result(True)
            release.result(timeout=10)

    issued, revoked = synthetic_provider(env, before_exchange=pause)
    stale = begin_oauth(env, csrf)
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        pending = pool.submit(finish_oauth, env, stale)
        exchanging.result(timeout=10)
        assert env.client.post('/disconnect', data={'csrf': csrf}).status_code == 200
        assert finish_oauth(env, begin_oauth(env, csrf)).status_code == 200  # new attempt issues token-1
        release.set_result(True)
        assert pending.result(timeout=10).status_code == 409  # the stale attempt then issues token-2
    assert env.store.get('connection', UID)['access_token'] == 'token-1'
    assert revoked == ['token-2']


def test_disconnect_leaves_other_accounts_and_canceled_jobs_alone(env):
    csrf = login(env)
    other = TestClient(main.app, base_url='https://pcloud.example.invalid')
    other_csrf = login(env, uid='synthetic-user-b', client=other)
    synthetic_provider(env)
    other_state = begin_oauth(env, other_csrf, client=other)
    connection(env)
    settings(env)
    assert deliver(env).status_code == 202
    assert env.client.post('/disconnect', data={'csrf': csrf}).status_code == 200
    assert finish_oauth(env, other_state, client=other).status_code == 200
    assert env.store.get('connection', 'synthetic-user-b')['status'] == 'active'
    assert finish_oauth(env, begin_oauth(env, csrf)).status_code == 200
    worker.run_next_job(env.store)
    assert [job['state'] for job in env.store.jobs(UID)] == ['canceled']
    other.close()


def test_failed_revocation_stops_exports_but_preserves_recovery_token(env):
    csrf = login(env)
    connection(env)
    deliver(env)
    env.monkeypatch.setattr(PCloudClient, 'logout', lambda self: (False, 'provider secret error'))
    result = env.client.post('/disconnect', data={'csrf': csrf})
    assert result.status_code == 502 and 'not confirmed' in result.text
    assert 'provider secret' not in result.text
    assert env.store.get('connection', UID)['status'] == 'revoke_pending'
    assert env.store.jobs(UID)[0]['state'] == 'canceled'
    assert 'files' not in env.store.jobs(UID)[0]
    assert deliver(env).status_code == 409
    env.monkeypatch.setattr(PCloudClient, 'logout', lambda self: (True, None))
    assert env.client.post('/disconnect', data={'csrf': csrf}).status_code == 200
    assert env.store.get('connection', UID) is None


def test_disconnect_preserves_completed_receipts(env):
    csrf = login(env)
    connection(env)
    deliver(env)
    success_provider(env)
    worker.run_next_job(env.store)
    before = env.store.jobs(UID)[0]
    assert before['state'] == 'completed' and before['uploaded'] == ['summary.md']
    env.monkeypatch.setattr(PCloudClient, 'logout', lambda self: (False, 'synthetic outage'))
    result = env.client.post('/disconnect', data={'csrf': csrf})
    after = env.store.jobs(UID)[0]
    assert after == before
    assert 'Completed' in result.text and '1 file saved' in result.text


def test_disconnect_scrubs_partial_payload_but_keeps_saved_file_receipts(env):
    csrf = login(env)
    connection(env)
    settings(env, save_transcript=True)
    deliver(env)
    identity, uid, lease, job = env.store.claim()
    job['uploaded'] = ['summary.md']
    env.store.settle(identity, uid, lease, job, 'failed')
    env.monkeypatch.setattr(PCloudClient, 'logout', lambda self: (True, None))
    env.client.post('/disconnect', data={'csrf': csrf})
    after = env.store.jobs(UID)[0]
    assert after['state'] == 'canceled' and after['uploaded'] == ['summary.md']
    assert after['title'] == 'Same title'
    assert not {'files', 'audio_token', 'authorization_token'} & after.keys()


@pytest.mark.parametrize('tamper', ['body', 'uid', 'scope', 'none'])
def test_delivery_signature_covers_identity_and_content(env, tamper):
    connection(env)
    value = payload()
    headers = TRANSPORT.delivery_headers(UID, 'https://pcloud.example.invalid/conversation', value)
    uid = UID
    if tamper == 'body':
        value['structured']['overview'] = 'tampered'
    elif tamper == 'uid':
        uid = 'other'
    elif tamper == 'scope':
        headers = {'X-Omi-Plugin-Authorization': TRANSPORT.token(UID, 'setup')}
    else:
        headers = {}
    assert deliver(env, value, uid=uid, headers=headers).status_code == 401
    assert env.store.jobs(UID) == []


def test_legacy_missing_consent_does_not_export_or_store_sensitive_content(env):
    connection(env)
    env.store.put('settings', UID, UID, {'save_transcript': True, 'save_audio': True})
    response = deliver(env)
    assert response.status_code == 202
    job = env.store.jobs(UID)[0]
    assert list(job['files']) == ['summary.md'] and job['audio_token'] is None
    assert 'Synthetic private transcript' not in json.dumps(job)
    calls = success_provider(env)
    assert worker.run_next_job(env.store)
    assert [name for name, _ in calls] == ['summary.md']
    assert env.store.jobs(UID)[0]['state'] == 'completed'


def test_discard_and_uid_audio_never_create_cross_conversation_buffers(env):
    connection(env)
    value = payload()
    value['discarded'] = True
    assert deliver(env, value).json()['status'] == 'skipped'
    assert env.client.post('/audio?uid=' + UID, content=b'private').status_code == 410
    assert env.store.jobs(UID) == []


def test_distinct_conversation_identity_is_unique_but_retries_are_not(env):
    connection(env)
    a = deliver(env).json()['backup_id']
    again = deliver(env, payload(title='Changed title')).json()['backup_id']
    b = deliver(env, payload('conversation-b')).json()['backup_id']
    assert a == again and a != b
    jobs = env.store.jobs(UID)
    assert len(jobs) == 2 and jobs[0]['path'] != jobs[1]['path']


def test_failed_partial_upload_preserves_payload_and_resumes_only_missing_files(env):
    connection(env)
    settings(env, save_transcript=True)
    job_id = deliver(env).json()['backup_id']
    env.monkeypatch.setattr(PCloudClient, 'ensure_folder', lambda *a: (1, None))
    calls = []

    def first(self, folder_ref, filename, content, overwrite=True):
        calls.append(filename)
        return (
            (BackupUploadResult('1', filename, '/file', 1, 'now'), None)
            if filename == 'summary.md'
            else (None, 'secret provider text')
        )

    env.monkeypatch.setattr(PCloudClient, 'upload_file', first)
    worker.run_next_job(env.store)
    job = env.store.jobs(UID)[0]
    assert job['state'] == 'pending' and job['uploaded'] == ['summary.md']
    assert 'transcript.md' in job['files'] and 'secret provider text' not in job['error']
    calls = success_provider(env)
    assert env.store.retry(UID, job_id)
    worker.run_next_job(Store(str(env.store.path), [env.key]))
    assert [name for name, _ in calls] == ['transcript.md']
    done = env.store.jobs(UID)[0]
    assert done['state'] == 'completed' and done['files'] == {} and done['audio_token'] is None


def test_unfinished_backup_follows_a_destination_folder_change(env):
    connection(env)
    settings(env, save_transcript=True)
    job_id = deliver(env).json()['backup_id']
    folders = []
    env.monkeypatch.setattr(PCloudClient, 'ensure_folder', lambda self, path: (folders.append(path) or 1, None))

    def partial(self, folder_ref, filename, content, overwrite=True):
        if filename == 'summary.md':
            return BackupUploadResult('1', filename, '/file', 1, 'now'), None
        return None, 'provider failure'

    env.monkeypatch.setattr(PCloudClient, 'upload_file', partial)
    worker.run_next_job(env.store)
    assert env.store.jobs(UID)[0]['uploaded'] == ['summary.md']
    assert folders and all(path == f'/Omi Conversations/{job_id}' for path in folders)

    settings(env, save_transcript=True, folder_name='Work Notes')
    folders.clear()
    calls = success_provider(env)
    env.monkeypatch.setattr(PCloudClient, 'ensure_folder', lambda self, path: (folders.append(path) or 1, None))
    assert env.store.retry(UID, job_id)
    worker.run_next_job(env.store)

    assert folders and all(path == f'/Work Notes/{job_id}' for path in folders)
    assert sorted(name for name, _ in calls) == ['summary.md', 'transcript.md'], 'the new folder gets the whole backup'
    assert env.store.jobs(UID)[0]['state'] == 'completed'


def test_completed_backup_receipts_survive_expiry(env):
    connection(env)
    job_id = deliver(env).json()['backup_id']
    success_provider(env)
    worker.run_next_job(env.store)
    assert env.store.jobs(UID)[0]['uploaded'] == ['summary.md']
    with env.store.transaction() as conn:
        conn.execute('UPDATE jobs SET expires=? WHERE id=?', (time.time() - 1, job_id))
    assert env.store.claim() is None  # runs the expiry scrub
    done = env.store.jobs(UID)[0]
    assert done['state'] == 'completed' and done['uploaded'] == ['summary.md']


def test_failed_backups_stay_reachable_beyond_the_recent_history(env):
    failed = env.store.enqueue(UID, 'old-failed', {'generation': 'g', 'files': {}, 'audio_token': None})
    with env.store.transaction() as conn:
        conn.execute('UPDATE jobs SET state=? WHERE id=?', ('failed', failed))
    for index in range(35):
        newer = env.store.enqueue(UID, f'newer-{index}', {'generation': 'g', 'files': {}, 'audio_token': None})
        with env.store.transaction() as conn:
            conn.execute('UPDATE jobs SET state=? WHERE id=?', ('completed', newer))
    listed = env.store.jobs(UID)
    assert failed in [job['id'] for job in listed], 'an old failed backup must stay retryable from settings'
    assert len([job for job in listed if job['state'] == 'completed']) <= 30


def test_opt_out_and_relink_fence_queued_jobs(env):
    connection(env)
    settings(env, save_transcript=True)
    deliver(env)
    settings(env, save_transcript=False)
    calls = success_provider(env)
    worker.run_next_job(env.store)
    assert [name for name, _ in calls] == ['summary.md']
    deliver(env, payload('new-conversation'))
    saved = env.store.get('connection', UID)
    saved['generation'] = 'different-account-generation'
    env.store.put('connection', UID, UID, saved)
    worker.run_next_job(env.store)
    assert env.store.jobs(UID)[0]['state'] == 'canceled'


def test_store_claim_nonce_rotation_and_encryption_are_durable(env):
    connection(env)
    job_id = deliver(env).json()['backup_id']
    assert env.store.consume_nonce('nonce', UID, 900)
    assert not env.store.consume_nonce('nonce', UID, 900)
    claimed = env.store.claim()
    assert claimed[0] == job_id and env.store.claim() is None
    raw = env.store.path.read_bytes()
    assert b'synthetic-provider-token' not in raw and b'Synthetic summary' not in raw
    new_key = Fernet.generate_key()
    env.store.cipher = MultiFernet([Fernet(new_key), Fernet(env.key.encode())])
    env.store.rotate_keys()
    env.store.cipher = MultiFernet([Fernet(new_key)])
    assert env.store.get('connection', UID)['status'] == 'active'
    assert env.store.jobs(UID)[0]['id'] == job_id


def test_job_expiry_scrubs_pending_content(env):
    connection(env)
    deliver(env)
    with env.store.transaction() as conn:
        conn.execute('UPDATE jobs SET expires=?', (time.time() - 1,))
    assert env.store.claim() is None
    job = env.store.jobs(UID)[0]
    assert job['state'] == 'expired' and 'files' not in job and 'audio_token' not in job


def test_crashed_lease_reclaims_but_cannot_commit_stale_work(env):
    connection(env)
    deliver(env)
    first = env.store.claim()
    with env.store.transaction() as conn:
        conn.execute('UPDATE jobs SET due=0')
    reopened = Store(str(env.store.path), [env.key])
    second = reopened.claim()
    assert first[0] == second[0] and first[2] != second[2]
    with pytest.raises(RuntimeError):
        env.store.settle(first[0], UID, first[2], first[3], 'completed')


def test_duplicate_admission_is_atomic_across_store_instances(env):
    job = {'generation': 'a', 'files': {}, 'audio_token': None}

    def enqueue(index):
        store = Store(str(env.store.path), [env.key])
        return store.enqueue(UID, 'same-conversation', dict(job))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        identities = list(pool.map(enqueue, range(8)))
    assert len(set(identities)) == 1 and len(env.store.jobs(UID)) == 1


def test_fresh_delivery_replaces_an_expired_or_canceled_backup(env):
    first = env.store.enqueue(UID, 'conv-r', {'generation': 'old', 'files': {}, 'audio_token': None})
    with env.store.transaction() as conn:
        conn.execute('UPDATE jobs SET expires=? WHERE id=?', (time.time() - 1, first))
    assert env.store.claim() is None
    assert env.store.job_state(UID, first) == 'expired'

    again = env.store.enqueue(UID, 'conv-r', {'generation': 'new', 'files': {}, 'audio_token': None})
    assert again == first and env.store.job_state(UID, first) == 'pending'
    claimed = env.store.claim()
    assert claimed[0] == first and claimed[3]['generation'] == 'new'

    env.store.cancel_jobs(UID)
    assert env.store.job_state(UID, first) == 'canceled'
    env.store.enqueue(UID, 'conv-r', {'generation': 'reconnected', 'files': {}, 'audio_token': None})
    assert env.store.job_state(UID, first) == 'pending'


def test_completed_and_active_backups_still_deduplicate(env):
    identity = env.store.enqueue(UID, 'conv-d', {'generation': 'one', 'files': {}, 'audio_token': None})
    env.store.enqueue(UID, 'conv-d', {'generation': 'two', 'files': {}, 'audio_token': None})
    claimed = env.store.claim()
    assert claimed[3]['generation'] == 'one', 'a pending job is not replaced'
    env.store.settle(identity, UID, claimed[2], {**claimed[3], 'uploaded': ['summary.md']}, 'completed')
    env.store.enqueue(UID, 'conv-d', {'generation': 'three', 'files': {}, 'audio_token': None})
    assert env.store.job_state(UID, identity) == 'completed', 'a completed backup is never re-uploaded'


def test_backup_summary_follows_the_shared_primary_summary_vectors():
    from presentation import select_primary_summary

    vectors = json.loads(
        (Path(__file__).resolve().parents[2] / 'contracts' / 'parity' / 'conversation_summary.json').read_text()
    )
    assert vectors['cases']
    for case in vectors['cases']:
        assert select_primary_summary(case['conversation']) == case['expected'], case['id']


def test_backup_summary_uses_sections_when_the_overview_is_empty():
    from omi_plugin_sdk.models import Conversation
    from presentation import summary_markdown

    value = payload()
    value['structured']['overview'] = ''
    value['structured']['sections'] = [{'heading': 'Decisions', 'body_markdown': '- Ship the backup fix.'}]
    body = summary_markdown(Conversation.model_validate(value))
    assert '## Decisions\n\n- Ship the backup fix.' in body

    value['apps_results'] = [{'app_id': 'notes-app', 'content': 'App-written summary'}]
    assert 'App-written summary' in summary_markdown(Conversation.model_validate(value))


def test_expired_state_nonce_cannot_be_consumed(env):
    env.store.put('oauth', 'old', UID, {'uid': UID}, ttl=-1)
    assert env.store.get('oauth', 'old', consume=True) is None


def test_wrong_encryption_key_fails_readiness(env):
    env.store.check_ready()
    wrong = Store(str(env.store.path), [Fernet.generate_key().decode()])
    with pytest.raises(InvalidToken):
        wrong.check_ready()


def test_corrupt_job_is_visible_and_does_not_starve_other_jobs(env):
    connection(env)
    identity = deliver(env).json()['backup_id']
    deliver(env, payload('healthy-conversation'))
    with env.store.transaction() as conn:
        conn.execute('UPDATE jobs SET blob=? WHERE id=?', (b'corrupt-ciphertext', identity))
    assert env.store.claim() is None
    job = next(item for item in env.store.jobs(UID) if item['id'] == identity)
    assert job['state'] == 'unreadable'
    success_provider(env)
    assert worker.run_next_job(env.store)
    assert env.store.jobs(UID)[0]['state'] == 'completed'


@pytest.mark.parametrize('status', [403, 404, 503])
def test_queued_copy_stops_if_omi_access_is_no_longer_confirmed(env, status):
    connection(env)
    deliver(env)
    calls = success_provider(env)
    env.monkeypatch.setattr(requests, 'head', lambda *args, **kwargs: SimpleNamespace(status_code=status))
    worker.run_next_job(env.store)
    assert calls == [] and env.store.jobs(UID)[0]['state'] == 'pending'


def test_terminal_retry_budget_is_visible_and_can_be_retried_by_owner(env):
    connection(env)
    identity = deliver(env).json()['backup_id']
    env.monkeypatch.setattr(PCloudClient, 'ensure_folder', lambda *args: (None, 'provider error'))
    for index in range(5):
        with env.store.transaction() as conn:
            conn.execute('UPDATE jobs SET due=0')
        worker.run_next_job(env.store)
    assert env.store.jobs(UID)[0]['state'] == 'failed'
    csrf = login(env)
    assert env.client.post(f'/backups/{identity}/retry', data={'csrf': csrf}).status_code == 200
    assert env.store.jobs(UID)[0]['state'] == 'pending'
    assert env.store.retry('other-user', identity) is False


def test_completed_replay_is_not_reported_as_newly_queued(env):
    connection(env)
    deliver(env)
    success_provider(env)
    worker.run_next_job(env.store)
    result = deliver(env)
    assert result.status_code == 200 and result.json()['status'] == 'completed'


def test_setup_escapes_private_text_and_matches_saved_consent(env):
    connection(env)
    csrf = login(env)
    result = env.client.post(
        '/settings',
        data={
            'csrf': csrf,
            'folder_name': 'Folder <script>alert(1)</script>',
            'save_summary': 'on',
        },
    )
    assert result.status_code == 200
    assert '<script>' not in result.text
    assert 'name="save_transcript" checked' not in result.text
    assert 'name="save_audio" checked' not in result.text


def test_authenticated_sessions_share_one_mobile_desktop_state(env):
    csrf = login(env)
    assert (
        env.client.post(
            '/settings',
            data={
                'csrf': csrf,
                'folder_name': 'Saved From Mobile',
                'save_summary': 'on',
            },
        ).status_code
        == 200
    )
    other = TestClient(main.app, base_url='https://pcloud.example.invalid')
    try:
        login(env, client=other)
        response = other.get('/setup/pcloud')
        assert response.status_code == 200 and 'Saved From Mobile' in response.text
        assert response.headers['cache-control'] == 'no-store'
    finally:
        other.close()


@pytest.mark.parametrize(
    'url',
    [
        'http://storage.googleapis.com/file',
        'https://metadata.google.internal/file',
        'https://storage.googleapis.com.evil.invalid/file',
        'https://user:pass@storage.googleapis.com/file',
    ],
)
def test_audio_rejects_noncanonical_downloads(url):
    with pytest.raises(worker.BackupFailure):
        worker.audio_payload(url)


def test_audio_failure_retains_bound_token_and_success_uses_same_conversation(env):
    connection(env)
    settings(env, save_summary=False, save_audio=True)
    value = payload()
    value['_omi_backup_audio_token'] = TRANSPORT.token(UID, 'audio', conversation_id=value['id'], ttl=86400)
    job_id = deliver(env, value).json()['backup_id']
    calls = success_provider(env)
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {'audio_files': [{'id': 'part-one', 'status': 'pending', 'signed_url': None}]},
    )
    env.monkeypatch.setattr(requests, 'get', lambda *a, **kw: response)
    worker.run_next_job(env.store)
    job = env.store.jobs(UID)[0]
    assert job['state'] == 'pending' and job['audio_token'] == value['_omi_backup_audio_token']
    requests_seen = []

    class Download:
        status_code = 200
        headers = {'Content-Length': '4'}

        def raise_for_status(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, size):
            yield b'RIFF'

    def get(url, **kwargs):
        requests_seen.append(url)
        if '/backup-audio/' in url:
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    'audio_files': [
                        {
                            'id': 'part-one',
                            'status': 'cached',
                            'signed_url': 'https://storage.googleapis.com/synthetic/file',
                            'content_type': 'audio/wav',
                        }
                    ]
                },
            )
        return Download()

    env.monkeypatch.setattr(requests, 'get', get)
    env.store.retry(UID, job_id)
    worker.run_next_job(env.store)
    assert '/backup-audio/conversation-a' in requests_seen[0]
    assert len(calls) == 1 and calls[0][0].startswith('audio-part-one-') and calls[0][0].endswith('.wav')
    assert calls[0][1] == b'RIFF'
    assert env.store.jobs(UID)[0]['state'] == 'completed'
