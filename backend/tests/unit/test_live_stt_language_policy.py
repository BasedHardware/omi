"""Live language prior, dark routing, and bounded conformance telemetry."""

import asyncio
from types import SimpleNamespace

import pytest

from config.stt_provider_policy import SONIOX_PROVIDER
from utils.stt import streaming as st
from utils.stt.language_policy import (
    MAX_DETECTION_CHARS,
    MAX_PENDING_DETECTIONS,
    LiveLanguageObservations,
    LiveLanguageProfile,
    classify_output,
    hintable_allocation,
    observe_live_segments,
    record_live_connection,
    soniox_hints,
)
from utils.stt.live_metrics import LANGUAGE_CONSTRAINT, OUTPUT_LANGUAGE_SEGMENTS
from utils.stt.live_rollout import window_allocation
from utils.stt.provider_resilience import ProviderCircuitBreaker


@pytest.mark.parametrize(
    'language,multi,expected,group',
    [
        ('pt-BR', True, ('pt', 'en'), 'non_en'),
        ('pt', False, ('pt',), 'non_en'),
        ('en-US', True, ('en',), 'en'),
        ('multi', True, (), 'unknown'),
        ('', False, (), 'unknown'),
    ],
)
def test_session_profile(monkeypatch, language, multi, expected, group):
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '100')
    profile = LiveLanguageProfile.create(language, multi=multi, uid='stable-user')
    assert (profile.expected, profile.primary_group) == (expected, group)
    assert profile.arm == ('hintable' if multi and group == 'non_en' else 'na')


def test_hash_allocation_is_stable_and_dark_by_default(monkeypatch):
    monkeypatch.delenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', raising=False)
    assert not hintable_allocation('u')
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '25')
    allocation = [hintable_allocation(str(i)) for i in range(1000)]
    assert allocation == [hintable_allocation(str(i)) for i in range(1000)]
    assert 200 < sum(allocation) < 300
    assert not hintable_allocation(None)


def test_hintable_bucket_has_an_independent_salt(monkeypatch):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '50')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '50')
    assert any(hintable_allocation(str(uid)) != window_allocation(str(uid)) for uid in range(100))


@pytest.mark.parametrize('surface', ['multi_channel', 'custom_stt', 'byok'])
def test_out_of_scope_sessions_keep_the_existing_selection_and_hints(monkeypatch, surface):
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '100')
    monkeypatch.setenv('SONIOX_API_KEY', 'local-test-key')
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    profile = LiveLanguageProfile.create('pt', multi=True, uid=surface, in_scope=False)
    assert profile.arm == 'na'
    assert st.get_stt_service_for_language('pt', language_profile=profile)[0] == st.STTService.modulate
    assert soniox_hints('multi', profile) == []


def test_hint_vocabulary_filters_each_code_and_preserves_identification(monkeypatch):
    profile = LiveLanguageProfile.create('mt', multi=True, uid='u')
    assert soniox_hints('multi', profile) == ['en']
    monkeypatch.setenv('STT_MULTI_LANGUAGE_HINTS', 'false')
    assert soniox_hints('multi', profile) == []


@pytest.mark.parametrize('configured_order', ['true', 'false'])
def test_hintable_arm_prefers_soniox_but_respects_exclude_key_and_breaker(monkeypatch, configured_order):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', configured_order)
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '100')
    monkeypatch.setenv('SONIOX_API_KEY', 'local-test-key')
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    circuit = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    monkeypatch.setattr(st, '_soniox_circuit', circuit)
    profile = LiveLanguageProfile.create('pt', multi=True, uid='u')
    selected = lambda **kwargs: st.get_stt_service_for_language('pt', language_profile=profile, **kwargs)[0]
    assert selected() == st.STTService.soniox
    assert selected(exclude=frozenset({SONIOX_PROVIDER})) == st.STTService.modulate
    monkeypatch.setenv('SONIOX_API_KEY', '')
    assert selected() == st.STTService.modulate
    monkeypatch.setenv('SONIOX_API_KEY', 'local-test-key')
    circuit.record_failure()
    assert selected() == st.STTService.modulate
    account_circuit = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    monkeypatch.setattr(st, '_soniox_circuit', account_circuit)
    account_circuit.record_account_rejection()
    assert selected() == st.STTService.modulate
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '0')
    control = LiveLanguageProfile.create('pt', multi=True, uid='u')
    assert control.arm == 'control'
    assert st.get_stt_service_for_language('pt', language_profile=control)[0] == st.STTService.modulate


def test_hintable_arm_respects_provider_enablement(monkeypatch):
    from utils.stt import language_policy

    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '100')
    monkeypatch.setenv('SONIOX_API_KEY', 'local-test-key')
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    monkeypatch.setattr(language_policy, 'provider_is_enabled', lambda provider, _surface: provider != SONIOX_PROVIDER)
    profile = LiveLanguageProfile.create('pt', multi=True, uid='u')
    assert st.get_stt_service_for_language('pt', language_profile=profile)[0] == st.STTService.modulate


def test_explicit_parakeet_preference_keeps_existing_fallback_order(monkeypatch):
    monkeypatch.setenv('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '100')
    monkeypatch.setenv('SONIOX_API_KEY', 'local-test-key')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://local-test.invalid')
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox', 'parakeet'])
    profile = LiveLanguageProfile.create('pt', multi=True, uid='u')
    # This auto-detect request is outside Parakeet's vocabulary, so the
    # existing preference path falls through to Velma rather than Soniox.
    assert (
        st.get_stt_service_for_language('pt', language_profile=profile, preferred_service='parakeet')[0]
        == st.STTService.modulate
    )


@pytest.mark.parametrize('configured_order', [True, False])
@pytest.mark.asyncio
async def test_failed_preferred_soniox_falls_into_normal_chain(monkeypatch, configured_order):
    monkeypatch.setattr('utils.stt.provider_resilience.STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])
    monkeypatch.setattr(st, '_soniox_circuit', ProviderCircuitBreaker(failure_threshold=2, cooldown_seconds=30))
    calls = []

    async def soniox():
        calls.append('soniox')
        raise RuntimeError('unavailable')

    async def modulate():
        calls.append('modulate')
        return SimpleNamespace(is_connection_dead=False, finish=lambda: None)

    _, actual = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.soniox,
        connect_primary=soniox,
        connect_modulate=modulate,
        use_config=configured_order,
    )
    assert actual == st.STTService.modulate
    assert calls == ['soniox', 'modulate']


def test_classification_prefers_provider_language_and_keeps_short_segments_unknown(monkeypatch):
    profile = LiveLanguageProfile.create('pt', multi=True, uid='u')
    assert classify_output('a', profile, 'pt') == ('in_profile', 'pt')
    assert classify_output('a', profile, 'it') == ('out_of_profile', 'it')
    assert classify_output('a', profile, 'pt-BR') == ('in_profile', 'pt')
    zh = LiveLanguageProfile.create('zh-CN', multi=True, uid='u')
    assert classify_output('a', zh, 'zh-cn') == ('in_profile', 'zh')
    assert classify_output('a', profile) == ('undetermined', None)
    monkeypatch.setattr('utils.stt.language_policy.detect_langs', lambda _: [SimpleNamespace(lang='it', prob=0.99)])
    assert classify_output('a' * 24, profile) == ('out_of_profile', 'it')
    monkeypatch.setattr('utils.stt.language_policy.detect_langs', lambda _: [SimpleNamespace(lang='it', prob=0.80)])
    assert classify_output('a' * 24, profile) == ('undetermined', None)
    seen = []
    monkeypatch.setattr(
        'utils.stt.language_policy.detect_langs',
        lambda value: (seen.append(value), [SimpleNamespace(lang='pt-br', prob=0.99)])[1],
    )
    assert classify_output('a' * 1000, profile) == ('in_profile', 'pt')
    assert len(seen[0]) == MAX_DETECTION_CHARS
    unknown = LiveLanguageProfile.create('multi', multi=True, uid='u')
    assert classify_output('a' * 30, unknown, 'it') == ('undetermined', None)


@pytest.mark.asyncio
async def test_metric_labels_and_ephemeral_language_metadata(monkeypatch):
    monkeypatch.setattr('utils.stt.language_policy.detect_langs', lambda _: [SimpleNamespace(lang='it', prob=0.99)])
    profile = LiveLanguageProfile.create('pt', multi=True, uid='u')
    observations = LiveLanguageObservations(profile)
    constraint = LANGUAGE_CONSTRAINT.labels('soniox', 'hinted', 'non_en', profile.arm)
    out = OUTPUT_LANGUAGE_SEGMENTS.labels('soniox', 'non_en', profile.arm, 'out_of_profile')
    before_constraint, before_out = constraint._value.get(), out._value.get()
    observations.connected('soniox', 'multi')
    segment = {'text': 'a' * 24, '_provider_language': 'it'}
    observations.observe(segment, 'soniox', lambda coro, name: asyncio.create_task(coro, name=name))
    assert '_provider_language' not in segment
    observations.observe({'text': 'a' * 24}, 'soniox', lambda coro, name: asyncio.create_task(coro, name=name))
    await observations.summarize()
    assert constraint._value.get() == before_constraint + 1
    assert out._value.get() == before_out + 2
    assert observations.counts['out_of_profile'] == 2


@pytest.mark.asyncio
async def test_invalid_provider_code_uses_the_off_loop_detector(monkeypatch):
    monkeypatch.setattr('utils.stt.language_policy.detect_langs', lambda _: [SimpleNamespace(lang='it', prob=0.99)])
    observations = LiveLanguageObservations(LiveLanguageProfile.create('pt', multi=True, uid='u'))
    spawned = []

    def spawn(coro, name):
        spawned.append(name)
        return asyncio.create_task(coro, name=name)

    segment = {'text': 'a' * 24, '_provider_language': 'unbounded-provider-value'}
    observations.observe(segment, 'soniox', spawn)
    await observations.summarize()
    assert spawned == ['stt_language_detect']
    assert observations.counts['out_of_profile'] == 1


def test_client_provider_label_cannot_expand_metric_cardinality():
    observations = LiveLanguageObservations(LiveLanguageProfile.create('pt', multi=True, uid='u'))
    host = SimpleNamespace(
        use_custom_stt=False,
        language_observations=observations,
        stt_language='multi',
        spawn=None,
    )
    record_live_connection(host, 'arbitrary-client-string')
    observe_live_segments(host, [{'text': 'a', '_provider_language': 'it'}], 'arbitrary-client-string')
    assert observations.providers == {'other'}
    assert observations.counts['out_of_profile'] == 1
    host.use_custom_stt = True
    observe_live_segments(host, [{'text': 'a', '_provider_language': 'it'}], 'arbitrary-client-string')
    assert observations.counts['out_of_profile'] == 1


def test_telemetry_failure_cannot_abort_segment_delivery():
    observations = LiveLanguageObservations(LiveLanguageProfile.create('pt', multi=True, uid='u'))
    host = SimpleNamespace(
        use_custom_stt=False,
        language_observations=observations,
        stt_language='multi',
        spawn=lambda _coro, name: (_ for _ in ()).throw(RuntimeError(name)),
    )
    segment = {'text': 'a' * 24, '_provider_language': 'invalid-code'}
    observe_live_segments(host, [segment], 'soniox')
    assert segment == {'text': 'a' * 24}


def test_full_detector_queue_records_one_undetermined_segment():
    observations = LiveLanguageObservations(LiveLanguageProfile.create('pt', multi=True, uid='u'))
    observations.pending.update(object() for _ in range(MAX_PENDING_DETECTIONS))
    segment = {'text': 'a' * 24}
    observations.observe(segment, 'soniox', lambda _coro, name: pytest.fail(f'unexpected spawn: {name}'))
    assert observations.counts == {'undetermined': 1}
