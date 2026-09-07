"""Speaker-sample verification must not silently default to English (#12899).

extract_speaker_samples() runs while the conversation is still live, before
finalization resolves conversation['language'] — so that field is normally empty
at sample-extraction time. PR #12901 threaded a language kwarg through to
Deepgram but sourced it from conversation['language'], which is still empty in
this live path, so verification kept transcribing in English and rejecting
every non-English sample. This pins the fallback to the user's app-level
language preference, the same source chat/memories/process_conversation use.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import asyncio  # noqa: E402

import numpy as np  # noqa: E402

import utils.speaker_identification as speaker_identification_mod  # noqa: E402

SAMPLE_RATE = 16000


def _conversation(language):
    return {
        'started_at': 1700000000.0,
        'transcript_segments': [
            {'id': 'seg1', 'start': 0.0, 'end': 12.0, 'speaker_id': 0, 'text': 'hello there friend'},
        ],
        'audio_files': [{'chunk_timestamps': [1700000000.0]}],
        'language': language,
    }


def _wire_common_stubs(monkeypatch, conversation, captured):
    monkeypatch.setattr(speaker_identification_mod.users_db, "get_person", lambda uid, pid: None)
    monkeypatch.setattr(speaker_identification_mod.users_db, "get_person_speech_samples_count", lambda uid, pid: 0)
    monkeypatch.setattr(speaker_identification_mod.conversations_db, "get_conversation", lambda uid, cid: conversation)
    monkeypatch.setattr(
        speaker_identification_mod, "download_audio_chunks_and_merge", lambda *a, **k: b"\x00" * (SAMPLE_RATE * 12 * 2)
    )
    monkeypatch.setattr(
        speaker_identification_mod, "_trim_pcm_audio", lambda pcm, sr, s, e: b"\x00" * (SAMPLE_RATE * 10 * 2)
    )
    monkeypatch.setattr(speaker_identification_mod.users_db, "add_person_speech_sample", lambda *a, **k: True)
    monkeypatch.setattr(
        speaker_identification_mod, "upload_person_speech_sample_from_bytes", lambda *a, **k: "people/u1/p1/a.wav"
    )
    monkeypatch.setattr(
        speaker_identification_mod, "extract_embedding_from_bytes", lambda *a, **k: np.zeros((1, 4), dtype=np.float32)
    )
    monkeypatch.setattr(speaker_identification_mod.users_db, "set_person_speaker_embedding", lambda *a, **k: True)

    async def fake_verify(wav_bytes, sample_rate, expected_text, language=None):
        captured['language'] = language
        return "hello there friend", True, "ok"

    monkeypatch.setattr(speaker_identification_mod, "verify_and_transcribe_sample", fake_verify)


def test_falls_back_to_user_language_preference_when_conversation_language_is_empty(monkeypatch):
    captured: dict = {}
    _wire_common_stubs(monkeypatch, _conversation(language=None), captured)
    monkeypatch.setattr(speaker_identification_mod.users_db, "get_user_language_preference", lambda uid: "ja")

    asyncio.run(
        speaker_identification_mod.extract_speaker_samples(
            uid="u1", person_id="p1", conversation_id="c1", segment_ids=["seg1"]
        )
    )

    assert captured['language'] == "ja"


def test_uses_conversation_language_without_consulting_user_preference(monkeypatch):
    captured: dict = {}
    _wire_common_stubs(monkeypatch, _conversation(language="de"), captured)

    def _boom(uid):
        raise AssertionError("should not consult user preference when conversation already has a language")

    monkeypatch.setattr(speaker_identification_mod.users_db, "get_user_language_preference", _boom)

    asyncio.run(
        speaker_identification_mod.extract_speaker_samples(
            uid="u1", person_id="p1", conversation_id="c1", segment_ids=["seg1"]
        )
    )

    assert captured['language'] == "de"
