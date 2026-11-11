"""Visibility changes preserve the app's document identity and subcollections.

The old republish path read a snapshot, deleted it and recreated another id.
The current production helper updates in place, so a missing document must not
be resurrected. Import the real module and inject only its lazy database seam:
replacing Firestore/packages in sys.modules hid dependencies and broke collection
when MCP callback transactions added another SDK import.
"""

from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from database import apps


@pytest.fixture
def app_store(monkeypatch):
    database = MagicMock()
    reference = database.collection.return_value.document.return_value
    monkeypatch.setattr(apps, 'db', database)
    return database, reference


def test_missing_private_doc_is_not_recreated(app_store):
    _, reference = app_store
    reference.update.side_effect = NotFound('Synthetic missing app')
    with pytest.raises(NotFound):
        apps.update_app_visibility_in_db('plug-private', private=False)
    reference.update.assert_called_once_with({'private': False})
    reference.get.assert_not_called()
    reference.delete.assert_not_called()
    reference.set.assert_not_called()


@pytest.mark.parametrize('app_id,private', [('plug-private', False), ('plug', True)])
def test_visibility_change_updates_the_same_document_in_place(app_store, app_id, private):
    database, reference = app_store
    apps.update_app_visibility_in_db(app_id, private=private)
    database.collection.assert_called_once_with(apps.apps_collection)
    database.collection.return_value.document.assert_called_once_with(app_id)
    reference.update.assert_called_once_with({'private': private})
    reference.get.assert_not_called()
    reference.delete.assert_not_called()
    reference.set.assert_not_called()
