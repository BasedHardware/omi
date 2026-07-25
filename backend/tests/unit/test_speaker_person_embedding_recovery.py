"""A taught person whose stored embedding was lost must be recoverable (#10434).

extract_speaker_samples stores a person's speech sample, then extracts the speaker
embedding inside a try/except that only logs. When that extraction fails the person
keeps quality-verified samples with no embedding, and nothing ever recomputes it — so
the listen session skips them on every later session and they can never be matched,
however many times the user teaches them. The user's own profile already self-heals
through the same fallback; these pin the person side of that behaviour.

Recovery is deliberately limited to speech_samples_version >= 3 samples, which passed
verify_and_transcribe_sample when they were stored, so it restores a lost embedding
without reopening the quality gate that intentionally drops bad samples.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import numpy as np  # noqa: E402

import routers.listen.speakers as speakers_mod  # noqa: E402


class _Persistence:
    """Run persistence work inline and record it, like the real host's serialized queue."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def call(self, fn, *args, **kwargs):
        self.calls.append((getattr(fn, "__name__", str(fn)), args))
        return fn(*args, **kwargs)


def _matcher(uid: str = "u1") -> speakers_mod.SpeakerMatcher:
    host = SimpleNamespace(request=SimpleNamespace(uid=uid), persistence=_Persistence())
    return speakers_mod.SpeakerMatcher(host)


def _v3_person() -> dict:
    return {"id": "p1", "name": "Sarah", "speech_samples": ["people/u1/p1/a.wav"], "speech_samples_version": 3}


def test_recovers_a_taught_person_whose_embedding_was_lost(monkeypatch):
    vector = np.full((1, 512), 0.25, dtype=np.float32)
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: b"RIFFfake-wav")
    monkeypatch.setattr(speakers_mod, "extract_embedding_from_bytes", lambda audio, name: vector)

    persisted: dict[str, list] = {}

    def _persist(uid, person_id, embedding):
        persisted[person_id] = embedding
        return True

    monkeypatch.setattr(speakers_mod.user_db, "set_person_speaker_embedding", _persist)

    matcher = _matcher()
    recovered = asyncio.run(matcher._recover_person_embedding(_v3_person()))

    assert recovered is not None
    assert np.array_equal(recovered, vector)
    # Written back, so the next session matches from storage instead of paying for
    # extraction again — and the person stops being invisible permanently.
    assert persisted["p1"] == vector.flatten().tolist()


def test_recovered_embedding_is_usable_for_matching(monkeypatch):
    """The recovered vector must be shaped for compare_embeddings, not just non-None."""
    vector = np.full((1, 512), 0.25, dtype=np.float32)
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: b"RIFFfake-wav")
    monkeypatch.setattr(speakers_mod, "extract_embedding_from_bytes", lambda audio, name: vector)
    monkeypatch.setattr(speakers_mod.user_db, "set_person_speaker_embedding", lambda *a, **k: True)

    recovered = asyncio.run(_matcher()._recover_person_embedding(_v3_person()))

    assert speakers_mod.compare_embeddings(recovered, vector) < speakers_mod.SPEAKER_MATCH_THRESHOLD


def test_person_without_samples_is_not_recovered(monkeypatch):
    """No samples means nothing to rebuild from — return None rather than reach storage."""
    reached = []
    monkeypatch.setattr(speakers_mod, "download_sample_audio", lambda path: reached.append(path) or b"x")

    person = {"id": "p2", "name": "Alex", "speech_samples": [], "speech_samples_version": 3}

    assert asyncio.run(_matcher()._recover_person_embedding(person)) is None
    assert reached == []


def test_recovery_failure_is_contained(monkeypatch):
    """A storage/extraction failure must not break loading the other speakers."""

    def _boom(path):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(speakers_mod, "download_sample_audio", _boom)

    assert asyncio.run(_matcher()._recover_person_embedding(_v3_person())) is None
