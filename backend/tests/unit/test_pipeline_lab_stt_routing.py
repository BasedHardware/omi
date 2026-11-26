"""Pipeline lab STT routing: production's batch route per audio recording, under an arm's env.

Synthetic inputs only (no network, no real audio): a fake LID answer and a generated tone."""

import json
from pathlib import Path

import numpy as np
import pytest

from testing.pipeline_lab.stt_routing import compare_metrics, routing
from testing.pipeline_lab.stt_routing.routing import MULTILINGUAL, PARAKEET, Inputs, LidCache, RoutingError, decide
from utils.stt.batch_language import LanguageDecision

PROFILE = [{'ja': 33}, {'en': 17, 'ja': 30}, {'vi': 28}]
MULTI_USER = {'language': 'en', 'transcription_preferences': {'single_language_mode': False}}
PCM = (np.sin(np.arange(16000 * 4) / 8.0) * 3000).astype('<i2').tobytes()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for name in (
        'BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED',
        'BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED',
        'BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED',
        'STT_PRERECORDED_MODEL',
    ):
        monkeypatch.delenv(name, raising=False)


def windows(count):
    from testing.pipeline_lab.cassette.adapters import pcm16_to_wav

    return [pcm16_to_wav(PCM[i * 3200 : i * 3200 + 32000] or PCM) for i in range(count)]


@pytest.fixture
def speech(monkeypatch):
    """The product's strict-VAD sample windows, stubbed: synthetic tones have no speech to find."""
    from utils.batch_pipeline import intake

    state = {'count': 3}
    monkeypatch.setattr(intake, '_speech_windows', lambda wav: windows(state['count']) if state['count'] else None)
    return state


def self_lid(language):
    seen = []

    def answer(wav):
        seen.append(len(wav))
        return language(len(seen)) if callable(language) else language

    answer.seen = seen
    return answer


def lid(language, confidence=0.999):
    calls = []

    def answer(pcm16):
        calls.append(len(pcm16))
        return LanguageDecision(language, confidence, 'audio_lid', 30.0)

    answer.calls = calls
    return answer


def test_pinned_en_goes_straight_to_parakeet_without_a_probe():
    probe = lid('zh')
    route = decide(MULTI_USER, {'language': 'en'}, PCM, lid=probe)
    assert (route.route, route.reason, route.language) == (PARAKEET, 'admitted_pinned', 'en')
    assert probe.calls == []


USER = {**MULTI_USER, 'live_stt_language_sessions': PROFILE}
LEGACY = {'STT_PRERECORDED_MODEL': 'parakeet,modulate-velma-2'}


def test_sampled_upload_with_zh_first_window_goes_to_legacy(speech):
    with routing.patched_environ(LEGACY):
        route = decide(USER, {'language': 'en'}, PCM, lid=lid('zh'), self_lid=self_lid('en'))
    assert route.reason == 'legacy:sampled_first_window_unsafe' and route.lid_language == 'zh'
    assert route.route == MULTILINGUAL and route.pieces


def test_sampled_upload_admitted_only_when_every_later_window_is_supported(speech):
    probe = self_lid('en')
    route = decide(USER, {'language': 'en'}, PCM, lid=lid('en'), self_lid=probe)
    assert (route.route, route.reason, route.self_lid_windows) == (PARAKEET, 'sampled:admitted', 2)
    assert len(probe.seen) == 2


def test_one_chinese_window_later_in_the_upload_refuses_it(speech):
    with routing.patched_environ(LEGACY):
        route = decide(
            USER, {'language': 'en'}, PCM, lid=lid('en'), self_lid=self_lid(lambda n: 'zh' if n == 2 else 'en')
        )
    assert route.reason == 'legacy:sampled_later_window_unsupported'


def test_long_and_silent_uploads_are_refused_before_any_probe(speech):
    from utils.batch_pipeline.intake import SAMPLE_SCAN_SECONDS

    probe = lid('en')
    long_pcm = bytes(int(SAMPLE_SCAN_SECONDS + 1) * 32000)
    with routing.patched_environ(LEGACY):
        assert decide(USER, {}, long_pcm, lid=probe, self_lid=self_lid('en')).reason.startswith(
            'legacy:sampled_over_scan_limit'
        )
        speech['count'] = 0
        assert decide(USER, {}, PCM, lid=probe, self_lid=self_lid('en')).reason == 'legacy:sampled_no_speech'


def test_low_confidence_english_first_window_is_not_parakeet_safe(speech):
    with routing.patched_environ(LEGACY):
        route = decide(USER, {'language': 'en'}, PCM, lid=lid('en', 0.6), self_lid=self_lid('en'))
    assert route.reason == 'legacy:sampled_first_window_unsafe'


def test_the_arm_env_decides(speech):
    with routing.patched_environ({**LEGACY, 'BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED': 'false'}):
        assert decide(USER, {'language': 'en'}, PCM, lid=lid('zh'), self_lid=self_lid('en')).reason == 'admitted_pinned'
    with routing.patched_environ(LEGACY):
        assert decide(USER, {'language': 'en'}, PCM, lid=lid('zh'), self_lid=self_lid('en')).route != PARAKEET


def test_legacy_files_route_separately_and_mix():
    answers = iter(['en', 'zh'])

    def per_file(pcm16):
        return LanguageDecision(next(answers, 'zh'), 0.999, 'audio_lid', 2.0)

    two_files = bytes(32000 * 4)
    with routing.patched_environ(LEGACY):
        route = decide(USER, {'language': 'zz-unknown'}, two_files, lid=per_file, legacy_file_seconds=2)
    assert route.route == routing.MIXED and [p[2] for p in route.pieces] == [PARAKEET, MULTILINGUAL]


def test_patched_environ_restores_and_skips_lab_keys(monkeypatch):
    monkeypatch.setenv('BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED', 'true')
    with routing.patched_environ(
        {'BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED': 'false', routing.INPUTS_ENV: '/private/inputs.json'}
    ):
        import os

        assert os.environ['BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED'] == 'false'
        assert routing.INPUTS_ENV not in os.environ
    import os

    assert os.environ['BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED'] == 'true'


def test_cassette_pin_maps_a_route_to_its_stand_in():
    route = decide(MULTI_USER, {'language': 'en'}, PCM, lid=lid('en'))
    pin = routing.cassette_pin(route, {PARAKEET: {'provider': 'parakeet_local', 'model': 'cpu'}})
    assert pin == {'provider': 'parakeet_local', 'model': 'cpu', 'language': 'en'}
    mixed = routing.cassette_pin(route, {MULTILINGUAL: {'provider': 'modulate', 'model': 'velma-2'}}, MULTILINGUAL)
    assert mixed == {'provider': 'modulate', 'model': 'velma-2', 'language': 'multi'}


def test_inputs_and_enable_flag(tmp_path):
    assert not routing.enabled({})
    assert routing.enabled({routing.ROUTING_ENV: 'product'})
    with pytest.raises(RoutingError):
        Inputs.load({})
    path = tmp_path / 'inputs.json'
    path.write_text(json.dumps({'user': MULTI_USER, 'conversations': {'A': {'language': 'de'}}}))
    inputs = Inputs.load({routing.INPUTS_ENV: str(path)})
    assert inputs.conversation('A') == {'language': 'de'} and inputs.conversation('B') == {}


def test_lid_cache_replays_and_refuses_a_miss_without_record(tmp_path):
    cache = LidCache(tmp_path, record=False)
    with pytest.raises(RoutingError, match='no recorded LID answer'):
        cache.decision(PCM)
    body, _ = routing._probe(PCM)
    import hashlib

    (tmp_path / 'lid').mkdir()
    (tmp_path / 'lid' / f'{hashlib.sha256(body).hexdigest()}.json').write_text(
        json.dumps({'language': 'zh', 'confidence': 0.99, 'evidence': 'audio_lid'})
    )
    decision = cache.decision(PCM)
    assert (decision.language, decision.parakeet_safe, cache.calls) == ('zh', False, 0)


def test_compare_metric_counts_unsupported_speech_on_parakeet(tmp_path, monkeypatch):
    run = tmp_path / 'arm'
    (run / 'evening').mkdir(parents=True)
    (run / 'verdict.json').write_text(json.dumps({'scenarios': [{'name': 'evening'}]}))
    rows = [
        {'audio_seconds': 60.0, 'route': {'route': 'parakeet', 'reason': 'admitted_pinned', 'audio_sha256': 'aaaa'}},
        {'audio_seconds': 30.0, 'route': {'route': 'multilingual', 'lid_language': 'zh', 'audio_sha256': 'bbbb'}},
        {'audio_seconds': 10.0, 'route': {'route': 'parakeet', 'audio_sha256': 'cccc'}},
    ]
    (run / 'evening' / 'result.json').write_text(json.dumps({'audio': {'recordings': rows}}))
    reference = tmp_path / 'reference.json'
    reference.write_text(
        json.dumps({'aaaa': {'speech_s': 50, 'unsupported_s': 40}, 'bbbb': {'speech_s': 25, 'unsupported_s': 20}})
    )
    monkeypatch.setenv(compare_metrics.REFERENCE_ENV, str(reference))
    out = compare_metrics.stt_routing_metrics(Path(run))
    assert out['recordings'] == 3 and out['parakeet_recordings'] == 2 and out['lid_probes'] == 1
    assert out['unsupported_on_parakeet_s'] == 40 and out['unsupported_s'] == 60 and out['unreferenced'] == 1
    assert out['unsupported_on_parakeet_share'] == round(40 / 60, 3)
