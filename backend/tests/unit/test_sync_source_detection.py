"""Tests for /v2/sync-local-files filename → ConversationSource detection.

`detect_source_from_filenames` (utils/sync/files.py) is the single helper both
sync.py upload sites use to label a batch. It must:
  - map phone-mic Transcribe Later uploads ('omibatchphone', and the
    'omibatchphoneauto' offline auto-switch variant) → phone
  - map phone-mic WAL fallback uploads ('phonemic') → phone
  - keep mapping limitless uploads → limitless (first-match-wins preserved)
  - default plain omi-batch uploads → omi
"""

import sys
from unittest.mock import MagicMock

import pytest

from models.conversation_enums import ConversationSource


@pytest.fixture
def detect_source(monkeypatch):
    # utils.sync.files imports its sibling utils.sync.playback, which transitively
    # pulls in google-cloud-tasks. Stub the heavy sibling so the pure filename
    # helper imports hermetically (no network, no GCP deps).
    monkeypatch.setitem(sys.modules, 'utils.sync.playback', MagicMock())
    monkeypatch.delitem(sys.modules, 'utils.sync.files', raising=False)
    from utils.sync.files import detect_source_from_filenames

    return detect_source_from_filenames


@pytest.mark.parametrize(
    'filename,expected',
    [
        ('audio_omibatchphone_opus_fs320_16000_1_fs320_1720000000.bin', ConversationSource.phone),
        ('audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000000.bin', ConversationSource.phone),
        ('audio_phonemic_pcm16_16000_1_fs160_1720000000.bin', ConversationSource.phone),
        ('audio_omibatchlimitless_opus_fs320_16000_1_fs320_1720000000.bin', ConversationSource.limitless),
        ('audio_omibatch_opus_16000_1_fs320_1720000000.bin', ConversationSource.omi),
    ],
)
def test_source_mapping_matrix(detect_source, filename, expected):
    assert detect_source([filename]) == expected


def test_case_insensitive_detection(detect_source):
    assert detect_source(['AUDIO_OmiBatchPhone_1720000000.BIN']) == ConversationSource.phone
    assert detect_source(['AUDIO_PhoneMic_1720000000.BIN']) == ConversationSource.phone
    assert detect_source(['AUDIO_Limitless_1720000000.BIN']) == ConversationSource.limitless


def test_empty_and_none_filenames_default_to_omi(detect_source):
    assert detect_source([]) == ConversationSource.omi
    assert detect_source([None, None]) == ConversationSource.omi
    assert detect_source([None, '', 'audio_omibatch_opus_1.bin']) == ConversationSource.omi


def test_none_filenames_are_skipped_not_fatal(detect_source):
    # A None entry before a real match must not shadow detection.
    assert detect_source([None, 'audio_omibatchphone_1.bin']) == ConversationSource.phone


def test_limitless_still_wins_within_a_batch(detect_source):
    # First-match-wins: a limitless file sets limitless regardless of later files.
    files = [
        'audio_omibatchlimitless_opus_1.bin',
        'audio_omibatchphone_opus_2.bin',
    ]
    assert detect_source(files) == ConversationSource.limitless


def test_phone_detected_when_only_phone_files_present(detect_source):
    files = [
        'audio_omibatch_opus_1.bin',
        'audio_phonemic_pcm16_16000_1_fs160_2.bin',
    ]
    assert detect_source(files) == ConversationSource.phone
