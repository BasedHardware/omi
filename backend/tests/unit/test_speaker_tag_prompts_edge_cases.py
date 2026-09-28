"""Unit tests for speaker tag prompt selection, clip extraction, and voice profile UTC/null guards."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from database import voice_profiles as voice_profiles_db
from utils.speaker_tag_prompts import clips, selection, service


def _make_conversation(segments, *, started_at=None, created_at=None):
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    return {
        'id': 'conv-1',
        'started_at': started_at,
        'created_at': created_at or (now - timedelta(hours=1)),
        'status': 'completed',
        'audio_files': [
            {'chunk_timestamps': [float((created_at or (now - timedelta(hours=1))).timestamp())], 'duration': 60.0}
        ],
        'transcript_segments': segments,
        'structured': {'title': 'Standup'},
    }


def test_select_prompts_accepts_iso_string_timestamps_and_skips_empty_text_and_bool_speaker():
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    conv = _make_conversation(
        [
            {'id': 'seg-blank', 'speaker_id': 1, 'is_user': False, 'start': 0.0, 'end': 8.0, 'text': '   '},
            {
                'id': 'seg-valid',
                'speaker_id': True,
                'speaker': 'SPEAKER_03',
                'is_user': False,
                'start': 15.0,
                'end': 22.0,
                'text': 'Valid speech from speaker three.',
            },
        ],
        started_at='2026-09-24T11:00:00Z',
    )
    prompts = selection.select_prompts(
        [conv], now=now, owner_has_voice=False, named_allowed=True, answered=set(), people={}
    )
    assert len(prompts) == 1
    assert prompts[0].speaker_id == 3
    assert prompts[0].excerpt == 'Valid speech from speaker three.'


def test_conversation_clip_pcm_falls_back_to_created_at_and_normalizes_naive_utc(monkeypatch):
    naive_created = datetime(2026, 9, 24, 11, 0, 0)
    expected_epoch = naive_created.replace(tzinfo=timezone.utc).timestamp()
    conv = {
        'id': 'conv-clip',
        'started_at': None,
        'created_at': naive_created,
        'audio_files': [{'chunk_timestamps': [expected_epoch], 'duration': 10.0}],
    }
    monkeypatch.setattr(
        clips,
        'download_audio_chunks_and_merge',
        lambda uid, cid, relevant, fill_gaps=True, sample_rate=16000: b'\x01\x00' * (sample_rate * 10),
    )
    pcm = clips.conversation_clip_pcm('uid-1', conv, 1.0, 6.0)
    assert pcm is not None
    assert len(pcm) == 5 * 16000 * 2


def _raise_no_chunks(uid, cid, relevant, fill_gaps=True, sample_rate=16000):
    raise FileNotFoundError(f'No chunks found for conversation {cid}')


def test_conversation_clip_pcm_returns_none_when_listed_chunks_are_unreadable(monkeypatch):
    # Legacy path: chunk timestamps are listed but storage cannot return them.
    started = datetime(2026, 9, 26, 7, 0, 0, tzinfo=timezone.utc).timestamp()
    legacy = {'id': 'conv-legacy', 'started_at': started, 'audio_files': [{'chunk_timestamps': [started]}]}
    monkeypatch.setattr(clips, 'download_audio_chunks_and_merge', _raise_no_chunks)
    assert clips.conversation_clip_pcm('uid-1', legacy, 1.0, 6.0) is None

    # v2 path: validated spans cover the window, but the blobs are missing.
    v2 = {
        'id': 'conv-v2',
        'started_at': datetime.fromtimestamp(started, tz=timezone.utc),
        'audio_timeline': {'version': 2},
        'private_cloud_sync_enabled': True,
        'audio_files': [{'chunk_timestamps': [started], 'chunk_spans': [{'start': started, 'end': started + 10.0}]}],
    }
    assert clips.conversation_clip_pcm('uid-1', v2, 1.0, 6.0) is None


def test_voice_profile_settings_preserve_default_true_when_stored_as_explicit_none():
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.get.return_value.to_dict.return_value = {
        'speaker_tag_prompts_enabled': None,
        'save_other_voice_profiles': None,
        'speaker_embedding': [0.1, 0.2],
    }
    settings = voice_profiles_db.get_voice_profile_settings('uid-1', firestore_client=mock_client)
    assert settings == {'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': True}
    ctx_settings, has_voice = voice_profiles_db.get_voice_profile_context('uid-1', firestore_client=mock_client)
    assert ctx_settings == {'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': True}
    assert has_voice is True


def test_naive_datetimes_in_state_and_pooling_do_not_raise_type_error(monkeypatch):
    now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    naive_recent = datetime(2026, 9, 24, 11, 30, 0)
    state = {
        'answered': {'prompt-1': naive_recent},
        'last_shown_at': naive_recent,
        'last_empty_check_at': naive_recent,
        'consecutive_dismissals': 0,
    }
    assert voice_profiles_db.answered_prompt_ids(state, now) == {'prompt-1'}

    monkeypatch.setattr(
        voice_profiles_db,
        'get_voice_profile_context',
        lambda uid: ({'speaker_tag_prompts_enabled': True, 'save_other_voice_profiles': True}, True),
    )
    monkeypatch.setattr(voice_profiles_db, 'get_tag_prompt_state', lambda uid: state)
    res = service.get_prompts('uid-1', now=now)
    assert res.status == 'cooldown'
    assert res.next_eligible_at == naive_recent.replace(tzinfo=timezone.utc) + service.SHOW_COOLDOWN
