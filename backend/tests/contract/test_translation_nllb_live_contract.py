"""Live contract test: translation through the real backend path against NLLB (WP5, ADR-0035).

Exercises the backend's own translation client — TranslationService.translate_text,
which resolves the provider chain from HOSTED_TRANSLATION_API_URL +
TRANSLATION_SERVICE_MODELS and POSTs to the NLLB server's /v1/translate — against a
running NLLB (CTranslate2) instance. Proves the on-prem translation wiring end to end.

Gated on HOSTED_TRANSLATION_API_URL (skips in CI). Reaches the server on loopback
under --network host. Run:

  docker run --rm --network host \
    -e HOSTED_TRANSLATION_API_URL=http://127.0.0.1:8080 -e TRANSLATION_SERVICE_MODELS=nllb \
    -v /work/omi/src/omi:/repo -w /repo/backend omi-onprem-backend-test:v2 \
    python -m pytest tests/contract/test_translation_nllb_live_contract.py -q -p no:cacheprovider
"""

import os

import pytest

from utils.translation import TranslationService

pytestmark = pytest.mark.skipif(
    not os.getenv('HOSTED_TRANSLATION_API_URL', '').strip(),
    reason='HOSTED_TRANSLATION_API_URL not set — live NLLB server required',
)


@pytest.fixture
def service():
    return TranslationService()


@pytest.mark.parametrize(
    'text,source,target,expect_substr',
    [
        ('Good morning, how are you today?', 'en', 'it', 'buongiorno'),
        ('I would like a coffee, please.', 'en', 'fr', 'café'),
        ('The weather is beautiful this afternoon.', 'en', 'es', 'tiempo'),
    ],
)
def test_translate_text_through_backend_path(service, text, source, target, expect_substr):
    translated, detected = service.translate_text(target, text, source)
    assert isinstance(translated, str) and translated.strip()
    assert translated.strip().lower() != text.strip().lower(), 'expected a real translation, not the input'
    assert expect_substr in translated.lower(), f'{translated!r} missing expected token {expect_substr!r}'


def test_roundtrip_preserves_meaning(service):
    # en -> it -> en should return to (approximately) the original meaning.
    it, _ = service.translate_text('it', 'The cat is sleeping on the sofa.', 'en')
    back, _ = service.translate_text('en', it, 'it')
    low = back.lower()
    assert 'cat' in low and ('sleep' in low or 'asleep' in low)
