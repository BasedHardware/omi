"""Shared single-attempt policy for bounded Firestore reads.

The Firestore query and aggregation stream hooks call
``retry._predicate(exc)`` on every mid-stream error, so ``retry=None`` (the
usual way to disable gapic retries) crashes there with
``AttributeError`` and masks the real failure. ``FIRESTORE_NO_RETRY`` is a
``Retry`` object whose predicate rejects every error: one attempt inside
the caller's deadline, then the original error propagates.
"""

from google.api_core import retry

FIRESTORE_NO_RETRY = retry.Retry(predicate=lambda _exc: False)
