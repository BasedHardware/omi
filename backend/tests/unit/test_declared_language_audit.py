"""Declared-supported batch units are sampled for a self-gate language audit; routing never changes."""

from io import BytesIO
import threading
import wave

import pytest
from prometheus_client import REGISTRY

from utils.stt import batch_language, declared_language_audit as audit
from utils.stt.language_gate import SelfVerdict


def wav_bytes(seconds=40, sample_rate=16000):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, sample_rate, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * sample_rate))
    return output.getvalue()


class Inline:
    def submit(self, fn, *args):
        fn(*args)


def count(declared, heard, heard_class, confident):
    value = REGISTRY.get_sample_value(
        'omi_batch_pipeline_declared_language_audit_total',
        {'declared': declared, 'heard': heard, 'heard_class': heard_class, 'confident': confident},
    )
    return value or 0.0


def skipped(reason):
    return (
        REGISTRY.get_sample_value('omi_batch_pipeline_declared_language_audit_skipped_total', {'reason': reason}) or 0.0
    )


@pytest.fixture
def gate(monkeypatch):
    calls = []
    verdict = {'value': SelfVerdict('zh', 0.97, 0.02, 30.0)}

    def self_detect(probe, *, surface):
        calls.append((len(probe), surface))
        if isinstance(verdict['value'], Exception):
            raise verdict['value']
        return verdict['value']

    monkeypatch.delenv('BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED', raising=False)
    monkeypatch.setattr(audit.language_gate, 'self_detect', self_detect)
    monkeypatch.setattr(audit, '_POOL', Inline())
    monkeypatch.setattr(audit, '_PENDING', threading.BoundedSemaphore(audit.MAX_PENDING))
    monkeypatch.setattr(audit, 'sampled', lambda audio: True)
    return calls, verdict


def test_a_declared_english_unit_is_audited_and_still_routed_as_declared(gate):
    calls, _ = gate
    before = count('en', 'zh', 'unsupported', 'true')

    decision = batch_language.resolve_language('en', wav_bytes(), surface='batch')

    assert (decision.language, decision.evidence) == ('en', 'declared')
    assert count('en', 'zh', 'unsupported', 'true') == before + 1
    # Only the first 30 s of the 40 s unit reaches the gate.
    assert calls[0][1] == 'batch_audit'
    assert calls[0][0] <= 30 * 16000 * 2 + 100


def test_a_low_confidence_verdict_is_labelled_not_confident(gate):
    _, verdict = gate
    verdict['value'] = SelfVerdict('hi', 0.55, 0.3, 30.0)
    before = count('en', 'hi', 'unsupported', 'false')

    batch_language.resolve_language('en', wav_bytes(), surface='batch')

    assert count('en', 'hi', 'unsupported', 'false') == before + 1


def test_an_unavailable_gate_is_counted_as_unavailable(gate):
    _, verdict = gate
    verdict['value'] = None
    before = count('en', 'unavailable', 'unavailable', 'false')

    batch_language.resolve_language('en', wav_bytes(), surface='batch')

    assert count('en', 'unavailable', 'unavailable', 'false') == before + 1


def test_a_gate_error_is_skipped_and_releases_its_slot(gate, monkeypatch):
    _, verdict = gate
    verdict['value'] = RuntimeError('boom')
    monkeypatch.setattr(audit, '_PENDING', threading.BoundedSemaphore(1))
    before = skipped('error')

    batch_language.resolve_language('en', wav_bytes(), surface='batch')
    batch_language.resolve_language('en', wav_bytes(), surface='batch')

    assert skipped('error') == before + 2


def test_a_full_pool_skips_without_blocking(gate, monkeypatch):
    calls, _ = gate
    monkeypatch.setattr(audit, '_PENDING', threading.BoundedSemaphore(1))
    audit._PENDING.acquire()
    before = skipped('busy')
    try:
        decision = batch_language.resolve_language('en', wav_bytes(), surface='batch')
    finally:
        audit._PENDING.release()

    assert decision.evidence == 'declared'
    assert calls == []
    assert skipped('busy') == before + 1


def test_undecodable_audio_is_skipped(gate):
    calls, _ = gate
    before = skipped('decode_or_submit')

    decision = batch_language.resolve_language('en', b'not a wav', surface='batch')

    assert decision.evidence == 'declared'
    assert calls == []
    assert skipped('decode_or_submit') == before + 1


@pytest.mark.parametrize('surface', ['prerecorded', 'batch_shadow'])
def test_other_surfaces_are_not_audited(gate, surface):
    calls, _ = gate

    batch_language.resolve_language('en', wav_bytes(), surface=surface)

    assert calls == []


def test_a_declared_unsupported_language_is_not_audited(gate):
    calls, _ = gate

    batch_language.resolve_language('ja', wav_bytes(), surface='batch')

    assert calls == []


def test_kill_switch_stops_sampling(gate, monkeypatch):
    calls, _ = gate
    monkeypatch.setenv('BATCH_DECLARED_LANGUAGE_AUDIT_ENABLED', 'false')

    batch_language.resolve_language('en', wav_bytes(), surface='batch')

    assert calls == []


def test_unsampled_audio_is_not_audited(gate, monkeypatch):
    calls, _ = gate
    monkeypatch.setattr(audit, 'sampled', lambda audio: False)

    batch_language.resolve_language('en', wav_bytes(), surface='batch')

    assert calls == []


def test_sampling_is_stable_and_near_the_configured_share():
    import os

    picks = [audit.sampled(os.urandom(64)) for _ in range(20000)]
    share = sum(picks) / len(picks)
    assert abs(share - audit.SAMPLE_PERCENT / 100) < 0.006
    audio = b'same unit bytes'
    assert audit.sampled(audio) == audit.sampled(audio)
