"""D7 fixture-audio contract: known-content WAV into a labelled injection path.

This module does not inject audio. It pins the corpus fixture the phone-mic
journey must hear, and the receipt label that keeps a platform microphone
path honest versus an in-app fake. Adding a virtual audio device or a
capture-source seam is a stop-and-ask, not a silent fallback.
"""

from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import session_evidence as se

INJECTION_PLATFORM_MIC = "platform_mic"
INJECTION_IN_APP_FAKE = "in_app_fake"
ALLOWED_INJECTION_KINDS = frozenset({INJECTION_PLATFORM_MIC, INJECTION_IN_APP_FAKE})

CONTENT_EVIDENCE_CAPTURED_PCM = "captured_pcm"
CONTENT_EVIDENCE_TRANSCRIPT_PHRASE = "transcript_phrase"
ALLOWED_CONTENT_EVIDENCE = frozenset({CONTENT_EVIDENCE_CAPTURED_PCM, CONTENT_EVIDENCE_TRANSCRIPT_PHRASE})

FIXTURE_RELATIVE = Path("backend/testing/release_fixtures/transcription-release-probe.wav")
MANIFEST_RELATIVE = Path("backend/testing/release_fixtures/transcription-release-probe.json")

PHONE_MIC_SAMPLE_RATE = 16000
PHONE_MIC_CHANNELS = 1
PHONE_MIC_SAMPLE_WIDTH = 2


class FixtureAudioError(se.EvidenceError):
    """The D7 fixture is missing, the wrong bytes, or the wrong codec."""


@dataclass(frozen=True)
class KnownAudioFixture:
    path: Path
    sha256: str
    sample_rate: int
    channels: int
    sample_width: int
    frames: int
    duration_s: float
    expected_transcript: str
    language: str


def load_known_audio_fixture(repo_root: Path) -> KnownAudioFixture:
    """Load the LibriSpeech release-probe WAV the program already ships."""

    root = Path(repo_root)
    wav_path = root / FIXTURE_RELATIVE
    manifest_path = root / MANIFEST_RELATIVE
    if not wav_path.is_file() or not manifest_path.is_file():
        raise FixtureAudioError("D7 requires the transcription-release-probe WAV and manifest")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    expected = str(payload.get("sha256") or "")
    if digest != expected:
        raise FixtureAudioError(f"fixture sha256 {digest} does not match manifest {expected}")
    with wave.open(str(wav_path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frames = handle.getnframes()
        comptype = handle.getcomptype()
    if comptype != "NONE":
        raise FixtureAudioError(f"fixture must be uncompressed PCM, got {comptype!r}")
    if sample_rate != PHONE_MIC_SAMPLE_RATE or channels != PHONE_MIC_CHANNELS or sample_width != PHONE_MIC_SAMPLE_WIDTH:
        raise FixtureAudioError(
            "fixture is not unmodified phone-mic PCM16 16 kHz mono "
            f"(rate={sample_rate} channels={channels} width={sample_width})"
        )
    expected_transcript = str(payload.get("expected_transcript") or "").strip()
    if not expected_transcript:
        raise FixtureAudioError("fixture manifest is missing expected_transcript")
    return KnownAudioFixture(
        path=wav_path,
        sha256=digest,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        frames=frames,
        duration_s=frames / float(sample_rate),
        expected_transcript=expected_transcript,
        language=str(payload.get("language") or "en"),
    )


def refuse_platform_mic_without_host_audio(audio_disabled: bool) -> None:
    """V3 product boots use -no-audio; that cannot be labelled platform_mic."""

    if audio_disabled:
        raise FixtureAudioError(
            "platform_mic injection requires host audio on the emulator/simulator; "
            "-no-audio is a fake-silent path and must not be labelled a microphone"
        )


def validate_injection_receipt(document: Mapping[str, object]) -> list[str]:
    """A D7 receipt must name the injection kind so a fake cannot pose as a mic."""

    errors: list[str] = []
    live = document.get("fixture_audio")
    if not isinstance(live, Mapping):
        return ["fixture_audio: required object"]
    kind = live.get("injection_kind")
    if kind not in ALLOWED_INJECTION_KINDS:
        errors.append(f"fixture_audio.injection_kind must be one of {sorted(ALLOWED_INJECTION_KINDS)}, got {kind!r}")
    digest = live.get("fixture_sha256")
    if not isinstance(digest, str) or not se.SHA256_RE.fullmatch(digest):
        errors.append("fixture_audio.fixture_sha256 must be 64-char hex")
    heard = live.get("heard")
    if heard is not True:
        errors.append("fixture_audio.heard must be true: a played file is not acceptance")
    evidence = live.get("content_evidence")
    if evidence not in ALLOWED_CONTENT_EVIDENCE:
        errors.append(
            "fixture_audio.content_evidence must be captured_pcm or transcript_phrase "
            f"(fixture content, not that a file played), got {evidence!r}"
        )
    if kind == INJECTION_IN_APP_FAKE and live.get("platform_path_proven") is True:
        errors.append("in_app_fake must not claim platform_path_proven")
    if kind == INJECTION_PLATFORM_MIC and live.get("platform_path_proven") is not True:
        errors.append("platform_mic receipts must set platform_path_proven true")
    return errors
