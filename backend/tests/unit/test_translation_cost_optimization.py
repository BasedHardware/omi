from __future__ import annotations

import asyncio

import pytest

from config.translation import TranslationProvider
from tests.unit.translation_test_support import (
    DictTranslationStore,
    FakeProvider,
    build_service,
    profile,
    provider_error,
    translations,
)
from utils.translation import TranslationStatus
from utils.translation_cache import ConversationLanguageState
from utils.translation_coordinator import (
    STABILITY_IS_FINAL,
    STABILITY_PUNCTUATION,
    STABILITY_SOFT_BOUNDARY,
    STABILITY_SPEAKER_SWITCH,
    TranslationCoordinator,
    _compute_stability_signals,
    _is_text_stable,
)
from utils.translation_core.cache import CachedTranslation
from utils.translation_core.planner import fingerprint_text


def test_duplicate_sentences_are_sent_to_provider_once_and_reassembled():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[translations(('Bonjour.', 'en'), ('Partagé.', 'en'), ('Au revoir.', 'en'))],
    )
    service, _cache = build_service({TranslationProvider.google: provider})

    results = service.translate_outcomes(
        'fr',
        [('first', 'Hello. Shared.'), ('second', 'Shared. Bye.')],
    )

    assert [result.text for result in results] == ['Bonjour. Partagé.', 'Partagé. Au revoir.']
    assert provider.calls[0]['contents'] == ['Hello.', 'Shared.', 'Bye.']


def test_duplicate_unit_ids_preserve_order_and_identity():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[translations(('Uno.', 'en'), ('Dos.', 'en'))],
    )
    service, _cache = build_service({TranslationProvider.google: provider})

    results = service.translate_outcomes('es', [('same-id', 'One.'), ('same-id', 'Two.')])

    assert len(results) == 2
    assert [result.ordinal for result in results] == [0, 1]
    assert [result.unit_id for result in results] == ['same-id', 'same-id']
    assert [result.text for result in results] == ['Uno.', 'Dos.']


def test_output_cardinality_always_equals_input_cardinality_including_empty_text():
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service({TranslationProvider.google: provider})

    results = service.translate_outcomes('es', [('empty', ''), ('full', 'Hello')])

    assert len(results) == 2
    assert results[0].status == TranslationStatus.unchanged
    assert results[0].text == ''
    assert results[1].text == 'Hola'


def test_source_language_reaches_the_provider():
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service({TranslationProvider.google: provider})

    service.translate_units_batch('es', [('segment', 'Hello')], source_language='en')

    assert provider.calls[0]['source_language'] == 'en'


def test_max_batch_size_chunks_provider_calls_without_changing_output_order():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[
            translations(('Uno.', 'en'), ('Dos.', 'en')),
            translations(('Tres.', 'en'), ('Cuatro.', 'en')),
            translations(('Cinco.', 'en')),
        ],
    )
    service, _cache = build_service(
        {TranslationProvider.google: provider},
        selected_profile=profile(max_batch_size=2),
    )

    outcomes = service.translate_outcomes('es', [('unit', 'One. Two. Three. Four. Five.')])

    assert outcomes[0].text == 'Uno. Dos. Tres. Cuatro. Cinco.'
    assert [call['contents'] for call in provider.calls] == [
        ['One.', 'Two.'],
        ['Three.', 'Four.'],
        ['Five.'],
    ]


def test_dominant_detected_language_is_reconstructed_from_sentence_results():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[translations(('Un.', 'en'), ('Deux.', 'fr'), ('Trois.', 'en'))],
    )
    service, _cache = build_service({TranslationProvider.google: provider})

    outcome = service.translate_outcomes('fr', [('unit', 'One. Two. Three.')])[0]

    assert outcome.detected_language == 'en'
    assert outcome.text == 'Un. Deux. Trois.'


def test_full_text_cache_hit_skips_provider_even_with_duplicate_unit_ids():
    store = DictTranslationStore()
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Deux.', 'en'))])
    service, cache = build_service({TranslationProvider.google: provider}, store=store)
    cache.put(fingerprint_text('One.'), 'fr', CachedTranslation('Un.', 'en'), profile())

    outcomes = service.translate_outcomes('fr', [('same', 'One.'), ('same', 'Two.')])

    assert [outcome.text for outcome in outcomes] == ['Un.', 'Deux.']
    assert provider.calls[0]['contents'] == ['Two.']


def test_negative_sentence_cache_and_provider_result_reconstruct_one_complete_unit():
    store = DictTranslationStore()
    store.negative.add((fingerprint_text('Already.'), 'en'))
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hello.', 'es'))])
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)

    outcome = service.translate_outcomes('en', [('unit', 'Already. Hola.')])[0]

    assert outcome.status == TranslationStatus.translated
    assert outcome.text == 'Already. Hello.'
    assert provider.calls[0]['contents'] == ['Hola.']


@pytest.mark.parametrize(
    ('text', 'signals', 'expected'),
    [
        ('Hello.', set(), True),
        ('你好。', set(), True),
        ('नमस्ते।', set(), True),
        ('مرحبا؟', set(), True),
        ('Hello', {STABILITY_PUNCTUATION}, True),
        ('Hello', {STABILITY_SPEAKER_SWITCH}, True),
        ('Hello', {STABILITY_IS_FINAL}, True),
        ('Hello', {STABILITY_SOFT_BOUNDARY}, True),
        ('Hello', set(), False),
        ('', {STABILITY_IS_FINAL}, False),
    ],
)
def test_text_stability_contract(text, signals, expected):
    assert _is_text_stable(text, signals) is expected


def test_stability_signal_computation_combines_content_time_speaker_and_size():
    signals = _compute_stability_signals(
        'one two three four five six seven eight nine ten eleven twelve.',
        last_update_at=1.0,
        now=4.0,
        prev_speaker_id=1,
        curr_speaker_id=2,
    )

    assert signals == {STABILITY_PUNCTUATION, STABILITY_SPEAKER_SWITCH, STABILITY_SOFT_BOUNDARY}


def test_conversation_language_gate_enters_target_mode_and_exits_on_foreign(monkeypatch):
    detections = iter([('en', 0.99)] * 4 + [('fr', 0.99)])
    monkeypatch.setattr(
        'utils.translation_cache.detect_language_with_confidence',
        lambda *_args, **_kwargs: next(detections),
    )
    state = ConversationLanguageState('en-US')

    assert [state.observe('target text', speaker_id=1) for _ in range(4)] == [False, False, False, True]
    assert state.monolingual
    assert not state.observe('foreign text', speaker_id=2)
    assert not state.monolingual
    assert state.consecutive_target == 0
    assert state.is_speaker_foreign(2)


def test_conversation_language_gate_preserves_state_on_unknown_detection(monkeypatch):
    monkeypatch.setattr(
        'utils.translation_cache.detect_language_with_confidence',
        lambda *_args, **_kwargs: (None, 0.0),
    )
    state = ConversationLanguageState('en')
    state.monolingual = True
    state.consecutive_target = 4

    assert state.observe('uncertain')
    assert state.observe_detection('', 1.0)
    assert state.monolingual
    assert state.consecutive_target == 4


def test_conversation_language_probe_interval_is_deterministic(monkeypatch):
    state = ConversationLanguageState('en')
    state.monolingual = True
    state.last_probe_time = 100.0

    monkeypatch.setattr('utils.translation_cache.time.monotonic', lambda: 129.9)
    assert not state.should_probe()
    monkeypatch.setattr('utils.translation_cache.time.monotonic', lambda: 130.0)
    assert state.should_probe()
    assert state.last_probe_time == 130.0


def test_coordinator_consumes_typed_success_through_production_path():
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Bonjour.', 'en'))])
    service, _cache = build_service({TranslationProvider.google: provider})
    callbacks: list[tuple[str, str, str, str]] = []

    async def on_ready(segment_id: str, text: str, detected: str, conversation_id: str) -> None:
        callbacks.append((segment_id, text, detected, conversation_id))

    coordinator = TranslationCoordinator('fr', service, on_ready)
    state = coordinator._get_or_create_state('segment-1')
    version = coordinator._next_version()
    state.version = version
    coordinator._batch_buffer.append(('segment-1', 'Hello.', 'conversation-1', version))

    asyncio.run(coordinator._flush_batch())

    assert callbacks == [('segment-1', 'Bonjour.', 'en', 'conversation-1')]
    assert state.committed_text == 'Hello.'
    assert state.assembled_translation == 'Bonjour.'


def test_coordinator_keeps_failed_input_retryable():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[provider_error(TranslationProvider.google)],
    )
    service, _cache = build_service({TranslationProvider.google: provider})
    callbacks: list[tuple[str, str, str, str]] = []

    async def on_ready(segment_id: str, text: str, detected: str, conversation_id: str) -> None:
        callbacks.append((segment_id, text, detected, conversation_id))

    coordinator = TranslationCoordinator('fr', service, on_ready)
    state = coordinator._get_or_create_state('segment-1')
    version = coordinator._next_version()
    state.version = version
    coordinator._batch_buffer.append(('segment-1', 'Hello.', 'conversation-1', version))

    asyncio.run(coordinator._flush_batch())

    assert callbacks == []
    assert state.committed_text == ''
    assert state.assembled_translation is None


def test_coordinator_rejects_stale_work_before_calling_provider():
    provider = FakeProvider(TranslationProvider.google, responses=[])
    service, _cache = build_service({TranslationProvider.google: provider})

    async def on_ready(_segment_id: str, _text: str, _detected: str, _conversation_id: str) -> None:
        raise AssertionError('stale work must not notify')

    coordinator = TranslationCoordinator('fr', service, on_ready)
    state = coordinator._get_or_create_state('segment-1')
    state.version = 2
    coordinator._batch_buffer.append(('segment-1', 'Hello.', 'conversation-1', 1))

    asyncio.run(coordinator._flush_batch())

    assert provider.calls == []
    assert state.committed_text == ''


def test_coordinator_negative_caches_typed_noop_without_notifying():
    store = DictTranslationStore()
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hello.', 'en'))])
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)
    callbacks: list[tuple[str, str, str, str]] = []

    async def on_ready(segment_id: str, text: str, detected: str, conversation_id: str) -> None:
        callbacks.append((segment_id, text, detected, conversation_id))

    coordinator = TranslationCoordinator('en', service, on_ready)
    state = coordinator._get_or_create_state('segment-1')
    version = coordinator._next_version()
    state.version = version
    coordinator._batch_buffer.append(('segment-1', 'Hello.', 'conversation-1', version))

    asyncio.run(coordinator._flush_batch())

    assert callbacks == []
    assert state.committed_text == 'Hello.'
    assert (fingerprint_text('Hello.'), 'en') in store.negative


def test_coordinator_does_not_negative_cache_unchanged_foreign_text():
    store = DictTranslationStore()
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hola.', 'es'))])
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)
    callbacks: list[tuple[str, str, str, str]] = []

    async def on_ready(segment_id: str, text: str, detected: str, conversation_id: str) -> None:
        callbacks.append((segment_id, text, detected, conversation_id))

    coordinator = TranslationCoordinator('en', service, on_ready)
    coordinator.language_state.monolingual = True
    coordinator.language_state.consecutive_target = 4
    state = coordinator._get_or_create_state('segment-1')
    version = coordinator._next_version()
    state.version = version
    coordinator._batch_buffer.append(('segment-1', 'Hola.', 'conversation-1', version))

    asyncio.run(coordinator._flush_batch())

    assert callbacks == []
    assert state.committed_text == 'Hola.'
    assert store.negative == set()
    assert not coordinator.language_state.monolingual
    assert coordinator.language_state.consecutive_target == 0
