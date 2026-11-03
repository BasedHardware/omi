"""Regression tests for ``database.wrapped`` path construction (issue #19958).

``_wrapped_doc_ref`` builds ``users/{uid}/wrapped/{year}``. Before the guard an
empty uid produced ``users//wrapped/2025`` — a collection path, not a document —
and an arbitrary year made a malformed doc id. These tests lock in the
validation at the single construction site every wrapped operation shares.
"""

from unittest.mock import MagicMock

import pytest

from database import wrapped


def _ref(*args, **kwargs):
    return wrapped._wrapped_doc_ref(*args, **kwargs)


def _db(monkeypatch):
    """Point the module-level Firestore client at a recording fake."""
    client = MagicMock()
    monkeypatch.setattr(wrapped, 'db', client)
    return client


class TestWrappedDocRefValidation:
    def test_valid_inputs_return_a_document_reference(self, monkeypatch):
        client = _db(monkeypatch)
        wrapped._wrapped_doc_ref('uid-1', 2025)
        client.collection.assert_called_once_with('users')

    @pytest.mark.parametrize(
        'bad_uid',
        ['', '   ', None, 123, 'a/b', 'a\\b', '../other', 'a..b', 'a\x00b', 'a\nb', 'x' * 200],
    )
    def test_rejects_bad_uid(self, monkeypatch, bad_uid):
        _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped._wrapped_doc_ref(bad_uid, 2025)

    @pytest.mark.parametrize('bad_year', [1999, 2101, 0, '2025', 2025.5, True])
    def test_rejects_bad_year(self, monkeypatch, bad_year):
        _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped._wrapped_doc_ref('uid-1', bad_year)

    def test_bool_year_rejected_even_though_bool_is_int(self, monkeypatch):
        _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped._wrapped_doc_ref('uid-1', True)

    @pytest.mark.parametrize('year', [2000, 2025, 2100])
    def test_boundary_years_accepted(self, monkeypatch, year):
        _db(monkeypatch)
        wrapped._wrapped_doc_ref('uid-1', year)


class TestWrappedOperationsUseTheGuard:
    """Every public read/write reaches _wrapped_doc_ref, so a bad uid or year is
    rejected by the shared validator before it can form a Firestore path."""

    def test_get_wrapped_rejects_empty_uid(self, monkeypatch):
        client = _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped.get_wrapped('', 2025)
        client.collection.assert_not_called()

    def test_get_wrapped_rejects_bad_year(self, monkeypatch):
        client = _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped.get_wrapped('uid-1', 1900)
        client.collection.assert_not_called()

    def test_create_wrapped_rejects_bad_uid(self, monkeypatch):
        client = _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped.create_wrapped(None, 2025)
        client.collection.assert_not_called()

    def test_update_wrapped_status_rejects_bad_year(self, monkeypatch):
        client = _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped.update_wrapped_status('uid-1', True, wrapped.WrappedStatus.DONE)
        client.collection.assert_not_called()

    def test_update_wrapped_progress_rejects_bad_uid(self, monkeypatch):
        client = _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped.update_wrapped_progress(' ', 2025, {})
        client.collection.assert_not_called()

    def test_reset_wrapped_for_regeneration_rejects_bad_year(self, monkeypatch):
        client = _db(monkeypatch)
        with pytest.raises(ValueError):
            wrapped.reset_wrapped_for_regeneration('uid-1', 9999)
        client.collection.assert_not_called()
