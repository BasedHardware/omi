"""The empty-success guard: speech-positive zero-word segments after a degraded chain.

2026-10-23 staging soak class: with SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED=false
(the prod default), the sync double-empty path recorded expected_silence without
ever inspecting VAD, so a chain like Parakeet blackholed + Modulate valid-empty
completed speech-positive units with zero words as success.
"""

import os
import wave
from pathlib import Path

import pytest

import database.sync_jobs as sync_jobs_module
from utils.stt import local_vad, prerecorded_health, vendor_guard
from utils.stt.prerecorded_health import CREDIT_AUTH, PROVIDER_ERROR, note_provider_failure
from utils.sync import empty_success_guard
from utils.sync.empty_success_guard import GUARD_TOTAL, settle

_PIPELINE = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')


def _wav(path: Path, seconds: float = 8.0) -> str:
    with wave.open(str(path), 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        target.writeframes(b'\x00\x00' * int(16000 * seconds))
    return str(path)


@pytest.fixture(autouse=True)
def _clean_vendor_state(monkeypatch, tmp_path):
    monkeypatch.delenv('SYNC_EMPTY_SUCCESS_GUARD_ENABLED', raising=False)
    monkeypatch.delenv('STT_PRERECORDED_VENDOR_FAIL_FAST', raising=False)
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda _: [])
    vendor_guard.reset_vendor_guard_for_tests()
    prerecorded_health.reset_prerecorded_health_for_tests()
    yield
    vendor_guard.reset_vendor_guard_for_tests()
    prerecorded_health.reset_prerecorded_health_for_tests()


def _speech(tmp_path, monkeypatch, start=0.0, end=6.0) -> str:
    monkeypatch.setattr(local_vad, 'offline_pcm_speech_segments', lambda _: [{'start': start, 'end': end}])
    return _wav(tmp_path / 'segment.wav')


def test_parakeet_down_and_modulate_empty_holds_speech_positive_segment(tmp_path, monkeypatch):
    """Parakeet failing while the fallback serves empty must not complete as silence."""
    path = _speech(tmp_path, monkeypatch)
    note_provider_failure('parakeet', PROVIDER_ERROR)
    before = GUARD_TOTAL.labels('modulate', 'held_provider_error')._value.get()
    held, reason = settle(path, provider='modulate')
    assert (held, reason) == (True, empty_success_guard.HELD_PROVIDER_ERROR)
    assert GUARD_TOTAL.labels('modulate', 'held_provider_error')._value.get() > before
    prerecorded_health.reset_prerecorded_health_for_tests()


def test_credit_auth_failure_holds_speech_positive_segment(tmp_path, monkeypatch):
    """An out-of-credits refusal recorded by the vendor guard holds the segment."""
    path = _speech(tmp_path, monkeypatch)
    vendor_guard.record_breaker_quota_error(vendor_guard.ENDPOINT_LID)
    held, reason = settle(path, provider='modulate')
    assert (held, reason) == (True, empty_success_guard.HELD_CREDIT_AUTH)


def test_prior_provider_failure_marker_holds_across_attempts_and_instances(tmp_path, monkeypatch):
    """A provider-class failure recorded for the job is durable degradation
    evidence: no in-memory state is needed, so another instance's Cloud Tasks
    retry still holds the empty that follows it."""
    path = _speech(tmp_path, monkeypatch)
    marked = {'job-1': True}

    def fake_was_marked(job_id, tag):
        assert tag == empty_success_guard.PRIOR_PROVIDER_FAILURE_TAG
        return marked.get(job_id, False)

    monkeypatch.setattr(sync_jobs_module, 'was_marked_once', fake_was_marked)
    held, reason = settle(path, provider='modulate', job_id='job-1')
    assert (held, reason) == (True, empty_success_guard.HELD_PROVIDER_ERROR)
    # The same healthy chain on a job without a recorded provider failure stays unchanged.
    held, reason = settle(path, provider='modulate', job_id='job-2')
    assert (held, reason) == (False, empty_success_guard.SPEECH_POSITIVE_HEALTHY_CHAIN)


def test_unreadable_job_marker_never_degrades_a_chain(tmp_path, monkeypatch):
    """A stubbed or failing marker read fails closed: a healthy chain is unchanged."""
    path = _speech(tmp_path, monkeypatch)
    monkeypatch.setattr(sync_jobs_module, 'was_marked_once', lambda job_id, tag: 'mock-truthy-not-bool')
    held, reason = settle(path, provider='modulate', job_id='job-3')
    assert (held, reason) == (False, empty_success_guard.SPEECH_POSITIVE_HEALTHY_CHAIN)


def test_dispatch_note_does_not_bleed_across_contexts(tmp_path, monkeypatch):
    """The swallowed LID failure note is scoped to its dispatch context only."""
    path = _speech(tmp_path, monkeypatch)
    note_provider_failure('modulate', PROVIDER_ERROR)
    prerecorded_health.reset_prerecorded_health_for_tests()
    held, reason = settle(path, provider='modulate')
    assert (held, reason) == (False, empty_success_guard.SPEECH_POSITIVE_HEALTHY_CHAIN)


def test_failed_lid_probe_notes_dispatch_health(monkeypatch, tmp_path):
    """A transport-failed LID probe leaves the degradation note the guard reads."""
    import httpx

    import utils.stt.batch_language as batch_language

    def refuse_post(*args, **kwargs):
        raise httpx.ConnectError('transport refused')

    monkeypatch.setenv('MODULATE_API_KEY', 'test-key')
    monkeypatch.setattr(httpx.Client, 'post', refuse_post)
    decision = batch_language.detect(_wav(tmp_path / 'probe.wav', seconds=2))
    assert decision.evidence == 'unavailable'
    assert prerecorded_health.recent_dispatch_failure() == 'provider_error'
    prerecorded_health.reset_prerecorded_health_for_tests()


def test_healthy_chain_speech_positive_unchanged(tmp_path, monkeypatch):
    """A healthy chain keeps today's behavior, counted for the lead's follow-up."""
    path = _speech(tmp_path, monkeypatch)
    held, reason = settle(path, provider='parakeet')
    assert (held, reason) == (False, empty_success_guard.SPEECH_POSITIVE_HEALTHY_CHAIN)


def test_genuine_silence_unchanged(tmp_path):
    """Validated zero-span VAD still authorizes the silence record."""
    path = _wav(tmp_path / 'segment.wav')  # the autouse fixture stubs VAD to no spans
    held, reason = settle(path, provider='modulate')
    assert (held, reason) == (False, empty_success_guard.SILENCE_CONFIRMED)


def test_short_speech_below_threshold_unchanged(tmp_path, monkeypatch):
    """Below the long-speech handoff threshold the guard stays out of the decision."""
    path = _speech(tmp_path, monkeypatch, start=1.0, end=3.0)
    note_provider_failure('modulate', PROVIDER_ERROR)
    held, reason = settle(path, provider='modulate')
    assert (held, reason) == (False, empty_success_guard.SPEECH_BELOW_THRESHOLD)
    prerecorded_health.reset_prerecorded_health_for_tests()


def test_kill_switch_disables_guard(tmp_path, monkeypatch):
    monkeypatch.setenv('SYNC_EMPTY_SUCCESS_GUARD_ENABLED', 'false')
    path = _speech(tmp_path, monkeypatch)
    note_provider_failure('parakeet', CREDIT_AUTH)
    held, reason = settle(path, provider='modulate')
    assert (held, reason) == (False, empty_success_guard.GUARD_DISABLED)
    prerecorded_health.reset_prerecorded_health_for_tests()


def test_inspection_failure_keeps_silence_behavior(tmp_path):
    """An unreadable file never becomes hold evidence; it keeps legacy behavior."""
    held, reason = settle(str(tmp_path / 'missing.wav'), provider='modulate')
    assert (held, reason) == (False, empty_success_guard.INSPECTION_UNAVAILABLE)


def test_pipeline_holds_before_silence_record():
    """Both silence decisions (double-empty and post-admission) hold, never launder."""
    source = Path(_PIPELINE).read_text(encoding='utf-8')
    silence_calls = [i for i in range(len(source)) if source.startswith('_record_empty_segment_as_silence(', i)]
    assert len(silence_calls) >= 3  # definition site plus the two call sites
    guard_calls = [
        i for i in range(len(source)) if source.startswith('empty_success_guard.settle(path, provider=provider', i)
    ]
    assert len(guard_calls) == 2
    for guard_call in guard_calls:
        raise_between = source.index('raise TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED', guard_call)
        silence_call = source.index('_record_empty_segment_as_silence(', raise_between)
        assert guard_call < raise_between < silence_call
