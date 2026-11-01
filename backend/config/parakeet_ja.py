"""Japanese on the live Parakeet window, served by a separate ja model deployment.

The window path posts to the European/English `parakeet-tdt-0.6b-v3` pool, which
cannot transcribe Japanese. Japanese sessions instead post to their own
`parakeet-tdt_ctc-0.6b-ja` endpoint, gated by an owner-hash percent:

- `HOSTED_PARAKEET_JA_API_URL` unset or empty: Japanese stays on its vendors (kill switch).
- `PARAKEET_JA_WINDOW_PERCENT` (default 0; invalid reads as 0): share of owners
  whose Japanese sessions may take the window. Ramp 5 -> 25 -> 100.

Everything else about the window (admission, cost-routing stage and bench, fallback
to Soniox/Modulate) is unchanged; cost and health keys already carry the language.
"""

from __future__ import annotations

import math
import os

JA_WINDOW_MODEL = 'nvidia/parakeet-tdt_ctc-0.6b-ja'
JA_URL_ENV = 'HOSTED_PARAKEET_JA_API_URL'
JA_PERCENT_ENV = 'PARAKEET_JA_WINDOW_PERCENT'
JA_COHORT_SALT = 'parakeet-window-ja'


def ja_window_url() -> str:
    return os.getenv(JA_URL_ENV, '').strip().rstrip('/')


def ja_window_percent() -> float:
    try:
        value = float(os.getenv(JA_PERCENT_ENV, '0'))
    except ValueError:
        return 0.0
    return min(100.0, max(0.0, value)) if math.isfinite(value) else 0.0


def ja_window_configured() -> bool:
    """Whether any owner can take the ja window: endpoint set and a nonzero ramp."""
    return bool(ja_window_url()) and ja_window_percent() > 0


def ja_window_allocated(uid: str | None) -> bool:
    if not uid or not ja_window_configured():
        return False
    from config.policy.batch import cohort_bucket

    return cohort_bucket(uid, JA_COHORT_SALT, bits=64) < ja_window_percent()


def window_endpoint(language: str) -> str:
    """Base URL the window posts to for a normalized language; empty means none."""
    if language == 'ja':
        return ja_window_url()
    # Unchanged value: replica routing compares it to the family URL verbatim.
    return os.getenv('HOSTED_PARAKEET_API_URL', '')
