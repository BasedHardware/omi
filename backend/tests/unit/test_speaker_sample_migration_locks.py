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
