import asyncio
import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Mock modules that initialize GCP clients at import time or have complex dependencies
sys.modules["database._client"] = MagicMock()
sys.modules["utils.other.storage"] = MagicMock()
sys.modules["utils.stt.pre_recorded"] = MagicMock()
sys.modules["utils.stt.speaker_embedding"] = MagicMock()
sys.modules["stripe"] = MagicMock()


class NotFound(Exception):
    pass


_google_module = sys.modules.setdefault("google", types.ModuleType("google"))
_google_cloud_module = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
_google_exceptions_module = types.ModuleType("google.cloud.exceptions")
_google_exceptions_module.NotFound = NotFound
sys.modules.setdefault("google.cloud.exceptions", _google_exceptions_module)
_google_firestore_module = types.ModuleType("google.cloud.firestore")
sys.modules.setdefault("google.cloud.firestore", _google_firestore_module)
_google_firestore_v1_module = types.ModuleType("google.cloud.firestore_v1")
_google_firestore_v1_module.FieldFilter = MagicMock()
_google_firestore_v1_module.transactional = lambda func: func
sys.modules.setdefault("google.cloud.firestore_v1", _google_firestore_v1_module)
setattr(_google_module, "cloud", _google_cloud_module)
setattr(_google_cloud_module, "exceptions", _google_exceptions_module)
setattr(_google_cloud_module, "firestore", _google_firestore_module)


import utils.speaker_sample_migration as migration


class _FakeEmbedding:
    def __init__(self, values):
        self._values = values

    def flatten(self):
        return self

    def tolist(self):
        return list(self._values)


def _run(coro):
    return asyncio.run(coro)


def test_get_migration_lock_reuses_same_key(monkeypatch):
    monkeypatch.setattr(migration, "_migration_locks", {}, raising=False)

    lock1 = _run(migration._get_migration_lock("uid-1", "person-1"))
    lock2 = _run(migration._get_migration_lock("uid-1", "person-1"))
    lock3 = _run(migration._get_migration_lock("uid-1", "person-2"))

    assert lock1 is lock2
    assert lock1 is not lock3


def test_migrate_returns_early_for_version_two(monkeypatch):
    def fail_get_person(*_args, **_kwargs):
        raise AssertionError("get_person should not be called for version >= 2")

    monkeypatch.setattr(migration.users_db, "get_person", fail_get_person)

    person = {"id": "person-1", "speech_samples_version": 2, "speech_samples": ["a.wav"]}
    result = _run(migration.migrate_person_samples_v1_to_v2("uid-1", person))

    assert result == person


def test_migrate_transient_transcription_failure_skips_updates(monkeypatch):
    person = {"id": "person-1", "speech_samples_version": 1, "speech_samples": ["a.wav"]}
    updates = []
    deletions = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(_path):
        return b"bytes"

    async def fake_verify(_audio, _rate, _expected_text=None):
        return None, False, "transcription_failed: network glitch"

    def fake_update(*_args, **_kwargs):
        updates.append((_args, _kwargs))

    def fake_delete(path):
        deletions.append(path)
        return True

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration, "verify_and_transcribe_sample", fake_verify)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)
    monkeypatch.setattr(migration, "delete_sample_from_storage", fake_delete)

    result = _run(migration.migrate_person_samples_v1_to_v2("uid-1", person))

    assert result == person
    assert updates == []
    assert deletions == []


def test_migrate_deletes_quality_failures_and_updates(monkeypatch):
    person = {"id": "person-1", "speech_samples_version": 1, "speech_samples": ["bad.wav", "good.wav"]}
    updates = []
    deletions = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(path):
        if path == "missing.wav":
            raise NotFound("missing")
        return b"bytes-" + path.encode("utf-8")

    async def fake_verify(audio_bytes, _rate, _expected_text=None):
        if audio_bytes.startswith(b"bytes-bad"):
            return None, False, "insufficient_words: 2/5"
        return "space cats unite", True, "ok"

    def fake_delete(path):
        deletions.append(path)
        return True

    def fake_extract(_bytes, _name):
        return _FakeEmbedding([0.1, 0.2])

    def fake_update(uid, person_id, samples, transcripts, version, speaker_embedding):
        updates.append(
            {
                "uid": uid,
                "person_id": person_id,
                "samples": samples,
                "transcripts": transcripts,
                "version": version,
                "speaker_embedding": speaker_embedding,
            }
        )

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration, "verify_and_transcribe_sample", fake_verify)
    monkeypatch.setattr(migration, "delete_sample_from_storage", fake_delete)
    monkeypatch.setattr(migration, "extract_embedding_from_bytes", fake_extract)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)

    result = _run(migration.migrate_person_samples_v1_to_v2("uid-1", person))

    assert deletions == ["bad.wav"]
    assert updates == [
        {
            "uid": "uid-1",
            "person_id": "person-1",
            "samples": ["good.wav"],
            "transcripts": ["space cats unite"],
            "version": 2,
            "speaker_embedding": [0.1, 0.2],
        }
    ]
    assert result["speech_samples"] == ["good.wav"]
    assert result["speech_sample_transcripts"] == ["space cats unite"]
    assert result["speech_samples_version"] == 2
    assert result["speaker_embedding"] == [0.1, 0.2]


def test_migrate_missing_sample_marks_for_deletion(monkeypatch):
    person = {
        "id": "person-1",
        "speech_samples_version": 1,
        "speech_samples": ["missing.wav", "good.wav"],
    }
    deletions = []
    updates = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(path):
        if path == "missing.wav":
            raise NotFound("missing")
        return b"bytes-" + path.encode("utf-8")

    async def fake_verify(_audio, _rate, _expected_text=None):
        return "ready to roll", True, "ok"

    def fake_delete(path):
        deletions.append(path)
        return True

    def fake_extract(_bytes, _name):
        return _FakeEmbedding([1.0])

    def fake_update(uid, person_id, samples, transcripts, version, speaker_embedding):
        updates.append(
            {
                "uid": uid,
                "person_id": person_id,
                "samples": samples,
                "transcripts": transcripts,
                "version": version,
                "speaker_embedding": speaker_embedding,
            }
        )

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration, "verify_and_transcribe_sample", fake_verify)
    monkeypatch.setattr(migration, "delete_sample_from_storage", fake_delete)
    monkeypatch.setattr(migration, "extract_embedding_from_bytes", fake_extract)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)

    result = _run(migration.migrate_person_samples_v1_to_v2("uid-1", person))

    assert deletions == ["missing.wav"]
    assert updates[0]["samples"] == ["good.wav"]
    assert updates[0]["transcripts"] == ["ready to roll"]
    assert result["speech_samples"] == ["good.wav"]


def test_migrate_transient_download_failure_skips_updates(monkeypatch):
    person = {
        "id": "person-1",
        "speech_samples_version": 1,
        "speech_samples": ["flaky.wav", "good.wav"],
    }
    updates = []
    deletions = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(path):
        if path == "flaky.wav":
            raise Exception("network hiccup")
        return b"bytes-" + path.encode("utf-8")

    async def fake_verify(_audio, _rate, _expected_text=None):
        return "all good", True, "ok"

    def fake_delete(path):
        deletions.append(path)
        return True

    def fake_update(*_args, **_kwargs):
        updates.append((_args, _kwargs))

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration, "verify_and_transcribe_sample", fake_verify)
    monkeypatch.setattr(migration, "delete_sample_from_storage", fake_delete)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)

    result = _run(migration.migrate_person_samples_v1_to_v2("uid-1", person))

    assert result == person
    assert updates == []
    assert deletions == []


# v2 -> v3 migration tests


def test_migrate_v2_to_v3_returns_early_for_version_three(monkeypatch):
    def fail_get_person(*_args, **_kwargs):
        raise AssertionError("get_person should not be called for version >= 3")

    monkeypatch.setattr(migration.users_db, "get_person", fail_get_person)

    person = {"id": "person-1", "speech_samples_version": 3, "speech_samples": ["a.wav"]}
    result = _run(migration.migrate_person_samples_v2_to_v3("uid-1", person))

    assert result == person


def test_migrate_v2_to_v3_returns_early_for_version_one(monkeypatch):
    """v2→v3 should not process v1 samples (needs v1→v2 first)."""

    def fail_get_person(*_args, **_kwargs):
        raise AssertionError("get_person should not be called for version 1")

    monkeypatch.setattr(migration.users_db, "get_person", fail_get_person)

    person = {"id": "person-1", "speech_samples_version": 1, "speech_samples": ["a.wav"]}
    result = _run(migration.migrate_person_samples_v2_to_v3("uid-1", person))

    assert result == person


def test_migrate_v2_to_v3_regenerates_embedding(monkeypatch):
    person = {
        "id": "person-1",
        "speech_samples_version": 2,
        "speech_samples": ["good.wav"],
        "speech_sample_transcripts": ["hello world"],
        "speaker_embedding": [0.1, 0.2],  # old v1 embedding
    }
    updates = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(_path):
        return b"audio-bytes"

    def fake_extract(_bytes, _name):
        return _FakeEmbedding([0.5, 0.6, 0.7])  # new v2 embedding

    def fake_update(uid, person_id, samples, transcripts, version, speaker_embedding):
        updates.append(
            {
                "uid": uid,
                "person_id": person_id,
                "samples": samples,
                "transcripts": transcripts,
                "version": version,
                "speaker_embedding": speaker_embedding,
            }
        )

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration, "extract_embedding_from_bytes", fake_extract)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)

    result = _run(migration.migrate_person_samples_v2_to_v3("uid-1", person))

    assert updates == [
        {
            "uid": "uid-1",
            "person_id": "person-1",
            "samples": ["good.wav"],
            "transcripts": ["hello world"],
            "version": 3,
            "speaker_embedding": [0.5, 0.6, 0.7],
        }
    ]
    assert result["speech_samples_version"] == 3
    assert result["speaker_embedding"] == [0.5, 0.6, 0.7]


def test_migrate_v2_to_v3_no_samples_just_updates_version(monkeypatch):
    person = {
        "id": "person-1",
        "speech_samples_version": 2,
        "speech_samples": [],
        "speech_sample_transcripts": [],
    }
    version_updates = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_update_version(_uid, _person_id, version):
        version_updates.append(version)

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_version", fake_update_version)

    result = _run(migration.migrate_person_samples_v2_to_v3("uid-1", person))

    assert version_updates == [3]
    assert result["speech_samples_version"] == 3


def test_migrate_v2_to_v3_transient_failure_skips_update(monkeypatch):
    person = {
        "id": "person-1",
        "speech_samples_version": 2,
        "speech_samples": ["flaky.wav"],
        "speech_sample_transcripts": ["text"],
    }
    updates = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(_path):
        raise Exception("network hiccup")

    def fake_update(*_args, **_kwargs):
        updates.append((_args, _kwargs))

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)

    result = _run(migration.migrate_person_samples_v2_to_v3("uid-1", person))

    assert result == person  # unchanged
    assert updates == []


def test_migrate_v2_to_v3_missing_first_sample_skips_update(monkeypatch):
    person = {
        "id": "person-1",
        "speech_samples_version": 2,
        "speech_samples": ["missing.wav"],
        "speech_sample_transcripts": ["text"],
        "speaker_embedding": [0.1, 0.2],
    }
    updates = []

    def fake_get_person(_uid, _person_id):
        return person

    def fake_download(_path):
        raise NotFound("missing")

    def fake_update(*_args, **_kwargs):
        updates.append((_args, _kwargs))

    monkeypatch.setattr(migration.users_db, "get_person", fake_get_person)
    monkeypatch.setattr(migration, "download_sample_audio", fake_download)
    monkeypatch.setattr(migration.users_db, "update_person_speech_samples_after_migration", fake_update)

    result = _run(migration.migrate_person_samples_v2_to_v3("uid-1", person))

    assert result == person
    assert updates == []


# v1 -> v3 composite migration tests


def test_migrate_v1_to_v3_chains_both_migrations(monkeypatch):
    """v1→v3 should run v1→v2 then v2→v3."""
    person_v1 = {
        "id": "person-1",
        "speech_samples_version": 1,
        "speech_samples": ["sample.wav"],
    }
    person_v2 = {
        "id": "person-1",
        "speech_samples_version": 2,
        "speech_samples": ["sample.wav"],
        "speech_sample_transcripts": ["transcribed text"],
        "speaker_embedding": [0.1, 0.2],
    }
    person_v3 = {
        "id": "person-1",
        "speech_samples_version": 3,
        "speech_samples": ["sample.wav"],
        "speech_sample_transcripts": ["transcribed text"],
        "speaker_embedding": [0.5, 0.6],
    }

    call_order = []

    async def fake_v1_to_v2(_uid, _person):
        call_order.append("v1_to_v2")
        return person_v2

    async def fake_v2_to_v3(_uid, _person):
        call_order.append("v2_to_v3")
        return person_v3

    monkeypatch.setattr(migration, "migrate_person_samples_v1_to_v2", fake_v1_to_v2)
    monkeypatch.setattr(migration, "migrate_person_samples_v2_to_v3", fake_v2_to_v3)

    result = _run(migration.migrate_person_samples_v1_to_v3("uid-1", person_v1))

    assert call_order == ["v1_to_v2", "v2_to_v3"]
    assert result["speech_samples_version"] == 3


def test_migrate_v1_to_v3_returns_early_for_version_three(monkeypatch):
    person = {"id": "person-1", "speech_samples_version": 3, "speech_samples": ["a.wav"]}
    result = _run(migration.migrate_person_samples_v1_to_v3("uid-1", person))

    assert result == person


def test_migrate_v1_to_v3_stops_if_v1_to_v2_fails(monkeypatch):
    """If v1→v2 has transient failure, v1→v3 should return without attempting v2→v3."""
    person_v1 = {
        "id": "person-1",
        "speech_samples_version": 1,
        "speech_samples": ["flaky.wav"],
    }

    async def fake_v1_to_v2(_uid, person):
        # Simulate transient failure - returns unchanged person
        return person

    async def fake_v2_to_v3(_uid, _person):
        raise AssertionError("v2_to_v3 should not be called if v1_to_v2 fails")

    monkeypatch.setattr(migration, "migrate_person_samples_v1_to_v2", fake_v1_to_v2)
    monkeypatch.setattr(migration, "migrate_person_samples_v2_to_v3", fake_v2_to_v3)

    result = _run(migration.migrate_person_samples_v1_to_v3("uid-1", person_v1))

    assert result["speech_samples_version"] == 1
