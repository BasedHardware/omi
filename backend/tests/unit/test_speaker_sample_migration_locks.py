"""Migration locks must not accumulate forever in long-lived processes."""

from __future__ import annotations

import asyncio

import utils.speaker_sample_migration as migration


def test_migration_lock_is_released_after_v1_to_v2(monkeypatch):
    monkeypatch.setattr(migration, '_migration_locks', {}, raising=False)

    def fake_get_person(_uid, person_id):
        return {'id': person_id, 'speech_samples_version': 2}

    monkeypatch.setattr(migration.users_db, 'get_person', fake_get_person)

    person = {'id': 'person-1', 'speech_samples_version': 1, 'speech_samples': []}
    result = asyncio.run(migration.migrate_person_samples_v1_to_v2('uid-1', person))

    assert result['speech_samples_version'] == 2
    assert migration._migration_locks == {}
    assert migration._migration_lock_holders == {}


def test_lock_entry_survives_until_every_holder_releases(monkeypatch):
    """A finishing migration must not evict a lock another caller is still using.

    Otherwise the next caller builds a second Lock for the same person and the
    two migrations run concurrently against the same Firestore document.
    """
    monkeypatch.setattr(migration, '_migration_locks', {}, raising=False)
    monkeypatch.setattr(migration, '_migration_lock_holders', {}, raising=False)
    key = ('uid-1', 'person-1')

    async def scenario():
        first = await migration._get_migration_lock(*key)
        second = await migration._get_migration_lock(*key)
        assert second is first

        await migration._release_migration_lock(*key, first)
        assert migration._migration_locks.get(key) is first
        assert await migration._get_migration_lock(*key) is first

        await migration._release_migration_lock(*key, second)
        await migration._release_migration_lock(*key, first)

    asyncio.run(scenario())

    assert migration._migration_locks == {}
    assert migration._migration_lock_holders == {}
