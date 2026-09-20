from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import fixture_audio as fa

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_d7_reuses_the_release_probe_wav_unmodified() -> None:
    fixture = fa.load_known_audio_fixture(REPO_ROOT)
    assert fixture.path.name == "transcription-release-probe.wav"
    assert fixture.sha256 == "1fb553adb5a6389eef5b7ebdbf9ed2a6082518a646ce9bf872bf33b964eedc14"
    assert fixture.sample_rate == 16000
    assert fixture.channels == 1
    assert fixture.sample_width == 2
    assert 4.5 < fixture.duration_s < 5.5
    assert "wizard who had vanished" in fixture.expected_transcript
    assert fixture.language == "en"


def test_no_audio_emulator_cannot_be_labelled_a_platform_microphone() -> None:
    fa.refuse_platform_mic_without_host_audio(False)
    with pytest.raises(fa.FixtureAudioError, match="-no-audio"):
        fa.refuse_platform_mic_without_host_audio(True)


def test_receipt_must_name_injection_kind_and_that_the_app_heard_it() -> None:
    fixture = fa.load_known_audio_fixture(REPO_ROOT)
    ok = {
        "fixture_audio": {
            "injection_kind": fa.INJECTION_PLATFORM_MIC,
            "fixture_sha256": fixture.sha256,
            "heard": True,
            "content_evidence": fa.CONTENT_EVIDENCE_TRANSCRIPT_PHRASE,
            "platform_path_proven": True,
        }
    }
    assert fa.validate_injection_receipt(ok) == []
    fake = {
        "fixture_audio": {
            "injection_kind": fa.INJECTION_IN_APP_FAKE,
            "fixture_sha256": fixture.sha256,
            "heard": True,
            "content_evidence": fa.CONTENT_EVIDENCE_TRANSCRIPT_PHRASE,
            "platform_path_proven": True,
        }
    }
    assert any("must not claim platform_path_proven" in err for err in fa.validate_injection_receipt(fake))
    played_only = {
        "fixture_audio": {
            "injection_kind": fa.INJECTION_PLATFORM_MIC,
            "fixture_sha256": fixture.sha256,
            "heard": False,
            "content_evidence": "file_played",
            "platform_path_proven": True,
        }
    }
    played_errors = fa.validate_injection_receipt(played_only)
    assert any("heard must be true" in err for err in played_errors)
    assert any("content_evidence" in err for err in played_errors)
