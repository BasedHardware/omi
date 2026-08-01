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

import numpy as np  # noqa: E402

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
