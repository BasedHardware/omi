"""Tests for utils.log_sanitizer — masks sensitive tokens while preserving searchability."""

import pytest

from utils.log_sanitizer import sanitize


class TestSanitizeShortStrings:
    """Strings shorter than 8 chars are left as-is."""

    def test_short_word(self):
        assert sanitize("hello") == "hello"

    def test_7_char_string(self):
        assert sanitize("abcdefg") == "abcdefg"

    def test_none(self):
        assert sanitize(None) == "None"

    def test_empty(self):
        assert sanitize("") == ""


class TestSanitizeMediumStrings:
    """Strings 8-12 chars with digits: first 3 + *** + last 3."""

    def test_8_char_with_digit(self):
        result = sanitize("abcdef1h")
        assert result == "abc***f1h"

    def test_12_char_with_digit(self):
        result = sanitize("abcdef1hijkl")
        assert result == "abc***jkl"

    def test_8_char_pure_alpha_not_masked(self):
        """Pure alphabetic strings are NOT masked (they're words, not tokens)."""
        assert sanitize("abcdefgh") == "abcdefgh"


class TestSanitizeLongStrings:
    """Strings 13+ chars with digits: first 4 + *** + last 4."""

    def test_13_char_with_digit(self):
        result = sanitize("abcdefgh1jklm")
        assert result == "abcd***jklm"

    def test_13_char_pure_alpha_not_masked(self):
        """Pure alphabetic strings are NOT masked."""
        assert sanitize("abcdefghijklm") == "abcdefghijklm"

    def test_jwt_like_token(self):
        token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitize(token)
        assert result.startswith("eyJh")
        assert result.endswith("VCJ9")
        assert "***" in result

    def test_base64_blob(self):
        blob = "dGhpcyBpcyBhIGxvbmcgYmFzZTY0IHN0cmluZw=="
        result = sanitize(blob)
        assert result.startswith("dGhp")
        assert "***" in result


class TestSanitizePreservesStructure:
    """JSON keys, punctuation, and short values stay intact."""

    def test_json_with_token(self):
        text = '{"access_token": "ya29xABCDEFGHIJKLMNOP1234567890"}'
        result = sanitize(text)
        assert '"access_token": "' in result  # key preserved (no digits)
        assert "***" in result  # token value is masked

    def test_error_message_with_token(self):
        text = "Apple token exchange failed: {\"error\":\"invalid_grant\",\"token\":\"abc123def456ghij\"}"
        result = sanitize(text)
        assert "Apple token exchange failed:" in result  # message preserved
        assert "invalid_grant" in result  # no digits, not masked
        assert "***" in result  # token is masked

    def test_ip_address_not_masked(self):
        """IPs have dots separating segments, so segments < 8 chars stay visible."""
        result = sanitize("connecting to 10.128.0.5:8080")
        assert "10.128.0.5" in result

    def test_uid_partially_masked(self):
        """UIDs contain digits, so they get masked."""
        result = sanitize("uid=abc123def456ghij")
        assert "uid=" in result
        assert "***" in result

    def test_status_code_preserved(self):
        result = sanitize("HTTP 403: some_long_error_message_here")
        assert "HTTP 403:" in result
        assert "some_long_error_message_here" in result  # pure alpha + underscores, not masked

    def test_pure_words_not_masked(self):
        """Regular English words and snake_case identifiers are not masked."""
        text = "access_token client_secret invalid_grant exchange"
        assert sanitize(text) == text


class TestSanitizeTruncation:
    """Very long strings are truncated to prevent log bloat."""

    def test_long_string_truncated(self):
        # Use digits so the truncation marker isn't confused by masking
        long_text = "x" * 3000
        result = sanitize(long_text)
        assert len(result) < 3000
        # Pure alpha, so not masked — truncation marker should be intact
        assert "...[truncated]" in result

    def test_under_limit_not_truncated(self):
        text = "a" * 1999
        result = sanitize(text)
        assert "...[truncated]" not in result


class TestSanitizeNonStringInput:
    """sanitize() accepts any type and converts to str."""

    def test_dict_input(self):
        data = {"client_id": "abc123", "client_secret": "superSecret1ValueHere1234"}
        result = sanitize(data)
        assert "client_id" in result  # key preserved (no digits in key)
        assert "client_secret" in result  # key preserved
        assert "***" in result  # value with digits is masked

    def test_int_input(self):
        assert sanitize(42) == "42"

    def test_list_input(self):
        result = sanitize([True, False, True])
        assert "True" in result


class TestSanitizeEmails:
    """Email addresses get local part masked, domain preserved."""

    def test_simple_email(self):
        result = sanitize("john@example.com")
        assert "example.com" in result
        assert "john" not in result
        assert "***" in result

    def test_email_in_log_message(self):
        result = sanitize("Found contact: John Doe -> john.doe@gmail.com")
        assert "gmail.com" in result
        assert "john.doe" not in result

    def test_short_local_part(self):
        result = sanitize("ab@example.com")
        assert "***@example.com" == result

    def test_email_with_digits(self):
        result = sanitize("user123@company.org")
        assert "company.org" in result
        assert "***" in result

    def test_multiple_emails(self):
        result = sanitize("from alice@a.com to bob@b.com")
        assert "a.com" in result
        assert "b.com" in result
        assert "alice" not in result
        assert "bob" not in result


class TestSanitizeKeyValuePreserved:
    """key=value style text should not be falsely masked."""

    def test_simple_key_value(self):
        """key=value where value is a regular word should be preserved."""
        result = sanitize("attendee=charlie")
        assert "attendee" in result
        assert "charlie" in result

    def test_key_value_with_token(self):
        """key=value where value looks like a token should be masked."""
        result = sanitize("token=abc123def456ghij")
        assert "token=" in result
        assert "***" in result
