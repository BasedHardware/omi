"""Declared-supported serving batch units are sampled for a language audit; routing never changes."""

from io import BytesIO
import math
import os
from types import SimpleNamespace
from unittest.mock import Mock
import wave

import pytest
from prometheus_client import REGISTRY

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.language_probe_authorization import ServingLanguageProbeGuard
from utils.executors import ExecutorSaturatedError
from utils.stt import batch_language, declared_language_audit as audit
from utils.stt.batch_language import LanguageDecision
from utils.stt.language_gate import SelfVerdict


def wav_bytes(seconds=40, *, voiced=True, sample_rate=16000):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        if voiced:
            frames = b''.join(
                int(3000 * math.sin(2 * math.pi * 220 * i / sample_rate)).to_bytes(2, 'little', signed=True)
                for i in range(sample_rate)
            )
            writer.writeframes(frames * int(seconds))
        else:
            writer.writeframes(b'\x01\x00' * int(seconds * sample_rate))
    return output.getvalue()


VOICED = wav_bytes()


class Inline:
    def submit(self, fn, *args):
        fn(*args)


class Full:
    def submit(self, fn, *args):
        raise ExecutorSaturatedError('full')


def audited(**labels):
    base = {'declared': 'en', 'heard': 'zh', 'heard_class': 'unsupported', 'confident': 'true', 'classifier': 'self'}
    return REGISTRY.get_sample_value('omi_batch_pipeline_declared_language_audit_total', {**base, **labels}) or 0.0


def skipped(reason):
    return (
        REGISTRY.get_sample_value('omi_batch_pipeline_declared_language_audit_skipped_total', {'reason': reason}) or 0.0
    )


def serving_guard(authorize=None, custom_stt=False):
    item = SimpleNamespace(owner_id='owner-test', duration_seconds=40.0)
    return ServingLanguageProbeGuard(
        object(), item, authorize=authorize or (lambda store, item, snapshots=None: None), custom_stt=custom_stt
    )


@pytest.fixture
def lab(monkeypatch):
    state = SimpleNamespace(self_calls=[], vendor_calls=[], verdict=SelfVerdict('zh', 0.97, 0.02, 30.0))

    def self_detect(probe, *, surface):
        state.self_calls.append((len(probe), surface))
        return state.verdict

    def vendor(probe):
        state.vendor_calls.append(len(probe))
        return LanguageDecision('hi', 0.93, 'audio_lid', 30.0)

    monkeypatch.delenv('BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED', raising=False)
    monkeypatch.setenv('HOSTED_LID_API_URL', 'http://lid.test')
    monkeypatch.setattr(audit.language_gate, 'self_detect', self_detect)
    monkeypatch.setattr(batch_language, 'detect', vendor)
    monkeypatch.setattr(audit, 'declared_language_audit_executor', Inline())
    monkeypatch.setattr(audit, 'sampled', lambda audio: True)
    monkeypatch.setattr('utils.funded_processing.consent_allows', lambda uid: True)
    state.funding_calls = []

    def funded(uid, **kwargs):
        state.funding_calls.append(kwargs)
        return SimpleNamespace(managed=state.funded)

    state.funded = True
    monkeypatch.setattr('utils.stt_cap_dispatch.funded_allowance', funded)
    monkeypatch.setattr('utils.stt_cap_dispatch.sync_allowed', Mock(side_effect=AssertionError('admission')))
    monkeypatch.setattr(audit, '_probe_window', [0.0, 0])
    return state


def resolve(audio=VOICED, guard=None, language='en', surface='batch'):
    guard = serving_guard() if guard is None else guard
    return (
        batch_language.resolve_language(language, audio, surface=surface, before_probe=guard, before_self_probe=guard),
        guard,
    )


def test_a_declared_english_unit_is_audited_and_still_routed_as_declared(lab):
    before = audited()

    decision, guard = resolve()

    assert (decision.language, decision.evidence) == ('en', 'declared')
    assert guard.decision is None  # the serving guard is never called by the audit
    assert audited() == before + 1
    assert lab.self_calls[0][1] == 'batch_audit'
    assert lab.self_calls[0][0] <= 30 * 16000 * 2 + 100  # only the first 30 s of the 40 s unit


def test_without_a_self_gate_the_vendor_probe_classifies(lab, monkeypatch):
    monkeypatch.setenv('HOSTED_LID_API_URL', '')
    monkeypatch.setenv('STT_GPU_FLEET_OFF', 'true')
    before = audited(heard='hi', classifier='vendor')

    resolve()

    assert lab.self_calls == []
    assert len(lab.vendor_calls) == 1
    assert audited(heard='hi', classifier='vendor') == before + 1


def test_vendor_probes_are_capped_per_process_per_hour(lab, monkeypatch):
    monkeypatch.setenv('HOSTED_LID_API_URL', '')
    monkeypatch.setenv('STT_GPU_FLEET_OFF', 'true')
    monkeypatch.setattr(audit, 'MAX_PROBES_PER_HOUR', 1)
    before = skipped('probe_cap')

    resolve()
    resolve()

    assert len(lab.vendor_calls) == 1
    assert skipped('probe_cap') == before + 1


def test_self_gate_probes_share_the_hourly_cap(lab, monkeypatch):
    monkeypatch.setattr(audit, 'MAX_PROBES_PER_HOUR', 1)
    before = skipped('probe_cap')

    resolve()
    resolve()

    assert len(lab.self_calls) == 1
    assert skipped('probe_cap') == before + 1


def test_an_unusable_vendor_answer_is_skipped(lab, monkeypatch):
    monkeypatch.setenv('HOSTED_LID_API_URL', '')
    monkeypatch.setenv('STT_GPU_FLEET_OFF', 'true')
    monkeypatch.setattr(batch_language, 'detect', lambda probe: LanguageDecision('und', 0.0, 'unavailable', 30.0))
    before = skipped('vendor_unavailable')

    resolve()

    assert skipped('vendor_unavailable') == before + 1


def test_a_privacy_refusal_skips_the_sample_and_never_touches_serving(lab):
    def blocked(store, item, snapshots=None):
        raise BatchPrivacyBlocked('blocked')

    guard = serving_guard(blocked)
    before = skipped('not_authorized')

    decision, guard = resolve(guard=guard)

    assert decision.evidence == 'declared'
    assert guard.decision is None and guard.privacy_error is None
    guard.raise_if_denied()  # serving custody is unaffected
    assert lab.self_calls == []
    assert skipped('not_authorized') == before + 1


def test_a_consent_reset_skips_the_sample(lab, monkeypatch):
    monkeypatch.setattr('utils.funded_processing.consent_allows', lambda uid: False)
    before = skipped('not_authorized')

    resolve()

    assert lab.self_calls == []
    assert skipped('not_authorized') == before + 1


def test_leading_silence_is_not_a_language_sample(lab):
    before = skipped('no_speech')

    resolve(audio=wav_bytes(voiced=False))

    assert lab.self_calls == []
    assert lab.funding_calls == []  # a silent probe skips before any authorization read
    assert skipped('no_speech') == before + 1


def test_a_low_confidence_verdict_is_labelled_not_confident(lab):
    lab.verdict = SelfVerdict('hi', 0.55, 0.3, 30.0)
    before = audited(heard='hi', confident='false')

    resolve()

    assert audited(heard='hi', confident='false') == before + 1


def test_an_unavailable_self_gate_is_skipped_not_counted(lab):
    lab.verdict = None
    before = skipped('self_unavailable')

    resolve()

    assert skipped('self_unavailable') == before + 1


def test_a_reply_that_does_not_describe_the_probe_is_skipped(lab):
    lab.verdict = SelfVerdict('zh', 0.97, 0.02, 12.0)
    before = skipped('duration_mismatch')

    resolve()

    assert skipped('duration_mismatch') == before + 1


def test_a_full_pool_skips_without_blocking(lab, monkeypatch):
    monkeypatch.setattr(audit, 'declared_language_audit_executor', Full())
    before = skipped('busy')

    decision, _ = resolve()

    assert decision.evidence == 'declared'
    assert lab.self_calls == []
    assert skipped('busy') == before + 1


def test_undecodable_audio_is_skipped(lab):
    before = skipped('decode')

    decision, _ = resolve(audio=b'not a wav')

    assert decision.evidence == 'declared'
    assert skipped('decode') == before + 1


def test_a_classifier_bug_is_counted_and_never_raises(lab, monkeypatch):
    def broken(probe, *, surface):
        raise RuntimeError('boom')

    monkeypatch.setattr(audit.language_gate, 'self_detect', broken)
    before = skipped('error')

    decision, _ = resolve()

    assert decision.evidence == 'declared'
    assert skipped('error') == before + 1


def test_shadow_intake_and_unguarded_callers_are_not_audited(lab):
    class ShadowGuard:
        def __call__(self):
            return True

    resolve(guard=ShadowGuard())
    batch_language.resolve_language('en', VOICED, surface='batch')

    assert lab.self_calls == [] and lab.vendor_calls == []


@pytest.mark.parametrize('surface', ['prerecorded', 'batch_shadow'])
def test_other_surfaces_are_not_audited(lab, surface):
    resolve(surface=surface)

    assert lab.self_calls == []


def test_a_declared_unsupported_language_is_not_audited(lab):
    resolve(language='ja')

    assert lab.self_calls == []


def test_kill_switch_stops_sampling(lab, monkeypatch):
    monkeypatch.setenv('BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED', 'false')

    resolve()

    assert lab.self_calls == []


def test_unsampled_audio_is_not_audited(lab, monkeypatch):
    monkeypatch.setattr(audit, 'sampled', lambda audio: False)

    resolve()

    assert lab.self_calls == []


def test_sampling_is_stable_and_near_the_configured_share():
    picks = [audit.sampled(os.urandom(64)) for _ in range(20000)]
    share = sum(picks) / len(picks)
    assert abs(share - audit.SAMPLE_PERCENT / 100) < 0.006
    assert audit.sampled(b'same unit bytes') == audit.sampled(b'same unit bytes')


def test_voiced_seconds_measures_voiced_audio():
    assert audit.voiced_seconds(wav_bytes(5)) == pytest.approx(5.0, abs=0.05)
    assert audit.voiced_seconds(wav_bytes(5, voiced=False)) == 0.0


def test_an_unfunded_owner_is_skipped_without_admission_telemetry(lab, monkeypatch):
    from utils import stt_cap_dispatch

    lab.funded = False
    record_audio, record_decision = Mock(), Mock()
    monkeypatch.setattr(stt_cap_dispatch, 'record_audio', record_audio)
    monkeypatch.setattr(stt_cap_dispatch, 'record_decision', record_decision)
    before = skipped('not_funded')

    decision, guard = resolve()

    assert decision.evidence == 'declared'
    assert guard.decision is None
    assert lab.self_calls == [] and lab.vendor_calls == []
    assert skipped('not_funded') == before + 1
    record_audio.assert_not_called()
    record_decision.assert_not_called()


def test_the_funding_check_is_read_only(lab):
    resolve()

    assert lab.funding_calls == [{'lane': 'batch', 'ready_usage_only': True}]


def test_an_owner_with_their_own_stt_is_never_sampled(lab):
    before = skipped('custom_stt')

    decision, _ = resolve(guard=serving_guard(custom_stt=True))

    assert decision.evidence == 'declared'
    assert lab.self_calls == [] and lab.vendor_calls == [] and lab.funding_calls == []
    assert skipped('custom_stt') == before + 1


def test_the_real_pool_runs_the_sample_without_the_callers_deadline(lab, monkeypatch):
    import time

    from utils import executors
    from utils.stt.prerecorded_deadline import verification_deadline, verification_stt_deadline

    seen = []

    def self_detect(probe, *, surface):
        seen.append(verification_deadline.get())
        return lab.verdict

    monkeypatch.setattr(audit.language_gate, 'self_detect', self_detect)
    monkeypatch.setattr(audit, 'declared_language_audit_executor', executors.declared_language_audit_executor)
    before = audited()

    with verification_stt_deadline(time.monotonic() - 1):
        resolve()
    deadline = time.monotonic() + 5
    while not seen and time.monotonic() < deadline:
        time.sleep(0.01)

    assert seen == [None]
    for _ in range(100):
        if audited() == before + 1:
            break
        time.sleep(0.01)
    assert audited() == before + 1


def test_voiced_seconds_reads_the_probe_rate():
    assert audit.voiced_seconds(wav_bytes(5, sample_rate=8000)) == pytest.approx(5.0, abs=0.05)
    assert audit.voiced_seconds(wav_bytes(5, sample_rate=48000)) == pytest.approx(5.0, abs=0.05)


def test_an_unexpected_error_before_submission_is_counted(lab, monkeypatch):
    def broken(audio):
        raise RuntimeError('boom')

    monkeypatch.setattr(audit, 'sampled', broken)
    before = skipped('error')

    decision, _ = resolve()

    assert decision.evidence == 'declared'
    assert skipped('error') == before + 1
