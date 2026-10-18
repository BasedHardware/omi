"""Unit tests for backend/database/app_review_config.py — #21892.

Covers platform normalization, UID sanitization, plausible-version
gating (no (0,0,0) collisions), and resilient Firestore fetch.
"""

import pytest
from google.api_core.exceptions import ServiceUnavailable

import database.app_review_config as arc


class FakeDoc:
    def __init__(self, exists=True, data=None):
        self._exists = exists
        self._data = data

    @property
    def exists(self):
        return self._exists

    def to_dict(self):
        return self._data


class FakeDocumentRef:
    def __init__(self, doc):
        self._doc = doc

    def get(self):
        return self._doc


class FakeCollection:
    def __init__(self, doc):
        self._doc = doc

    def document(self, name):
        return FakeDocumentRef(self._doc)


class FakeClient:
    def __init__(self, doc=None, error=None):
        self._doc = doc or FakeDoc(False)
        self._error = error

    def collection(self, name):
        if self._error:
            raise self._error
        return FakeCollection(self._doc)


def hide(uid, platform, version, cfg=None):
    client = FakeClient(FakeDoc(True, cfg)) if cfg is not None else FakeClient()
    return arc.should_hide_subscription_ui(uid, platform, version, firestore_client=client)


# --- platform normalization ---


def test_platform_whitespace_and_case_normalized():
    cfg = {'reviewer_uids': ['rev-1']}
    for platform in (' ios', 'ios ', ' iOS ', 'IOS', ' macos ', 'MacOS'):
        assert hide('rev-1', platform, None, cfg) is True


def test_unsupported_platform_returns_false():
    cfg = {'reviewer_uids': ['rev-1']}
    assert hide('rev-1', 'android', None, cfg) is False
    assert hide('rev-1', None, None, cfg) is False
    assert hide('rev-1', '', None, cfg) is False


# --- uid sanitization ---


def test_uid_whitespace_matches_stripped_reviewer():
    cfg = {'reviewer_uids': ['rev-1']}
    assert hide(' rev-1 ', 'ios', None, cfg) is True


def test_reviewer_uid_with_whitespace_in_config_matches():
    cfg = {'reviewer_uids': [' rev-1 ', 'other']}
    assert hide('rev-1', 'ios', None, cfg) is True


def test_non_reviewer_uid_not_hidden():
    cfg = {'reviewer_uids': ['rev-1']}
    assert hide('normal-user', 'ios', None, cfg) is False


def test_non_string_reviewer_entries_ignored():
    cfg = {'reviewer_uids': [None, 42, 'rev-1']}
    assert hide('rev-1', 'ios', None, cfg) is True


# --- version gating ---


def test_exact_semantic_version_match_hides():
    cfg = {'hidden_versions': ['1.0.531']}
    assert hide('user', 'ios', '1.0.531', cfg) is True


def test_semantic_matches_any_build():
    cfg = {'hidden_versions': ['1.0.531']}
    assert hide('user', 'ios', '1.0.531+607', cfg) is True


def test_different_version_not_hidden():
    cfg = {'hidden_versions': ['1.0.531']}
    assert hide('user', 'ios', '2.0.0', cfg) is False


def test_malformed_versions_do_not_collide():
    cfg = {'hidden_versions': ['malformed..version']}
    # a different malformed string must NOT match the zero-fallback collision
    assert hide('user', 'ios', 'other..malformed', cfg) is False
    assert hide('user', 'ios', 'not.a.version', cfg) is False


def test_exact_malformed_string_still_matches():
    cfg = {'hidden_versions': ['malformed..version']}
    assert hide('user', 'ios', 'malformed..version', cfg) is True


def test_empty_version_entry_ignored():
    cfg = {'hidden_versions': ['', '   ']}
    assert hide('user', 'ios', '1.0.531', cfg) is False
    assert hide('user', 'ios', '', cfg) is False


# --- firestore boundary ---


def test_fetch_error_returns_empty_and_hides_nothing():
    assert hide('rev-1', 'ios', None, cfg=None) is False
    client = FakeClient(error=ServiceUnavailable('firestore down'))
    assert arc.should_hide_subscription_ui('rev-1', 'ios', None, firestore_client=client) is False


def test_missing_document_returns_empty():
    client = FakeClient(FakeDoc(False))
    assert arc._fetch_review_config('ios', client) == {}


def test_non_dict_document_returns_empty():
    client = FakeClient(FakeDoc(True, ['not-a-dict']))
    assert arc._fetch_review_config('ios', client) == {}


def test_programming_error_propagates_not_swallowed():
    """The narrowed fetch catch must not masquerade bugs as no-config."""
    client = FakeClient(error=AttributeError('misconfigured client'))
    with pytest.raises(AttributeError):
        arc._fetch_review_config('ios', client)
