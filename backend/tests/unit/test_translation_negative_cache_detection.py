"""Regression: a negative-cached segment must not vote in the unit's detected language.

TranslationEngine reconstructs a unit's detected_language by taking the most common
non-empty detection across its segments. A negative-cache hit means "this segment needs no
translation", which is not a language detection, so before the translation_core split it was
stored as '' and skipped by the tally (`if det_lang:`). The split started storing the target
language for segment-level negative hits, so a unit that mixes already-seen target-language
text with foreign speech now reports the target language. TranslationCoordinator feeds that
value to ConversationLanguageState.observe_detection, which pushes the conversation into
monolingual mode and stops translating that speaker's foreign speech.

The whole-unit negative hit keeps using the target language: there the no-op really does
describe the entire unit. Only the per-segment hit is wrong.

Seam: TranslationEngine takes its cache, provider chain and profile resolver by constructor
injection, so this drives the real engine with fakes and needs no monkeypatching.
"""

from config.translation import TranslationProfile
from utils.translation_core.engine import TranslationEngine
from utils.translation_core.planner import TranslationMode, TranslationUnit, build_translation_plan
from utils.translation_core.providers import ProviderBatch, ProviderTranslation, TranslationProvider

_PROFILE = TranslationProfile(
    providers=(TranslationProvider.google,),
    nllb_url='',
    nllb_timeout_seconds=1.0,
    google_project_id='test-project',
    cache_ttl_seconds=60,
    negative_cache_ttl_seconds=60,
)

_TARGET_TEXT = 'Hello there my friend.'
_FOREIGN_TEXT = 'Como estas amigo mio?'


class _FakeCache:
    """Only the listed fingerprints are negative-cached; nothing is positively cached."""

    def __init__(self, negative_fingerprints: set[str]) -> None:
        self._negative = negative_fingerprints

    def get(self, fingerprint: str, target_language: str):
        return None

    def is_negative(self, fingerprint: str, target_language: str) -> bool:
        return fingerprint in self._negative

    def put(self, fingerprint: str, target_language: str, value: object, profile: object) -> None:
        return None


class _FakeProviders:
    """Detects the foreign language for whatever the engine actually sends for translation."""

    def __init__(self, detected_language: str) -> None:
        self._detected_language = detected_language
        self.requested: list[list[str]] = []

    def translate(self, contents, target_language, source_language, profile, mode):
        self.requested.append(list(contents))
        return ProviderBatch(
            provider=TranslationProvider.google,
            translations=tuple(
                ProviderTranslation(text=f'translated:{content}', detected_language=self._detected_language)
                for content in contents
            ),
        )


def _fingerprint_of(unit: TranslationUnit, text: str) -> str:
    """Ask the planner itself which fingerprint it assigns to that sentence."""
    plan = build_translation_plan([unit], TranslationMode.sentence)
    return next(segment.fingerprint for segment in plan.unique_segments if segment.text == text)


def test_negative_cached_segment_does_not_vote_for_target_language():
    unit = TranslationUnit(ordinal=0, unit_id='unit-1', text=f'{_TARGET_TEXT} {_FOREIGN_TEXT}')
    cache = _FakeCache({_fingerprint_of(unit, _TARGET_TEXT)})
    providers = _FakeProviders(detected_language='es')
    engine = TranslationEngine(cache, providers, lambda: _PROFILE)

    outcome = engine.translate([unit], target_language='en', mode=TranslationMode.sentence)[0]

    # Only the foreign sentence was actually detected, so it is the unit's language.
    assert outcome.detected_language == 'es'
    # The negative-cached sentence is still returned untranslated alongside the translated one.
    assert _TARGET_TEXT in outcome.text
    assert providers.requested == [[_FOREIGN_TEXT]]


def test_negative_cached_segments_do_not_outvote_the_only_detection():
    # Two negative-cached target-language sentences would outvote the single foreign detection
    # 2-to-1 if they were allowed to vote at all.
    unit = TranslationUnit(
        ordinal=0,
        unit_id='unit-2',
        text=f'{_TARGET_TEXT} Good to see you again. {_FOREIGN_TEXT}',
    )
    cache = _FakeCache(
        {
            _fingerprint_of(unit, _TARGET_TEXT),
            _fingerprint_of(unit, 'Good to see you again.'),
        }
    )
    engine = TranslationEngine(cache, _FakeProviders(detected_language='es'), lambda: _PROFILE)

    outcome = engine.translate([unit], target_language='en', mode=TranslationMode.sentence)[0]

    assert outcome.detected_language == 'es'
