"""Tests for database.apps resilience, ID validation, and merge writes."""

from unittest.mock import MagicMock

import pytest
from google.cloud.firestore import ArrayRemove, ArrayUnion
from google.cloud.firestore_v1 import _helpers

import database.apps as apps_db


def test_add_app_access_for_tester_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    apps_db.add_app_access_for_tester_db('app-123', 'user-456')

    fake_db.collection.assert_called_once_with('testers')
    fake_coll.document.assert_called_once_with('user-456')
    fake_doc.set.assert_called_once()
    args, kwargs = fake_doc.set.call_args
    assert kwargs.get('merge') is True
    assert 'apps' in args[0]
    assert type(args[0]['apps']).__name__ in ('ArrayUnion', 'MagicMock')


def test_remove_app_access_for_tester_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    apps_db.remove_app_access_for_tester_db('app-123', 'user-456')

    fake_db.collection.assert_called_once_with('testers')
    fake_coll.document.assert_called_once_with('user-456')
    fake_doc.set.assert_called_once()
    args, kwargs = fake_doc.set.call_args
    assert kwargs.get('merge') is True
    assert 'apps' in args[0]
    assert type(args[0]['apps']).__name__ in ('ArrayRemove', 'MagicMock')


def test_set_app_popular_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    apps_db.set_app_popular_db('app-123', True)

    fake_db.collection.assert_called_once_with('plugins_data')
    fake_coll.document.assert_called_once_with('app-123')
    fake_doc.set.assert_called_once_with({'is_popular': True}, merge=True)


def test_update_app_in_db_uses_update(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    payload = {'id': 'app-123', 'name': 'Updated App'}
    apps_db.update_app_in_db(payload)

    fake_coll.document.assert_called_once_with('app-123')
    fake_doc.update.assert_called_once_with(payload)


def test_update_app_in_db_preserves_dotted_field_path_update_mask(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    payload = {
        'id': 'app-123',
        'external_integration.chat_messages_enabled': True,
        'external_integration.chat_messages_target': 'main',
    }
    apps_db.update_app_in_db(payload)

    fake_doc.update.assert_called_once_with(payload)
    called_payload = fake_doc.update.call_args[0][0]

    # Verify Firestore's pbs_for_update generates nested field_paths in update_mask
    doc_path = 'projects/test-proj/databases/(default)/documents/plugins_data/app-123'
    [write] = _helpers.pbs_for_update(doc_path, called_payload, None)
    paths = set(write.update_mask.field_paths)
    assert 'external_integration.chat_messages_enabled' in paths
    assert 'external_integration.chat_messages_target' in paths
    assert 'id' in paths


def test_update_app_in_db_missing_id_raises_value_error(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(apps_db, 'db', fake_db)

    with pytest.raises(ValueError, match="app_data must include 'id'"):
        apps_db.update_app_in_db({'name': 'No ID'})


def test_upsert_app_to_db_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    payload = {'id': 'app-123', 'name': 'Upserted App'}
    apps_db.upsert_app_to_db(payload)

    fake_coll.document.assert_called_once_with('app-123')
    fake_doc.set.assert_called_once_with(payload, merge=True)


def test_upsert_app_to_db_missing_id_raises_value_error(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(apps_db, 'db', fake_db)

    with pytest.raises(ValueError, match="app_data must include 'id'"):
        apps_db.upsert_app_to_db({'name': 'No ID'})


def test_add_app_to_db_missing_id_raises_value_error(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(apps_db, 'db', fake_db)

    with pytest.raises(ValueError, match="app_data must include 'id'"):
        apps_db.add_app_to_db({'name': 'No ID'})


def test_update_persona_in_db_uses_set_merge(monkeypatch):
    fake_db = MagicMock()
    fake_coll = MagicMock()
    fake_doc = MagicMock()

    fake_db.collection.return_value = fake_coll
    fake_coll.document.return_value = fake_doc
    monkeypatch.setattr(apps_db, 'db', fake_db)

    payload = {'id': 'persona-123', 'name': 'Persona'}
    apps_db.update_persona_in_db(payload)

    fake_coll.document.assert_called_once_with('persona-123')
    fake_doc.set.assert_called_once_with(payload, merge=True)


def test_update_persona_in_db_missing_id_raises_value_error(monkeypatch):
    fake_db = MagicMock()
    monkeypatch.setattr(apps_db, 'db', fake_db)

    with pytest.raises(ValueError, match="persona_data must include 'id'"):
        apps_db.update_persona_in_db({'name': 'No ID'})
