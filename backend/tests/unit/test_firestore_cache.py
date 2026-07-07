import json
from datetime import datetime, timezone

from database import firestore_cache as fc


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.get_calls = 0
        self.set_calls = 0
        self.delete_calls = 0
        self.fail_get = False
        self.fail_set = False

    def get(self, key):
        self.get_calls += 1
        if self.fail_get:
            raise RuntimeError('redis get failed')
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.set_calls += 1
        if self.fail_set:
            raise RuntimeError('redis set failed')
        self.store[key] = value
        return True

    def delete(self, key):
        self.delete_calls += 1
        self.store.pop(key, None)
        return 1


def test_cache_disabled_fetches_every_time(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(fc, 'r', fake)
    monkeypatch.delenv('FIRESTORE_CACHE_ENABLED', raising=False)
    monkeypatch.delenv('FIRESTORE_CACHE_TEST_PROJECTION_ENABLED', raising=False)

    policy = fc.CachePolicy(namespace='test_projection', ttl_seconds=60)
    calls = {'count': 0}

    def fetch():
        calls['count'] += 1
        return {'value': calls['count']}

    assert fc.get_or_fetch(policy, 'uid_1', fetch) == {'value': 1}
    assert fc.get_or_fetch(policy, 'uid_1', fetch) == {'value': 2}
    assert calls['count'] == 2
    assert fake.get_calls == 0
    assert fake.set_calls == 0


def test_cache_enabled_populates_and_hits(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(fc, 'r', fake)
    monkeypatch.setenv('FIRESTORE_CACHE_ENABLED', 'true')
    monkeypatch.delenv('FIRESTORE_CACHE_TEST_PROJECTION_ENABLED', raising=False)

    policy = fc.CachePolicy(namespace='test_projection', ttl_seconds=60, jitter_ratio=0)
    calls = {'count': 0}

    def fetch():
        calls['count'] += 1
        return {'value': 'from-firestore'}

    assert fc.get_or_fetch(policy, 'uid_1', fetch) == {'value': 'from-firestore'}
    assert fc.get_or_fetch(policy, 'uid_1', fetch) == {'value': 'from-firestore'}
    assert calls['count'] == 1
    assert fake.get_calls == 2
    assert fake.set_calls == 1

    key = fc.make_cache_key(policy, 'uid_1')
    envelope = json.loads(fake.store[key])
    assert envelope['v'] == policy.version
    assert envelope['kind'] == 'value'
    assert envelope['payload'] == {'value': 'from-firestore'}


def test_redis_get_failure_falls_back_to_fetch(monkeypatch):
    fake = FakeRedis()
    fake.fail_get = True
    monkeypatch.setattr(fc, 'r', fake)
    monkeypatch.setenv('FIRESTORE_CACHE_ENABLED', 'true')

    policy = fc.CachePolicy(namespace='test_projection', ttl_seconds=60)

    assert fc.get_or_fetch(policy, 'uid_1', lambda: {'value': 'fallback'}) == {'value': 'fallback'}


def test_cache_round_trips_datetime_payloads(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(fc, 'r', fake)
    monkeypatch.setenv('FIRESTORE_CACHE_ENABLED', 'true')

    policy = fc.CachePolicy(namespace='test_projection', ttl_seconds=60, jitter_ratio=0)
    stamp = datetime(2026, 6, 14, 22, 0, tzinfo=timezone.utc)
    calls = {'count': 0}

    def fetch():
        calls['count'] += 1
        return {'custom_stt_since': stamp}

    assert fc.get_or_fetch(policy, 'uid_1', fetch) == {'custom_stt_since': stamp}
    assert fc.get_or_fetch(policy, 'uid_1', fetch) == {'custom_stt_since': stamp}
    assert calls['count'] == 1


def test_cache_key_includes_namespace_version_and_encoded_entity_id(monkeypatch):
    monkeypatch.setenv('FIRESTORE_CACHE_GLOBAL_VERSION', '1')
    policy = fc.CachePolicy(namespace='user_language', version=3)
    key = fc.make_cache_key(policy, 'uid:abc')

    assert key.startswith('fs:v')
    assert ':user_language:v3:b64:' in key
    assert key.endswith('dWlkOmFiYw')


def test_cache_key_entity_encoding_is_collision_free(monkeypatch):
    monkeypatch.setenv('FIRESTORE_CACHE_GLOBAL_VERSION', '1')
    policy = fc.CachePolicy(namespace='user_language', version=3)

    assert fc.make_cache_key(policy, 'a:b') != fc.make_cache_key(policy, 'a_b')


def test_users_module_only_wires_safe_projection_caches():
    source = open('database/users.py').read()

    assert "namespace='user_language'" in source
    assert "namespace='user_transcription_prefs'" in source
    assert "namespace='user_ai_profile'" in source

    forbidden_sections = [
        'def get_user_subscription',
        'def get_user_valid_subscription',
        'def get_byok_state',
        'def get_data_protection_level',
        'def get_user_private_cloud_sync_enabled',
        'def get_user_training_data_opt_in',
    ]
    for section in forbidden_sections:
        start = source.find(section)
        assert start != -1, f'missing expected section {section}'
        next_def = source.find('\ndef ', start + 1)
        block = source[start : next_def if next_def != -1 else len(source)]
        assert 'get_or_fetch(' not in block, f'{section} must not use projection cache in PR #29'


def test_ai_profile_update_bypasses_cached_getter_for_merge_safety():
    source = open('database/users.py').read()
    start = source.find('def update_ai_user_profile')
    assert start != -1
    next_def = source.find('\ndef ', start + 1)
    block = source[start : next_def if next_def != -1 else len(source)]

    assert '_get_ai_user_profile_from_firestore(uid)' in block
    assert 'get_ai_user_profile(uid)' not in block


def test_listen_reuses_transcription_projection_language_without_second_user_read():
    source = open('routers/transcribe.py').read()

    assert source.count('get_user_transcription_preferences(uid)') == 1
    assert "transcription_prefs.get('language', '')" in source
    assert 'get_user_language_preference' not in source
