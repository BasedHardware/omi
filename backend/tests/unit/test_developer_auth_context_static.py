from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_developer_api_auth_keeps_uid_dependencies_while_carrying_memory_app_key_context():
    dependencies_source = (ROOT / 'dependencies.py').read_text()

    assert 'class ApiKeyAuth' in dependencies_source
    assert 'self.uid = uid' in dependencies_source
    assert 'self.scopes = scopes' in dependencies_source
    assert 'self.app_id = app_id' in dependencies_source
    assert 'self.key_id = key_id' in dependencies_source
    assert 'return auth.uid' in dependencies_source
    assert 'def get_developer_memory_default_memory_read_context' in dependencies_source
    assert 'ProductAuthorizationContext' in dependencies_source
    assert "consumer='developer_api'" in dependencies_source
    assert "surface='developer_default_memory_read'" in dependencies_source
    assert "Scopes.MEMORIES_READ: 'memories.read'" in dependencies_source


def test_developer_api_key_lookup_returns_key_id_and_stable_app_id_for_memory_context():
    source = (ROOT / 'database' / 'dev_api_key.py').read_text()

    assert '"key_id": key_id' in source
    assert '"app_id": app_id' in source
    assert "key_data.get(\"app_id\") or \"developer_api\"" in source
    assert 'redis_db.cache_dev_api_key(hashed_key, user_id, scopes, key_id=key_id, app_id=app_id)' in source
    assert 'if cached_data.get("key_id") and cached_data.get("app_id"):' in source
    assert '# Legacy Redis entries predate app/key identity' in source
