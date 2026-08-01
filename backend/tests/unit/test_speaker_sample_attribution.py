"""An LLM-inferred enrolment must not be able to resurrect itself.

The resolution pass enrols voiceprints from identities a model inferred, and tags
the embedding `llm_inferred` so a wrong inference can be undone by clearing it.
Clearing the embedding is not enough on its own: extract_speaker_samples stores
the speech sample first, at speech_samples_version 3, and SpeakerMatcher rebuilds
a missing embedding from samples[0] for exactly those samples (#10453). The
sample left behind therefore rebuilds the cleared embedding on the next listen
session. These pin the three halves of the fix: the sample carries the
attribution, recovery refuses an inferred sample, and revoking removes both
artifacts. The user-taught self-heal path must keep working untouched.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

import database.users as users_db  # noqa: E402
import routers.listen.speakers as speakers_mod  # noqa: E402

INFERRED = users_db.SPEECH_SAMPLE_ATTRIBUTION_LLM_INFERRED
INFERRED_FIELD = users_db.LLM_INFERRED_SPEECH_SAMPLES_FIELD


class _Persistence:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def call(self, fn, *args, **kwargs):
        self.calls.append((getattr(fn, "__name__", str(fn)), args))
        return fn(*args, **kwargs)


def _matcher(uid: str = "u1") -> speakers_mod.SpeakerMatcher:
    host = SimpleNamespace(request=SimpleNamespace(uid=uid), persistence=_Persistence())
    return speakers_mod.SpeakerMatcher(host)


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _PersonRef:
    """Stands in for a Firestore document reference inside a transaction."""

    def __init__(self, data):
        self.data = data

    def get(self, transaction=None):
        return _Snapshot(self.data)


class _Transaction:
    def __init__(self):
        self.updates: list[dict] = []

    def update(self, ref, data):
        self.updates.append(data)
        ref.data.update(data)


def _add(person_ref, path, transcript=None, max_samples=5, attribution=None):
    transaction = _Transaction()
    ok = users_db._add_sample_transaction.to_wrap(transaction, person_ref, path, transcript, max_samples, attribution)
    return ok, transaction


def _remove(person_ref, path):
    transaction = _Transaction()
    ok = users_db._remove_sample_transaction.to_wrap(transaction, person_ref, path)
    return ok, transaction


def test_attribution_values_agree_across_layers():
    """speaker_identification cannot import the DB constants without a cycle, so pin them."""
    import utils.speaker_identification as speaker_identification

    assert speaker_identification.SPEAKER_ATTRIBUTION_LLM_INFERRED == INFERRED
    assert speaker_identification.SPEAKER_ATTRIBUTION_USER_TAGGED == users_db.SPEECH_SAMPLE_ATTRIBUTION_USER_TAGGED


def test_inferred_sample_is_marked_on_the_person():
    person_ref = _PersonRef({})

    ok, transaction = _add(person_ref, "people/u1/p1/a.wav", transcript="hello there", attribution=INFERRED)

    assert ok
    assert transaction.updates[0][INFERRED_FIELD] == ["people/u1/p1/a.wav"]


def test_user_tagged_sample_is_not_marked_inferred():
    person_ref = _PersonRef({})

    ok, transaction = _add(person_ref, "people/u1/p1/a.wav", transcript="hello there", attribution="user_tagged")

    assert ok
    assert INFERRED_FIELD not in transaction.updates[0]
    assert not users_db.is_person_speech_sample_llm_inferred(person_ref.data, "people/u1/p1/a.wav")


def test_marking_does_not_disturb_transcript_alignment():
    """The inferred marks are path-keyed, so the parallel arrays stay index-aligned."""
    person_ref = _PersonRef({})

    _add(person_ref, "a.wav")
    _add(person_ref, "b.wav", transcript="second", attribution=INFERRED)
    _add(person_ref, "c.wav", transcript="third")

    assert person_ref.data['speech_samples'] == ["a.wav", "b.wav", "c.wav"]
    assert person_ref.data['speech_sample_transcripts'] == ["", "second", "third"]
    assert person_ref.data[INFERRED_FIELD] == ["b.wav"]

    _remove(person_ref, "b.wav")

    assert person_ref.data['speech_samples'] == ["a.wav", "c.wav"]
    assert person_ref.data['speech_sample_transcripts'] == ["", "third"]
    assert person_ref.data[INFERRED_FIELD] == []


def test_removing_a_sample_drops_its_inferred_mark():
    person_ref = _PersonRef({})
    _add(person_ref, "a.wav", transcript="one", attribution=INFERRED)

    ok, transaction = _remove(person_ref, "a.wav")

    assert ok
    assert transaction.updates[0][INFERRED_FIELD] == []


def _v3_person(inferred: bool) -> dict:
    person = {
        "id": "p1",
        "name": "Sarah",
        "speech_samples": ["people/u1/p1/a.wav"],
        "speech_samples_version": 3,
    }
    if inferred:
        person[INFERRED_FIELD] = ["people/u1/p1/a.wav"]
    return person


def test_inferred_sample_is_not_used_to_rebuild_an_embedding(monkeypatch):
    """The whole point: a cleared inferred embedding must stay cleared."""
    reached: list[str] = []
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: reached.append(path) or b"RIFF")
    monkeypatch.setattr(
        speakers_mod, "extract_embedding_from_bytes", lambda audio, name: np.full((1, 512), 0.25, dtype=np.float32)
    )
    monkeypatch.setattr(speakers_mod.user_db, "set_person_speaker_embedding", lambda *a, **k: True)

    matcher = _matcher()
    recovered = asyncio.run(matcher._recover_person_embedding(_v3_person(inferred=True)))

    assert recovered is None
    assert reached == []
    assert matcher.host.persistence.calls == []


def test_user_taught_sample_is_still_rebuilt(monkeypatch):
    """#10453 self-heal is untouched for samples the user taught."""
    vector = np.full((1, 512), 0.25, dtype=np.float32)
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: b"RIFF")
    monkeypatch.setattr(speakers_mod, "extract_embedding_from_bytes", lambda audio, name: vector)
    monkeypatch.setattr(speakers_mod.user_db, "set_person_speaker_embedding", lambda *a, **k: True)

    recovered = asyncio.run(_matcher()._recover_person_embedding(_v3_person(inferred=False)))

    assert recovered is not None
    assert np.array_equal(recovered, vector)


def test_a_persons_other_inferred_sample_does_not_block_a_taught_one(monkeypatch):
    """Only the sample recovery would actually read decides, not the person overall."""
    vector = np.full((1, 512), 0.25, dtype=np.float32)
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: b"RIFF")
    monkeypatch.setattr(speakers_mod, "extract_embedding_from_bytes", lambda audio, name: vector)
    monkeypatch.setattr(speakers_mod.user_db, "set_person_speaker_embedding", lambda *a, **k: True)

    person = _v3_person(inferred=False)
    person["speech_samples"] = ["taught.wav", "guessed.wav"]
    person[INFERRED_FIELD] = ["guessed.wav"]

    assert asyncio.run(_matcher()._recover_person_embedding(person)) is not None


def test_revoking_removes_both_the_sample_and_the_embedding(monkeypatch):
    store = {
        "id": "p1",
        "speech_samples": ["taught.wav", "guessed.wav"],
        "speech_sample_transcripts": ["one", "two"],
        "speech_samples_version": 3,
        "speaker_embedding": [0.1, 0.2],
        "speaker_embedding_attribution": INFERRED,
        INFERRED_FIELD: ["guessed.wav"],
    }

    def _get_person(uid, person_id):
        return dict(store)

    def _remove_sample(uid, person_id, path):
        if path not in store["speech_samples"]:
            return False
        idx = store["speech_samples"].index(path)
        store["speech_samples"].pop(idx)
        store["speech_sample_transcripts"].pop(idx)
        store[INFERRED_FIELD] = [p for p in store[INFERRED_FIELD] if p != path]
        return True

    def _clear_embedding(uid, person_id):
        store.pop("speaker_embedding", None)
        store.pop("speaker_embedding_attribution", None)
        return True

    monkeypatch.setattr(users_db, "get_person", _get_person)
    monkeypatch.setattr(users_db, "remove_person_speech_sample", _remove_sample)
    monkeypatch.setattr(users_db, "clear_person_speaker_embedding", _clear_embedding)

    removed = users_db.clear_person_llm_inferred_enrolment("u1", "p1")

    assert removed == ["guessed.wav"]
    assert store["speech_samples"] == ["taught.wav"]
    assert store["speech_sample_transcripts"] == ["one"]
    assert "speaker_embedding" not in store
    assert store[INFERRED_FIELD] == []


def test_a_leading_inferred_sample_does_not_block_a_later_taught_one(monkeypatch):
    """Recovery reads the first sample it is allowed to trust, not merely the first sample."""
    vector = np.full((1, 512), 0.25, dtype=np.float32)
    read: list[str] = []
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: read.append(path) or b"RIFF")
    monkeypatch.setattr(speakers_mod, "extract_embedding_from_bytes", lambda audio, name: vector)
    monkeypatch.setattr(speakers_mod.user_db, "set_person_speaker_embedding", lambda *a, **k: True)

    person = _v3_person(inferred=False)
    person["speech_samples"] = ["guessed.wav", "taught.wav"]
    person[INFERRED_FIELD] = ["guessed.wav"]

    assert asyncio.run(_matcher()._recover_person_embedding(person)) is not None
    assert read == ["taught.wav"]


def test_revoking_keeps_an_embedding_the_user_later_confirmed(monkeypatch):
    """A newer user-tagged voiceprint outlives the revocation of an older inference."""
    store = {
        "id": "p1",
        "speech_samples": ["guessed.wav", "taught.wav"],
        "speech_sample_transcripts": ["one", "two"],
        "speech_samples_version": 3,
        "speaker_embedding": [0.1, 0.2],
        "speaker_embedding_attribution": users_db.SPEECH_SAMPLE_ATTRIBUTION_USER_TAGGED,
        INFERRED_FIELD: ["guessed.wav"],
    }
    cleared: list[str] = []

    def _remove_sample(uid, person_id, path):
        idx = store["speech_samples"].index(path)
        store["speech_samples"].pop(idx)
        store["speech_sample_transcripts"].pop(idx)
        store[INFERRED_FIELD] = [p for p in store[INFERRED_FIELD] if p != path]
        return True

    monkeypatch.setattr(users_db, "get_person", lambda uid, person_id: dict(store))
    monkeypatch.setattr(users_db, "remove_person_speech_sample", _remove_sample)
    monkeypatch.setattr(users_db, "clear_person_speaker_embedding", lambda uid, pid: cleared.append(pid) or True)

    removed = users_db.clear_person_llm_inferred_enrolment("u1", "p1")

    assert removed == ["guessed.wav"]
    assert store["speech_samples"] == ["taught.wav"]
    assert cleared == []
    assert store["speaker_embedding"] == [0.1, 0.2]


def test_revoking_leaves_a_person_with_no_inferred_samples_alone(monkeypatch):
    """A user-taught person must not lose their voiceprint to a revoke call."""
    cleared: list[str] = []
    monkeypatch.setattr(
        users_db, "get_person", lambda uid, person_id: {"id": person_id, "speech_samples": ["taught.wav"]}
    )
    monkeypatch.setattr(users_db, "remove_person_speech_sample", lambda *a: True)
    monkeypatch.setattr(users_db, "clear_person_speaker_embedding", lambda uid, pid: cleared.append(pid) or True)

    assert users_db.clear_person_llm_inferred_enrolment("u1", "p1") == []
    assert cleared == []


def _enrolment_pipeline(monkeypatch, *, embedding):
    """Stand up the storage/transcription pipeline extract_speaker_samples writes through."""
    import utils.speaker_identification as speaker_identification

    written: dict[str, Any] = {}

    async def _verify(wav_bytes, sample_rate, expected_text):
        return "spoken words", True, ""

    monkeypatch.setattr(users_db, "get_person", lambda uid, person_id: None)
    monkeypatch.setattr(users_db, "get_person_speech_samples_count", lambda uid, person_id: 0)
    monkeypatch.setattr(
        speaker_identification.conversations_db,
        "get_conversation",
        lambda uid, conversation_id: {
            "started_at": 1000.0,
            "transcript_segments": [{"id": "s1", "start": 0.0, "end": 20.0, "text": "hi", "speaker_id": 0}],
            "audio_files": [{"chunk_timestamps": [1000.0]}],
        },
    )
    monkeypatch.setattr(speaker_identification, "download_audio_chunks_and_merge", lambda *a, **k: b"")
    monkeypatch.setattr(speaker_identification, "_trim_pcm_audio", lambda *a: b"\x00" * 320000)
    monkeypatch.setattr(speaker_identification, "verify_and_transcribe_sample", _verify)
    monkeypatch.setattr(
        speaker_identification, "upload_person_speech_sample_from_bytes", lambda *a: "people/u1/p1/a.wav"
    )
    monkeypatch.setattr(speaker_identification, "extract_embedding_from_bytes", lambda wav_bytes, name: embedding())

    def _add(uid, person_id, path, transcript=None, attribution=None):
        written["sample"] = (path, attribution)
        return True

    def _set_embedding(uid, person_id, vector, attribution=None):
        written["embedding"] = attribution
        return True

    monkeypatch.setattr(users_db, "add_person_speech_sample", _add)
    monkeypatch.setattr(users_db, "set_person_speaker_embedding", _set_embedding)
    return speaker_identification, written


def _extract(module, **overrides):
    kwargs = {
        "uid": "u1",
        "person_id": "p1",
        "conversation_id": "c1",
        "segment_ids": ["s1"],
        "attribution": INFERRED,
    }
    kwargs.update(overrides)
    return asyncio.run(module.extract_speaker_samples(**kwargs))


def test_enrolment_that_stored_both_artifacts_is_reported_enrolled(monkeypatch):
    module, written = _enrolment_pipeline(monkeypatch, embedding=lambda: np.full((1, 8), 0.25, dtype=np.float32))

    assert _extract(module) is module.SpeakerEnrolmentOutcome.ENROLLED
    assert written["sample"] == ("people/u1/p1/a.wav", INFERRED)
    assert written["embedding"] == INFERRED


def test_enrolment_that_wrote_nothing_is_reported_skipped(monkeypatch):
    """Success used to mean 'did not raise', so a person with no audio counted as enrolled."""
    module, written = _enrolment_pipeline(monkeypatch, embedding=lambda: np.full((1, 8), 0.25, dtype=np.float32))
    monkeypatch.setattr(users_db, "get_person_speech_samples_count", lambda uid, person_id: 1)

    assert _extract(module) is module.SpeakerEnrolmentOutcome.SKIPPED
    assert written == {}


def test_a_sample_stored_without_its_embedding_raises_so_it_can_be_rolled_back(monkeypatch):
    """The stuck case: the inferred sample exists and recovery refuses to rebuild from it."""

    def _boom():
        raise RuntimeError("embedding backend down")

    module, written = _enrolment_pipeline(monkeypatch, embedding=_boom)

    with pytest.raises(module.SpeakerEnrolmentError):
        _extract(module)
    assert written["sample"] == ("people/u1/p1/a.wav", INFERRED)
    assert "embedding" not in written


def test_revoking_deletes_the_sample_objects_it_removed(monkeypatch):
    """Dropping the Firestore reference alone would orphan the revoked audio in the bucket."""
    import utils.speaker_identification as speaker_identification

    deleted: list[tuple] = []
    monkeypatch.setattr(
        users_db, "clear_person_llm_inferred_enrolment", lambda uid, person_id: ["people/u1/p1/guessed.wav"]
    )
    monkeypatch.setattr(
        speaker_identification,
        "delete_user_person_speech_sample",
        lambda uid, person_id, file_name: deleted.append((uid, person_id, file_name)),
    )

    removed = asyncio.run(speaker_identification.revoke_inferred_speaker_enrolment("u1", "p1"))

    assert removed == ["people/u1/p1/guessed.wav"]
    assert deleted == [("u1", "p1", "guessed.wav")]


def test_a_storage_deletion_failure_does_not_fail_the_revocation(monkeypatch):
    """Firestore has already dropped the reference by then; a stuck object is the lesser loss."""
    import utils.speaker_identification as speaker_identification

    def _boom(uid, person_id, file_name):
        raise RuntimeError("bucket unavailable")

    monkeypatch.setattr(users_db, "clear_person_llm_inferred_enrolment", lambda uid, person_id: ["a/b/c.wav"])
    monkeypatch.setattr(speaker_identification, "delete_user_person_speech_sample", _boom)

    assert asyncio.run(speaker_identification.revoke_inferred_speaker_enrolment("u1", "p1")) == ["a/b/c.wav"]
