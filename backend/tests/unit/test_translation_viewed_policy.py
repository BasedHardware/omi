from config.translation import TranslationProvider, resolve_ondemand_config, viewed_translation_profile
from tests.unit.translation_test_support import DictTranslationStore, FakeProvider, build_service, profile, translations
from utils.translation_core.cache import CachedTranslation, viewed_cache_fingerprint
from utils.translation_core.planner import TranslationMode, fingerprint_text


def test_viewed_uses_gemini_only_and_does_not_read_legacy_positive_or_negative():
    source = 'Yến nói với bác về năm 2025.'
    store = DictTranslationStore()
    legacy_key = fingerprint_text(source)
    store.values[(legacy_key, 'en')] = CachedTranslation('Incorrect NLLB', 'vi')
    store.negative.add((legacy_key, 'en'))
    gemini = FakeProvider(TranslationProvider.gemini, [translations(('Yến spoke with the elder about 2025.', 'vi'))])
    nllb = FakeProvider(TranslationProvider.nllb, [])
    service, _ = build_service({TranslationProvider.gemini: gemini, TranslationProvider.nllb: nllb}, store=store)
    viewed = viewed_translation_profile(
        profile((TranslationProvider.nllb, TranslationProvider.gemini)), resolve_ondemand_config({})
    )
    result = service.translate_outcomes('en', [('s1', source)], mode=TranslationMode.whole_text, profile=viewed)
    assert result[0].text == 'Yến spoke with the elder about 2025.'
    assert len(gemini.calls) == 1 and not nllb.calls
    assert (viewed_cache_fingerprint(legacy_key, '', 'en', 'whole_text', 'viewed_v1'), 'en') in store.values


def test_viewed_cache_identity_includes_hint_target_mode_and_version():
    source = fingerprint_text('bác là năm')
    baseline = viewed_cache_fingerprint(source, '', 'en', 'whole_text', 'viewed_v1')
    assert (
        len(
            {
                baseline,
                viewed_cache_fingerprint(source, 'vi', 'en', 'whole_text', 'viewed_v1'),
                viewed_cache_fingerprint(source, '', 'fr', 'whole_text', 'viewed_v1'),
                viewed_cache_fingerprint(source, '', 'en', 'sentence', 'viewed_v1'),
                viewed_cache_fingerprint(source, '', 'en', 'whole_text', 'viewed_v2'),
            }
        )
        == 5
    )
