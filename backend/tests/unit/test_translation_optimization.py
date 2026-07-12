from __future__ import annotations

import pytest

from config.translation import TranslationProvider
from tests.unit.translation_test_support import DictTranslationStore, FakeProvider, build_service, translations
from utils.translation import (
    TranslationNeed,
    TranslationService,
    TranslationStatus,
    classify_translation_need,
    detect_language_with_confidence,
    split_into_sentences,
)
from utils.translation_cache import should_persist_translation


def test_sentence_splitter_preserves_abbreviations_and_decimals():
    assert split_into_sentences('I live in the U.S. now. Version 3.11 works.') == [
        'I live in the U.S. now.',
        'Version 3.11 works.',
    ]
    assert split_into_sentences('Use fruits e.g. apples. It works.') == [
        'Use fruits e.g. apples.',
        'It works.',
    ]


def test_sentence_splitter_preserves_multilingual_enders():
    assert split_into_sentences('Hello. 你好。世界！') == ['Hello.', '你好。', '世界！']
    assert split_into_sentences('') == []


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('Hello, world', ['Hello, world']),
        ('Hello? Goodbye!', ['Hello?', 'Goodbye!']),
        ('First line\nSecond line', ['First line', 'Second line']),
        ('مرحبا؟ كيف حالك؟', ['مرحبا؟', 'كيف حالك؟']),
        ('नमस्ते। आप कैसे हैं?', ['नमस्ते।', 'आप कैसे हैं?']),
        ('The U.K. is rainy. Bring a coat.', ['The U.K. is rainy.', 'Bring a coat.']),
        ('The U.S.A. is large. Yes.', ['The U.S.A. is large.', 'Yes.']),
        ('F.B.I. agents arrived. They left.', ['F.B.I. agents arrived.', 'They left.']),
        ('Dr. Smith arrived. He was late.', ['Dr. Smith arrived.', 'He was late.']),
        ('Mrs. Smith arrived. She left.', ['Mrs. Smith arrived.', 'She left.']),
        ('We need apples, oranges, etc. for pie.', ['We need apples, oranges, etc. for pie.']),
        ('Red vs. Blue is better. We agree.', ['Red vs. Blue is better.', 'We agree.']),
        ('   ', []),
    ],
)
def test_sentence_splitter_behavioral_contract(text, expected):
    assert split_into_sentences(text) == expected


def test_confident_language_detection_handles_short_fillers_and_real_text():
    assert detect_language_with_confidence('hi', remove_non_lexical=False) == (None, 0.0)
    assert detect_language_with_confidence('um ah oh uh hmm', remove_non_lexical=True) == (None, 0.0)

    language, confidence = detect_language_with_confidence(
        'This is a sufficiently long English sentence for deterministic language detection.',
        remove_non_lexical=False,
    )
    assert language == 'en'
    assert confidence > 0.5


@pytest.mark.parametrize(
    ('detected', 'confidence', 'target', 'stable', 'expected'),
    [
        ('en', 0.90, 'en-US', False, TranslationNeed.SKIP),
        ('en', 0.89, 'en', True, TranslationNeed.DEFER),
        ('fr', 0.80, 'en', True, TranslationNeed.TRANSLATE),
        ('fr', 0.80, 'en', False, TranslationNeed.DEFER),
        ('fr', 0.79, 'en', True, TranslationNeed.DEFER),
        (None, 0.0, 'en', True, TranslationNeed.DEFER),
    ],
)
def test_translation_need_thresholds_are_explicit(monkeypatch, detected, confidence, target, stable, expected):
    monkeypatch.setattr(
        'utils.translation_language.detect_language_with_confidence',
        lambda *_args, **_kwargs: (detected, confidence),
    )

    assert classify_translation_need('long enough input', target, is_stable=stable) == expected


def test_whole_text_and_sentence_methods_delegate_to_one_engine():
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[
            translations(('Bonjour là-bas', 'en')),
            translations(('Bonjour.', 'en'), ('Comment ça va?', 'en')),
        ],
    )
    service, _cache = build_service({TranslationProvider.google: provider})

    assert service.translate_text('fr', 'Hello there') == ('Bonjour là-bas', 'en')
    assert service.translate_text_by_sentence('fr', 'Hello. How are you?') == ('Bonjour. Comment ça va?', 'en')

    assert provider.calls[0]['contents'] == ['Hello there']
    assert provider.calls[1]['contents'] == ['Hello.', 'How are you?']


def test_default_services_share_external_adapters_but_keep_session_lrus_separate():
    first = TranslationService()
    second = TranslationService()

    assert first.cache is not second.cache
    assert first.cache._persistent is second.cache._persistent
    assert first._engine._providers is second._engine._providers


def test_whitespace_only_input_skips_the_provider_in_every_mode():
    provider = FakeProvider(TranslationProvider.google, responses=[])
    service, _cache = build_service({TranslationProvider.google: provider})

    assert service.translate_text('fr', '   ') == ('   ', '')
    assert service.translate_text_by_sentence('fr', '   ') == ('   ', '')
    assert provider.calls == []


def test_full_text_cache_is_shared_by_sentence_mode():
    store = DictTranslationStore()
    provider = FakeProvider(
        TranslationProvider.google,
        responses=[translations(('Bonjour.', 'en'), ('Ça va?', 'en'))],
    )
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)

    first = service.translate_text_by_sentence('fr', 'Hello. How are you?')
    second = service.translate_text_by_sentence('fr', 'Hello. How are you?')

    assert first == ('Bonjour. Ça va?', 'en')
    assert second == first
    assert len(provider.calls) == 1


def test_memory_cache_survives_persistent_cache_miss():
    store = DictTranslationStore()
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hola', 'en'))])
    service, _cache = build_service({TranslationProvider.google: provider}, store=store)

    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    store.values.clear()
    assert service.translate_text('es', 'Hello') == ('Hola', 'en')
    assert len(provider.calls) == 1


def test_typed_unchanged_outcome_maps_to_legacy_tuple_only_at_facade():
    provider = FakeProvider(TranslationProvider.google, responses=[translations(('Hello', 'en'))])
    service, _cache = build_service({TranslationProvider.google: provider})

    outcomes = service.translate_outcomes('en', [('segment', 'Hello')])

    assert len(outcomes) == 1
    assert outcomes[0].status == TranslationStatus.unchanged
    assert service.translate_units_batch('en', []) == []


@pytest.mark.parametrize(
    ('source', 'translated', 'detected', 'target', 'expected'),
    [
        ('Hello', ' Hello ', 'en-US', 'en', False),
        ('Hello', 'HELLO', 'en', 'en', True),
        ('Hello', 'Bonjour', 'en', 'fr', True),
        ('hola', 'hello', 'es', 'en', True),
        ('hola', 'hola', 'es', 'en', False),
        ('123', '123', '', 'en', False),
        ('hi', 'hi', 'en', 'en-US', False),
        ('', '', '', 'en', False),
        ('one  two', 'one two', 'en', 'en', False),
    ],
)
def test_should_persist_translation_is_material_change_policy(source, translated, detected, target, expected):
    assert should_persist_translation(source, translated, detected, target) is expected
