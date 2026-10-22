"""Self-hosted language gate: shadow beside the vendor probe, cohort enforcement, safe fallback."""

from io import BytesIO
import logging
import wave
from unittest.mock import Mock

import httpx
import pytest

from config.prerecorded_language import language_gate_percent, self_lid_confidence_floor
from utils.stt import batch_language as lid
from utils.stt import language_gate as gate
from utils.stt import pre_recorded as stt

PARAKEET_URL = 'http://parakeet.test'
GATE_URL = PARAKEET_URL + '/v2/language'


def wav(seconds=6.0):
    output = BytesIO()
    with wave.open(output, 'wb') as writer:
        writer.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        writer.writeframes(b'\x01\x00' * int(seconds * 16000))
    return output.getvalue()


def response(status, body):
    result = Mock(status_code=status)
    result.json.return_value = body
    result.raise_for_status = Mock(
        side_effect=None if status < 400 else httpx.HTTPStatusError('x', request=Mock(), response=result)
    )
    return result


def gate_body(language='en', p_supported=0.99, seconds=6.0, top_p=None):
    return {
        'route': 'parakeet' if p_supported >= 0.9 else 'multilingual',
        'p_supported': p_supported,
        'language': language,
        'language_probability': p_supported if top_p is None else top_p,
        'audio_seconds': seconds,
        'threshold': 0.9,
        'model': 'whisper-base',
    }


class Wire:
    """One fake httpx.Client for both hosts, answering by URL."""

    def __init__(self, monkeypatch, *, vendor=('en', 0.99), self_gate=None, self_status=200):
        self.calls = []
        self.vendor = vendor
        self.self_gate = gate_body() if self_gate is None else self_gate
        self.self_status = self_status
        monkeypatch.setattr(httpx, 'Client', self)

    def __call__(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self.calls.append(url)
        if url == GATE_URL:
            if isinstance(self.self_status, Exception):
                raise self.self_status
            return response(self.self_status, self.self_gate)
        code, confidence = self.vendor
        return response(200, {'predicted_language_code': code, 'confidence': confidence, 'duration_ms': 6000})

    @property
    def vendor_calls(self):
        return [url for url in self.calls if url == lid.LID_URL]

    @property
    def gate_calls(self):
        return [url for url in self.calls if url == GATE_URL]


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    for name in (
        'STT_PRERECORDED_LANGUAGE_GUARD_ENABLED',
        'STT_PRERECORDED_SHORT_LID_GUARD_ENABLED',
        'STT_PRERECORDED_LANGUAGE_GATE_SHADOW',
        'STT_PRERECORDED_LANGUAGE_GATE_PERCENT',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('STT_PRERECORDED_MODEL', 'parakeet,modulate-velma-2')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-not-a-key')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', PARAKEET_URL + '/')


def shadow_count(**labels):
    base = dict(
        surface='prerecorded',
        self_route='parakeet',
        vendor_route='parakeet',
        self_bucket='en',
        vendor_bucket='en',
        vendor_conf='ge90',
        dur_bucket='6to10',
    )
    base.update(labels)
    return gate.SHADOW.labels(**base)._value.get()


def test_shadow_is_default_and_never_changes_the_vendor_route(monkeypatch):
    # Self gate says Arabic; the vendor route still decides while shadowing.
    wire = Wire(monkeypatch, vendor=('en', 0.99), self_gate=gate_body('ar', 0.0003))
    before = shadow_count(self_route='multilingual', self_bucket='ar')
    decision = lid.resolve_language('multi', wav())
    assert decision.evidence == 'audio_lid' and decision.parakeet_safe
    assert len(wire.vendor_calls) == 1 and len(wire.gate_calls) == 1
    assert shadow_count(self_route='multilingual', self_bucket='ar') == before + 1


def test_shadow_kill_switch_skips_the_gate_call(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_SHADOW', 'false')
    wire = Wire(monkeypatch)
    assert lid.resolve_language('multi', wav()).evidence == 'audio_lid'
    assert wire.gate_calls == [] and len(wire.vendor_calls) == 1


def test_declared_language_calls_neither_detector(monkeypatch):
    wire = Wire(monkeypatch)
    assert lid.resolve_language('en', wav()).evidence == 'declared'
    assert wire.calls == []


def test_dangerous_shadow_disagreement_is_logged_without_content(monkeypatch, caplog):
    Wire(monkeypatch, vendor=('ja', 0.97), self_gate=gate_body('en', 0.995))
    before = shadow_count(vendor_route='multilingual', vendor_bucket='ja')
    with caplog.at_level(logging.WARNING):
        lid.resolve_language('multi', wav())
    assert shadow_count(vendor_route='multilingual', vendor_bucket='ja') == before + 1
    assert 'event=language_gate_shadow_disagreement' in caplog.text
    assert 'vendor_language=ja' in caplog.text


def test_arabic_canary_vendor_english_permission_is_refused_when_enforced(monkeypatch, tmp_path):
    """Staging canary 10-22 05:29Z: Modulate called 6 s Arabic `en` at 0.9258 and selected Parakeet."""
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    wire = Wire(monkeypatch, vendor=('en', 0.9258145093917847), self_gate=gate_body('ar', 0.0003, 5.536, 0.9963))
    path = tmp_path / 'arabic.wav'
    path.write_bytes(wav(5.536))
    assert lid.resolve_file('multi', path, selector=stt.get_prerecorded_service, cohort_key='uid-1')[0] == 'modulate'
    assert wire.vendor_calls == []


def test_enforced_supported_audio_goes_to_parakeet_without_the_vendor_probe(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    wire = Wire(monkeypatch, vendor=('ja', 0.99), self_gate=gate_body('en', 0.996))
    parakeet = Mock()
    monkeypatch.setattr(stt, 'ParakeetPrerecordedProvider', lambda: parakeet)
    multilingual = Mock(side_effect=AssertionError('supported speech must stay on Parakeet'))
    monkeypatch.setattr(stt, 'ModulatePrerecordedProvider', multilingual)
    assert stt.prerecorded_from_bytes(wav(), language='multi') is parakeet.transcribe_bytes.return_value
    assert wire.vendor_calls == [] and len(wire.gate_calls) == 1


@pytest.mark.parametrize('failure', [503, 500, httpx.ReadTimeout('slow'), 'malformed'])
def test_enforced_gate_failure_falls_back_to_the_vendor_probe(monkeypatch, failure):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    if failure == 'malformed':
        wire = Wire(monkeypatch, vendor=('ja', 0.99), self_gate={'route': 'parakeet'})
    else:
        wire = Wire(monkeypatch, vendor=('ja', 0.99), self_status=failure)
    before = gate.ENFORCED.labels('prerecorded', 'vendor_fallback', 'und')._value.get()
    decision = lid.resolve_language('multi', wav())
    assert decision.evidence == 'audio_lid' and decision.language == 'ja' and not decision.parakeet_safe
    assert len(wire.vendor_calls) == 1
    assert gate.ENFORCED.labels('prerecorded', 'vendor_fallback', 'und')._value.get() == before + 1


def test_service_route_is_not_trusted_over_the_backend_threshold(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    body = gate_body('en', 0.85)
    body['route'] = 'parakeet'
    Wire(monkeypatch, self_gate=body)
    assert not lid.resolve_language('multi', wav()).parakeet_safe


@pytest.mark.parametrize(
    'seconds,p_supported,safe',
    [
        (0.9, 0.999, False),
        (3.0, 0.9778, False),  # highest offline P(supported) on 3 s unsupported speech
        (3.0, 0.984, False),
        (3.0, 0.985, True),
        (5.99, 0.98, False),
        (6.0, 0.9218, False),  # highest offline P(supported) on >=6 s unsupported speech
        (6.0, 0.95, True),
        (30, 0.949, False),
    ],
)
def test_self_gate_threshold_by_measured_seconds(monkeypatch, seconds, p_supported, safe):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    Wire(monkeypatch, self_gate=gate_body('en', p_supported, seconds))
    assert lid.resolve_language('multi', wav(max(seconds, 1))).parakeet_safe is safe


def test_unsupported_top_language_is_never_parakeet_even_with_high_p_supported():
    assert not lid.LanguageDecision('sqi', 0.97, 'self_lid', 10).parakeet_safe
    assert lid.LanguageDecision('pt', 0.97, 'self_lid', 10).parakeet_safe
    assert not lid.LanguageDecision('pt', 0.97, 'self_lid', None).parakeet_safe


def test_batch_intake_is_shadow_only_even_at_full_enforcement(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    wire = Wire(monkeypatch, vendor=('en', 0.99), self_gate=gate_body('ar', 0.0))
    decision = lid.resolve_language('multi', wav(), surface='batch')
    assert decision.evidence == 'audio_lid'
    assert len(wire.vendor_calls) == 1 and len(wire.gate_calls) == 1


@pytest.mark.parametrize('raw,value', [(None, 0), ('0', 0), ('5', 5), ('25', 25), ('100', 100), ('150', 100),
                                       ('-3', 0), ('5%', 0), ('', 0), ('typo', 0)])  # fmt: skip
def test_percent_parsing_never_widens_on_malformed_values(monkeypatch, raw, value):
    if raw is not None:
        monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', raw)
    assert language_gate_percent() == value


def test_uid_cohort_is_stable_and_proportional(monkeypatch):
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '25')
    probe = wav(1)
    picks = [gate.enforced_for(f'uid-{i}', probe) for i in range(4000)]
    assert 0.22 < sum(picks) / len(picks) < 0.28
    assert picks == [gate.enforced_for(f'uid-{i}', b'other audio') for i in range(4000)]
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '0')
    assert not any(gate.enforced_for(f'uid-{i}', probe) for i in range(200))


def test_gate_probe_is_bounded_to_30_seconds(monkeypatch):
    captured = {}

    class Client(Wire):
        def post(self, url, **kwargs):
            if url == GATE_URL:
                captured['body'] = kwargs['files']['file'][1]
            return super().post(url, **kwargs)

    Client(monkeypatch)
    lid.resolve_language('multi', wav(65))
    with wave.open(BytesIO(captured['body']), 'rb') as source:
        assert source.getnframes() == 30 * 16000


def test_no_parakeet_url_is_unavailable_not_a_verdict(monkeypatch):
    monkeypatch.delenv('HOSTED_PARAKEET_API_URL')
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '100')
    wire = Wire(monkeypatch, vendor=('en', 0.99))
    assert lid.resolve_language('multi', wav()).evidence == 'audio_lid'
    assert wire.gate_calls == []


@pytest.mark.parametrize('seconds', [None, True, float('nan'), 0.5])
def test_unmeasured_or_tiny_self_probe_has_no_floor(seconds):
    assert self_lid_confidence_floor(seconds) is None
