"""Web cohort uses authenticated platform and the existing server custody contract."""

from types import SimpleNamespace

import pytest

from config import server_batch
from tests.unit.test_desktop_batch_only import capture, host


@pytest.fixture(autouse=True)
def admission_env(monkeypatch):
    monkeypatch.setenv('HOSTED_PUSHER_API_URL', 'http://pusher.invalid')
    monkeypatch.setenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true')
    monkeypatch.delenv('SERVER_BATCH_ONLY_ENABLED', raising=False)
    monkeypatch.delenv('SERVER_BATCH_ONLY_WEB_PERCENT', raising=False)
    monkeypatch.delenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', raising=False)


def web(language='en'):
    row = capture()
    row.update(client_platform='web', source='unknown', language=language)
    h = host(row)
    h.request.source, h.request.language = 'web', language
    h.language = language
    h.client_device_context = SimpleNamespace(platform='web')
    h.language_profile = SimpleNamespace(primary='en', expected=('en',), source='learned')
    h.batch_record_capture = {}
    return h, row


@pytest.mark.parametrize('percent', [None, '0', '-1', 'invalid', 'nan'])
def test_web_defaults_live_even_with_auto_at_100(monkeypatch, percent):
    if percent is not None:
        monkeypatch.setenv('SERVER_BATCH_ONLY_WEB_PERCENT', percent)
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    h, row = web('multi')
    assert not server_batch.request_eligible(h)
    assert not server_batch.eligible(row, 'owner')
    assert not server_batch.suppress_live(h)


def test_declared_web_requires_owned_capture_before_suppression(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_ONLY_WEB_PERCENT', '100')
    h, row = web()
    assert server_batch.request_eligible(h)
    # Persisted source is unknown, so admission cannot require source='web'.
    assert server_batch.eligible(row, 'owner')
    assert not server_batch.suppress_live(h)
    h.batch_record_capture = row
    assert server_batch.suppress_live(h)


@pytest.mark.parametrize('language', ['multi', 'auto', ''])
def test_auto_web_needs_auto_cohort_and_learned_supported_profile(monkeypatch, language):
    monkeypatch.setenv('SERVER_BATCH_ONLY_WEB_PERCENT', '100')
    h, row = web(language)
    assert not server_batch.request_eligible(h)
    assert not server_batch.eligible(row, 'owner')
    monkeypatch.setenv('SERVER_BATCH_ONLY_AUTO_LANGUAGE_PERCENT', '100')
    assert server_batch.request_eligible(h)
    assert server_batch.eligible(row, 'owner')
    h.batch_record_capture = row
    assert server_batch.suppress_live(h)
    h.language_profile.source = 'declared'
    assert not server_batch.suppress_live(h)
    h.language_profile.source = 'learned'
    h.language_profile.expected = ('en', 'ja')
    assert not server_batch.suppress_live(h)


def test_web_cohort_uses_stable_separate_salt(monkeypatch):
    calls = []
    monkeypatch.setenv('SERVER_BATCH_ONLY_WEB_PERCENT', '25')
    monkeypatch.setattr(server_batch, 'cohort_bucket', lambda uid, salt: calls.append((uid, salt)) or 24)
    assert server_batch.selected('owner', 'web', 'unknown')
    assert calls == [('owner', 'server_batch_web_v1')]
    monkeypatch.setattr(server_batch, 'cohort_bucket', lambda *_: 25)
    assert not server_batch.selected('owner', 'web', 'web')
    assert not server_batch.selected('', 'web', 'web')
    assert not server_batch.selected('owner', 'web', 'phone_call')


@pytest.mark.parametrize('excluded', ['private', 'byok', 'custom', 'unsupported', 'pusher'])
def test_web_exclusions_keep_live_even_with_owned_capture(monkeypatch, excluded):
    monkeypatch.setenv('SERVER_BATCH_ONLY_WEB_PERCENT', '100')
    h, row = web()
    h.batch_record_capture = row
    if excluded == 'private':
        h.private_cloud_sync_enabled = row['private_cloud_sync_enabled'] = False
    elif excluded == 'byok':
        h.server_batch_byok = True
    elif excluded == 'custom':
        h.use_custom_stt = row['uses_custom_stt'] = True
    elif excluded == 'unsupported':
        h.request.language = h.language = row['language'] = 'ja'
    else:
        h.pusher_enabled = False
    assert not server_batch.request_eligible(h)
    assert not server_batch.suppress_live(h)
    if excluded not in {'byok', 'pusher'}:
        assert not server_batch.eligible(row, 'owner')


def test_web_e2ee_cannot_reserve_batch_custody(monkeypatch):
    monkeypatch.setenv('SERVER_BATCH_ONLY_WEB_PERCENT', '100')
    _, row = web()
    row['data_protection_level'] = 'e2ee'
    assert not server_batch.eligible(row, 'owner')


def test_owned_web_survives_rollbacks_but_new_admission_stays_live(monkeypatch):
    h, row = web('multi')
    h.batch_record_capture = row
    monkeypatch.setenv('SERVER_BATCH_ONLY_ENABLED', 'false')
    assert server_batch.suppress_live(h)
    assert not server_batch.request_eligible(h)
    assert not server_batch.eligible(row, 'owner')
