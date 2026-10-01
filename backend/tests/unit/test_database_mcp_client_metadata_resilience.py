"""Unit tests verifying defensive resilience and validation in mcp_client_metadata."""

from __future__ import annotations

import pytest

from database.mcp_client_metadata import (
    CIMD_CACHE_TTL_MAX_SECONDS,
    _BoundedPool,
    _cache_key,
    _cache_ttl_seconds,
    _header_content_length,
    _neg_cache_key,
    _parse_metadata_response,
    _validated_metadata,
    get_url_client,
    parse_metadata_url,
    sanitize_client_name,
)


def test_bounded_pool_rejects_invalid_dimensions():
    """Verify _BoundedPool validates worker count and queue size."""
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        _BoundedPool(0, 10)
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        _BoundedPool(-1, 10)
    with pytest.raises(ValueError, match="workers must be a positive integer"):
        _BoundedPool("4", 10)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="queue must be a non-negative integer"):
        _BoundedPool(4, -1)


def test_parse_metadata_url_rejects_invalid_types_and_empty():
    """Verify parse_metadata_url rejects non-string, empty, and whitespace strings."""
    assert parse_metadata_url(None) is None  # type: ignore[arg-type]
    assert parse_metadata_url("") is None
    assert parse_metadata_url("   ") is None
    assert parse_metadata_url(12345) is None  # type: ignore[arg-type]


def test_parse_metadata_url_rejects_unsafe_components():
    """Verify parse_metadata_url rejects query params, fragments, backslashes, and non-HTTPS."""
    assert parse_metadata_url("http://example.com/oauth") is None
    assert parse_metadata_url("https://example.com/oauth?cache=bust") is None
    assert parse_metadata_url("https://example.com/oauth#frag") is None
    assert parse_metadata_url("https://example.com\\path") is None
    assert parse_metadata_url("https://user:pass@example.com/oauth") is None


def test_parse_metadata_url_accepts_valid_https():
    """Verify parse_metadata_url returns ascii host and target path on valid URLs."""
    result = parse_metadata_url("https://auth.example.com/.well-known/oauth-client")
    assert result == ("auth.example.com", "/.well-known/oauth-client")


def test_cache_keys_validate_inputs():
    """Verify _cache_key and _neg_cache_key fail fast on invalid identifiers."""
    with pytest.raises(ValueError, match="client_id must be a non-empty string"):
        _cache_key("")
    with pytest.raises(ValueError, match="client_id must be a non-empty string"):
        _cache_key("   ")
    with pytest.raises(ValueError, match="client_id must be a non-empty string"):
        _cache_key(None)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="canonical_url must be a non-empty string"):
        _neg_cache_key("")
    with pytest.raises(ValueError, match="canonical_url must be a non-empty string"):
        _neg_cache_key("   ")

    assert _cache_key("https://client.com").startswith("mcp:cimd:")
    assert _neg_cache_key("https://client.com").startswith("mcp:cimd:neg:")


def test_cache_ttl_seconds_normalizes_and_bounds():
    """Verify _cache_ttl_seconds parses max-age and honors restrictions."""
    assert _cache_ttl_seconds(None) == CIMD_CACHE_TTL_MAX_SECONDS
    assert _cache_ttl_seconds(1234) == 0  # type: ignore[arg-type]
    assert _cache_ttl_seconds("no-store") == 0
    assert _cache_ttl_seconds("no-cache") == 0
    assert _cache_ttl_seconds("private, max-age=600") == 0
    assert _cache_ttl_seconds("max-age=300") == 300
    assert _cache_ttl_seconds("max-age=999999") == CIMD_CACHE_TTL_MAX_SECONDS
    assert _cache_ttl_seconds("max-age=invalid") == 0
    assert _cache_ttl_seconds("max-age=-50") == 0


def test_header_content_length():
    """Verify _header_content_length parses Content-Length safely."""
    assert _header_content_length(None) is None  # type: ignore[arg-type]
    assert _header_content_length(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n") is None
    assert _header_content_length(b"HTTP/1.1 200 OK\r\nContent-Length: 1024\r\n") == 1024
    assert _header_content_length(b"HTTP/1.1 200 OK\r\nContent-Length: bad\r\n") is None


def test_parse_metadata_response_rejects_invalid_inputs():
    """Verify _parse_metadata_response handles non-bytes or malformed bytes cleanly."""
    assert _parse_metadata_response(None) is None  # type: ignore[arg-type]
    assert _parse_metadata_response(b"") is None
    assert _parse_metadata_response(b"invalid http response") is None


def test_validated_metadata_rejects_malformed_documents():
    """Verify _validated_metadata rejects invalid payloads and enforces security whitelist."""
    assert _validated_metadata(None, "https://client.com") is None  # type: ignore[arg-type]
    assert _validated_metadata({}, "") is None

    # ID mismatch
    assert _validated_metadata({"client_id": "https://other.com"}, "https://client.com") is None

    # Missing redirect_uris
    doc = {"client_id": "https://client.com", "redirect_uris": []}
    assert _validated_metadata(doc, "https://client.com") is None

    # Invalid secret included
    doc_with_secret = {
        "client_id": "https://client.com",
        "redirect_uris": ["https://client.com/callback"],
        "client_secret": "compromised",
    }
    assert _validated_metadata(doc_with_secret, "https://client.com") is None


def test_sanitize_client_name_normalizes_and_bounds():
    """Verify sanitize_client_name cleans control chars and bounds length."""
    assert sanitize_client_name(None) == ""
    assert sanitize_client_name(123) == ""
    assert sanitize_client_name("  Test \x00 App  ") == "Test  App"
    oversized = "A" * 100
    assert len(sanitize_client_name(oversized)) == 64


def test_get_url_client_rejects_invalid_inputs():
    """Verify get_url_client fails fast with None on invalid client IDs."""
    assert get_url_client(None) is None  # type: ignore[arg-type]
    assert get_url_client("") is None
    assert get_url_client("   ") is None
    assert get_url_client("http://insecure.com") is None
    assert get_url_client("https://example.com?query=not_allowed") is None
