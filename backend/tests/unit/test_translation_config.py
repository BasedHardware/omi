from __future__ import annotations

import pytest
from config.translation import _positive_float, resolve_translation_profile


@pytest.mark.parametrize('raw', ['nan', 'inf', '+inf', '-inf', 'NaN'])
def test_positive_float_rejects_non_finite_values(raw: str) -> None:
    with pytest.raises(ValueError, match='finite'):
        _positive_float(raw, 'TRANSLATION_NLLB_TIMEOUT_SECONDS')


@pytest.mark.parametrize('raw', ['0', '-1', 'not-a-number'])
def test_positive_float_rejects_non_positive_or_invalid_values(raw: str) -> None:
    with pytest.raises(ValueError):
        _positive_float(raw, 'TRANSLATION_NLLB_TIMEOUT_SECONDS')


def test_translation_profile_preserves_finite_timeout() -> None:
    profile = resolve_translation_profile({'TRANSLATION_NLLB_TIMEOUT_SECONDS': '2.5'})
    assert profile.nllb_timeout_seconds == 2.5
