"""TtsSynthesizeRequest must bound the text length at the schema boundary.

The TTS proxy enforces a 5000-character limit at runtime (_TTS_REQUEST_CHAR_LIMIT), but the
shared request model only required min_length=1, so the schema/contract the mobile and desktop
clients rely on did not express the upper bound and an oversized payload was fully parsed before
the runtime check. Bounding text with max_length=5000 rejects it at request validation (422).

Test isolation: models.tts is pure pydantic and imports cleanly, so the test exercises the
model's validation directly (no router, no monkeypatch).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from models.tts import TtsSynthesizeRequest  # noqa: E402


def test_accepts_text_at_the_limit():
    req = TtsSynthesizeRequest(text='x' * 5000)
    assert len(req.text) == 5000


def test_rejects_empty_text():
    with pytest.raises(ValidationError):
        TtsSynthesizeRequest(text='')


def test_rejects_text_over_the_limit():
    with pytest.raises(ValidationError):
        TtsSynthesizeRequest(text='x' * 5001)
