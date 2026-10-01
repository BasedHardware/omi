"""Unit tests verifying defensive boundary guards in firestore_cache_metrics."""

import pytest

from database.firestore_cache_metrics import (
    FIRESTORE_CACHE_FETCH_SECONDS,
    FIRESTORE_CACHE_PAYLOAD_BYTES,
    FIRESTORE_CACHE_REQUESTS,
    _sanitize_namespace,
    observe_fetch,
    observe_payload,
    record_request,
)


def test_sanitize_namespace():
    """Verify _sanitize_namespace strips and lowercases valid names, rejects empty or non-string."""
    assert _sanitize_namespace(" User_Language ") == "user_language"
    with pytest.raises(ValueError, match="namespace must be a non-empty string"):
        _sanitize_namespace("")
    with pytest.raises(ValueError, match="namespace must be a non-empty string"):
        _sanitize_namespace("   ")
    with pytest.raises(ValueError, match="namespace must be a non-empty string"):
        _sanitize_namespace(None)  # type: ignore[arg-type]


def test_record_request_gracefully_handles_malformed():
    """Verify record_request falls back to unknown on unlisted result and does not crash on bad inputs."""
    # Invalid namespace or result doesn't raise exception to avoid breaking production callers
    record_request(None, "hit")  # type: ignore[arg-type]
    record_request("", "hit")
    record_request("user_language", None)  # type: ignore[arg-type]

    # Valid call increments Counter
    record_request("user_lang", "hit")
    val = FIRESTORE_CACHE_REQUESTS.labels(namespace="user_lang", result="hit")._value.get()
    assert val >= 1

    # Unrecognized label is mapped to unknown to bound cardinality
    record_request("user_lang", "unrecognized_attack_payload")
    unknown_val = FIRESTORE_CACHE_REQUESTS.labels(namespace="user_lang", result="unknown")._value.get()
    assert unknown_val >= 1


def test_observe_fetch_handles_malformed_and_nan():
    """Verify observe_fetch swallows negative, NaN, Inf, and non-numeric seconds gracefully."""
    observe_fetch("user_lang", -1.0)
    observe_fetch("user_lang", float("nan"))
    observe_fetch("user_lang", float("inf"))
    observe_fetch("user_lang", "not-a-number")  # type: ignore[arg-type]
    observe_fetch("user_lang", True)  # type: ignore[arg-type]

    # Valid observation
    observe_fetch("user_lang", 0.05)


def test_observe_payload_handles_malformed():
    """Verify observe_payload swallows negative, float, and non-numeric payload_bytes gracefully."""
    observe_payload("user_lang", -100)
    observe_payload("user_lang", 10.5)  # type: ignore[arg-type]
    observe_payload("user_lang", True)  # type: ignore[arg-type]
    observe_payload("user_lang", "100")  # type: ignore[arg-type]

    # Valid observation
    observe_payload("user_lang", 1024)
