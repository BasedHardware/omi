import io
from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from pydub import AudioSegment
from pydub.generators import Sine
from starlette.datastructures import UploadFile

from models.conversation import Conversation, CreateConversationResponse
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from routers import conversations as conversations_router

UID = "test-audio-import-uid"


def _create_sample_wav_bytes(duration_ms: int = 1000) -> bytes:
    tone = Sine(440).to_audio_segment(duration=duration_ms)
    buf = io.BytesIO()
    tone.set_frame_rate(16000).set_channels(1).export(buf, format="wav")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_audio_unsupported_extension():
    upload = UploadFile(filename="document.pdf", file=io.BytesIO(b"dummy pdf bytes"))
    with pytest.raises(HTTPException) as exc_info:
        await conversations_router.upload_audio_to_conversation(
            file=upload,
            language=None,
            uid=UID,
        )
    assert exc_info.value.status_code == 400
    assert "Unsupported file format" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_audio_empty_file():
    upload = UploadFile(filename="recording.mp3", file=io.BytesIO(b""))
    with pytest.raises(HTTPException) as exc_info:
        await conversations_router.upload_audio_to_conversation(
            file=upload,
            language=None,
            uid=UID,
        )
    assert exc_info.value.status_code == 400
    assert "Empty audio file" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_audio_file_too_large(monkeypatch):
    monkeypatch.setattr(conversations_router, "AUDIO_IMPORT_MAX_BYTES", 100)
    upload = UploadFile(filename="recording.wav", file=io.BytesIO(b"x" * 101))
    with pytest.raises(HTTPException) as exc_info:
        await conversations_router.upload_audio_to_conversation(
            file=upload,
            language=None,
            uid=UID,
        )
    assert exc_info.value.status_code == 413
    assert "maximum allowed size" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_audio_corrupt_file():
    upload = UploadFile(filename="recording.mp3", file=io.BytesIO(b"corrupt non-audio content"))
    with pytest.raises(HTTPException) as exc_info:
        await conversations_router.upload_audio_to_conversation(
            file=upload,
            language=None,
            uid=UID,
        )
    assert exc_info.value.status_code == 400
    assert "Could not decode audio file" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_audio_stt_failure(monkeypatch):
    wav_bytes = _create_sample_wav_bytes(500)
    upload = UploadFile(filename="recording.wav", file=io.BytesIO(wav_bytes))

    def failing_stt(*args, **kwargs):
        raise RuntimeError("Deepgram down")

    monkeypatch.setattr("utils.stt.pre_recorded.prerecorded_from_bytes", failing_stt)

    with pytest.raises(HTTPException) as exc_info:
        await conversations_router.upload_audio_to_conversation(
            file=upload,
            language=None,
            uid=UID,
        )
    assert exc_info.value.status_code == 502
    assert "Audio transcription service failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_audio_no_speech(monkeypatch):
    wav_bytes = _create_sample_wav_bytes(500)
    upload = UploadFile(filename="recording.wav", file=io.BytesIO(wav_bytes))

    monkeypatch.setattr("utils.stt.pre_recorded.prerecorded_from_bytes", lambda *a, **k: [])

    with pytest.raises(HTTPException) as exc_info:
        await conversations_router.upload_audio_to_conversation(
            file=upload,
            language=None,
            uid=UID,
        )
    assert exc_info.value.status_code == 400
    assert "No speech detected" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_audio_success(monkeypatch):
    wav_bytes = _create_sample_wav_bytes(1000)
    upload = UploadFile(filename="my_meeting.wav", file=io.BytesIO(wav_bytes))

    fake_words = [
        {"timestamp": [0.0, 0.5], "speaker": "SPEAKER_00", "text": "Hello"},
        {"timestamp": [0.5, 1.0], "speaker": "SPEAKER_01", "text": "world"},
    ]
    monkeypatch.setattr("utils.stt.pre_recorded.prerecorded_from_bytes", lambda *a, **k: fake_words)

    created_conversation_holder = {}

    def fake_process_conversation(
        uid,
        language_code,
        create_data,
        persistence_observer=None,
        derived_effects_disposition_observer=None,
        trigger=None,
    ):
        created_conversation_holder["create_data"] = create_data
        if persistence_observer:
            persistence_observer(True)
        now = datetime.now(timezone.utc)
        return Conversation(
            id="imported-conv-123",
            created_at=now,
            started_at=create_data.started_at,
            finished_at=create_data.finished_at,
            source=create_data.source,
            language=create_data.language,
            imported=create_data.imported,
            status=ConversationStatus.completed,
            structured=Structured(title="Imported Audio Note", overview="Summary of audio note"),
            transcript_segments=create_data.transcript_segments,
        )

    async def fake_trigger_external_integrations(uid, conv):
        return []

    monkeypatch.setattr(conversations_router, "process_conversation", fake_process_conversation)
    monkeypatch.setattr(conversations_router, "trigger_external_integrations", fake_trigger_external_integrations)

    response = await conversations_router.upload_audio_to_conversation(
        file=upload,
        language="en",
        uid=UID,
    )

    assert isinstance(response, CreateConversationResponse)
    assert response.conversation is not None
    assert response.conversation.id == "imported-conv-123"
    assert response.conversation.imported is True
    assert response.conversation.source == ConversationSource.phone
    assert response.conversation.structured.title == "Imported Audio Note"
    assert len(response.conversation.transcript_segments) >= 1
    assert created_conversation_holder["create_data"].imported is True
