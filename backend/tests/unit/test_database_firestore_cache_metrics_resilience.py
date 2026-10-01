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
    """Verify _sanitize_namespace normalizes allowlisted namespaces and maps unknown to 'unknown'."""
    assert _sanitize_namespace(" User_Language ") == "user_language"
    assert _sanitize_namespace("live_stt_language_sessions") == "live_stt_language_sessions"
    assert _sanitize_namespace("unrecognized_namespace_123") == "unknown"
    with pytest.raises(ValueError, match="namespace must be a non-empty string"):
        _sanitize_namespace("")
    with pytest.raises(ValueError, match="namespace must be a non-empty string"):
        _sanitize_namespace("   ")
    with pytest.raises(ValueError, match="namespace must be a non-empty string"):
        _sanitize_namespace(None)  # type: ignore[arg-type]


def test_record_request_gracefully_handles_malformed():
    """Verify record_request falls back to unknown on unlisted result/namespace and does not crash on bad inputs."""
    # Invalid namespace or result doesn't raise exception to avoid breaking production callers
    record_request(None, "hit")  # type: ignore[arg-type]
    record_request("", "hit")
    record_request("user_language", None)  # type: ignore[arg-type]

    # Valid call increments Counter
    record_request("user_language", "hit")
    val = FIRESTORE_CACHE_REQUESTS.labels(namespace="user_language", result="hit")._value.get()
    assert val >= 1

    # Unrecognized label is mapped to unknown to bound cardinality
    record_request("user_language", "unrecognized_attack_payload")
    unknown_val = FIRESTORE_CACHE_REQUESTS.labels(namespace="user_language", result="unknown")._value.get()
    assert unknown_val >= 1

    # Unrecognized namespace is mapped to unknown to bound cardinality
    record_request("unrecognized_namespace_999", "hit")
    ns_unknown_val = FIRESTORE_CACHE_REQUESTS.labels(namespace="unknown", result="hit")._value.get()
    assert ns_unknown_val >= 1


def _get_metric_values(hist):
    count = 0.0
    for s in hist._samples():
        if s.name == "_count":
            count = s.value
            break
    return hist._sum.get(), count


def test_observe_fetch_handles_malformed_and_nan():
    """Verify observe_fetch swallows negative, NaN, Inf, overflow, and non-numeric seconds gracefully."""
    hist = FIRESTORE_CACHE_FETCH_SECONDS.labels(namespace="user_language")
    sum_before, count_before = _get_metric_values(hist)

    # None of these invalid inputs should increment count or sum
    observe_fetch("user_language", -1.0)
    observe_fetch("user_language", float("nan"))
    observe_fetch("user_language", float("inf"))
    observe_fetch("user_language", "not-a-number")  # type: ignore[arg-type]
    observe_fetch("user_language", True)  # type: ignore[arg-type]
    observe_fetch("user_language", 10**400)  # OverflowError

    sum_after_invalid, count_after_invalid = _get_metric_values(hist)
    assert sum_after_invalid == sum_before
    assert count_after_invalid == count_before

    # Valid observation must increment count and sum
    observe_fetch("user_language", 0.05)
    sum_final, count_final = _get_metric_values(hist)
    assert count_final == count_before + 1
    assert sum_final == pytest.approx(sum_before + 0.05)


def test_observe_payload_handles_malformed():
    """Verify observe_payload swallows negative, float, and non-numeric payload_bytes gracefully."""
    hist = FIRESTORE_CACHE_PAYLOAD_BYTES.labels(namespace="user_language")
    sum_before, count_before = _get_metric_values(hist)

    # None of these invalid inputs should increment count or sum
    observe_payload("user_language", -100)
    observe_payload("user_language", 10.5)  # type: ignore[arg-type]
    observe_payload("user_language", True)  # type: ignore[arg-type]
    observe_payload("user_language", "100")  # type: ignore[arg-type]

    sum_after_invalid, count_after_invalid = _get_metric_values(hist)
    assert sum_after_invalid == sum_before
    assert count_after_invalid == count_before

    # Valid observation must increment count and sum
    observe_payload("user_language", 1024)
    sum_final, count_final = _get_metric_values(hist)
    assert count_final == count_before + 1
    assert sum_final == sum_before + 1024
