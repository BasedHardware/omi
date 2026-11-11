"""Regression tests for dropping a person's teaching profile with its sample (#5084).

The original bug lived in `delete_extra_speech_profile_sample`: the audio blob was
removed while the stored Firestore profile (speech_samples / speaker_embedding /
speech_sample_source) survived, so tagging that person later never rebuilt it.
The endpoint cases exercise that handler through the sanctioned seams
(import + patch.object). The handler imports PyAV via `av`, which is absent
locally, so endpoint cases skip here and run in CI.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import patch

import pytest

from utils.speech_profile_deletion import teaching_segment_ids_for_deleted_sample

try:
    from routers import speech_profile as sp_router

    _SP_IMPORTABLE = True
except Exception:  # PyAV (av) unavailable locally; present in CI
    sp_router = None
    _SP_IMPORTABLE = False


# ---------------------------------------------------------------------------
# helper: teaching_segment_ids_for_deleted_sample
# ---------------------------------------------------------------------------
def test_deleted_sample_clears_the_teaching_segments_from_that_conversation():
    person = {'speech_sample_source': {'conversation_id': 'conv-1', 'segment_ids': ['s1', 's2']}}

    assert teaching_segment_ids_for_deleted_sample(person, 'conv-1') == ['s1', 's2']


def test_deleted_sample_from_another_conversation_keeps_the_profile():
    person = {'speech_sample_source': {'conversation_id': 'conv-1', 'segment_ids': ['s1']}}

    assert teaching_segment_ids_for_deleted_sample(person, 'conv-2') == []


def test_missing_person_or_source_does_not_clear_a_profile():
    assert teaching_segment_ids_for_deleted_sample(None, 'conv-1') == []
    assert teaching_segment_ids_for_deleted_sample({}, 'conv-1') == []
    assert teaching_segment_ids_for_deleted_sample({'speech_sample_source': {}}, '') == []


# ---------------------------------------------------------------------------
# endpoint: delete_extra_speech_profile_sample
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _SP_IMPORTABLE, reason="PyAV (av) unavailable locally")
def test_delete_sample_invalidates_teaching_profile_for_matching_conversation():
    person = {'speech_sample_source': {'conversation_id': 'conv-1', 'segment_ids': ['s1', 's2']}}
    with patch.object(sp_router, 'delete_user_person_speech_sample') as delete_sample, patch.object(
        sp_router, 'get_person', return_value=person
    ), patch.object(
        sp_router, 'invalidate_person_speech_profile', return_value=['gs://bucket/p.wav']
    ) as invalidate, patch.object(
        sp_router, 'delete_speech_profile_blob'
    ) as delete_blob:
        resp = sp_router.delete_extra_speech_profile_sample(memory_id='conv-1', segment_idx=3, person_id='p1', uid='u1')

    assert resp == {'status': 'ok'}
    delete_sample.assert_called_once_with('u1', 'p1', 'conv-1_segment_3.wav')
    invalidate.assert_called_once_with('u1', 'p1', 'conv-1', ['s1', 's2'])
    delete_blob.assert_called_once_with('gs://bucket/p.wav')


@pytest.mark.skipif(not _SP_IMPORTABLE, reason="PyAV (av) unavailable locally")
def test_delete_sample_keeps_profile_for_another_conversation():
    person = {'speech_sample_source': {'conversation_id': 'conv-1', 'segment_ids': ['s1']}}
    with patch.object(sp_router, 'delete_user_person_speech_sample') as delete_sample, patch.object(
        sp_router, 'get_person', return_value=person
    ), patch.object(sp_router, 'invalidate_person_speech_profile') as invalidate, patch.object(
        sp_router, 'delete_speech_profile_blob'
    ) as delete_blob:
        resp = sp_router.delete_extra_speech_profile_sample(memory_id='conv-2', segment_idx=0, person_id='p1', uid='u1')

    assert resp == {'status': 'ok'}
    delete_sample.assert_called_once_with('u1', 'p1', 'conv-2_segment_0.wav')
    invalidate.assert_not_called()
    delete_blob.assert_not_called()


@pytest.mark.skipif(not _SP_IMPORTABLE, reason="PyAV (av) unavailable locally")
def test_delete_sample_without_person_uses_additional_audio_path():
    with patch.object(sp_router, 'delete_additional_profile_audio') as delete_audio, patch.object(
        sp_router, 'delete_user_person_speech_sample'
    ) as delete_sample, patch.object(sp_router, 'invalidate_person_speech_profile') as invalidate:
        resp = sp_router.delete_extra_speech_profile_sample(memory_id='conv-1', segment_idx=1, person_id=None, uid='u1')

    assert resp == {'status': 'ok'}
    delete_audio.assert_called_once_with('u1', 'conv-1_segment_1.wav')
    delete_sample.assert_not_called()
    invalidate.assert_not_called()
