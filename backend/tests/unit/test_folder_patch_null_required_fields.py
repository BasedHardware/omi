"""A PATCH to a folder must not write explicit nulls over fields the Folder model requires.

`PATCH /v1/folders/{folder_id}` validates the payload with `UpdateFolderRequest` (all fields optional),
then persists `model_dump(exclude_unset=True)`. `exclude_unset` keeps a key the caller sent
as explicit null — and released mobile/web clients serialize omitted/cleared fields as null.
`Folder.name/color/icon/order` are non-nullable, so writing a null over the stored values in Firestore
would cause every `Folder(**doc)` read to raise `ValidationError` (crashing GET /v1/folders and
GET /v1/folders/{id} with HTTP 500) with no un-poisoning path.

Fix: explicit nulls for required fields ('name', 'color', 'icon', 'order') mean "not sent" and
are dropped before persistence, while genuinely optional fields (e.g. `description`) still pass
a null through to allow clearing.
"""

from database.ports.folders import FolderEntity, FolderUpdate
from database import folders as firestore_folders
from fastapi import HTTPException

from datetime import datetime, timezone
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from models.folder import UpdateFolderRequest, Folder
    from routers import folders as folders_router
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)

folders_router.FolderUpdate = FolderUpdate

EXISTING_FOLDER = {
    'id': 'folder-1',
    'name': 'Existing Folder',
    'description': 'Existing description',
    'color': '#6B7280',
    'icon': 'folder',
    'created_at': datetime.now(timezone.utc),
    'updated_at': datetime.now(timezone.utc),
    'order': 0,
    'is_default': False,
    'is_system': False,
    'conversation_count': 5,
}

NULLED_REQUIRED = {
    'name': None,
    'color': None,
    'icon': None,
    'order': None,
}


class TestFolderPatchNullRequiredFields(unittest.TestCase):
    def test_patch_point_read_budget_through_firestore_adapter(self):
        for payload, expected_reads in (
            ({'name': 'Renamed'}, 2),
            ({'description': None}, 2),
            (NULLED_REQUIRED, 1),
            ({}, 1),
        ):
            with self.subTest(payload=payload):
                stored = {**EXISTING_FOLDER, 'revision': 4}
                client = MagicMock()
                ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
                snapshot = MagicMock(exists=True)
                snapshot.to_dict.side_effect = lambda: dict(stored)
                ref.get.return_value = snapshot

                def apply_update(data):
                    stored.update({**data, 'revision': stored['revision'] + data['revision'].value})

                ref.update.side_effect = apply_update

                def get_folder(uid, folder_id):
                    return firestore_folders.get_folder(uid, folder_id, firestore_client=client)

                def update_folder(uid, folder_id, patch_data):
                    return firestore_folders.update_folder(uid, folder_id, patch_data, firestore_client=client)

                with patch.object(folders_router.folders_db, 'get_folder', side_effect=get_folder), patch.object(
                    folders_router.folders_db, 'update_folder', side_effect=update_folder
                ):
                    result = folders_router.update_folder(
                        'folder-1', UpdateFolderRequest.model_validate(payload), 'test-uid'
                    )

                self.assertEqual(ref.get.call_count, expected_reads)
                self.assertEqual(ref.update.call_count, int(expected_reads == 2))
                self.assertEqual(result['name'], payload.get('name') or EXISTING_FOLDER['name'])
                if 'description' in payload:
                    self.assertIsNone(result['description'])

    def test_missing_patch_still_returns_not_found(self):
        for payload in ({'name': 'Renamed'}, NULLED_REQUIRED, {}):
            with self.subTest(payload=payload), patch.object(
                folders_router.folders_db, 'get_folder', return_value=None
            ), patch.object(folders_router.folders_db, 'update_folder', return_value=None):
                with self.assertRaises(HTTPException) as error:
                    folders_router.update_folder('missing', UpdateFolderRequest.model_validate(payload), 'test-uid')
                self.assertEqual(error.exception.status_code, 404)

    def test_explicit_null_required_fields_are_not_written(self):
        recorded_updates = []

        def fake_get_folder(uid, folder_id):
            return FolderEntity.model_construct(**EXISTING_FOLDER)

        def fake_update_folder(uid, folder_id, data):
            recorded_updates.append(data.model_dump(exclude_unset=True))
            return FolderEntity.model_construct(**EXISTING_FOLDER)

        with patch.object(folders_router.folders_db, 'get_folder', side_effect=fake_get_folder), patch.object(
            folders_router.folders_db, 'update_folder', side_effect=fake_update_folder
        ):

            req = UpdateFolderRequest.model_validate({**NULLED_REQUIRED, 'description': None})
            result = folders_router.update_folder('folder-1', req, 'test-uid')

            # Verified returned folder is a valid Folder instance / dict
            self.assertEqual(result['name'], 'Existing Folder')
            self.assertEqual(len(recorded_updates), 1)
            written = recorded_updates[0]

            # Required fields are dropped and not written as None
            for field in ('name', 'color', 'icon', 'order'):
                self.assertNotIn(field, written)

            # Optional description allows null clearing
            self.assertIn('description', written)
            self.assertIsNone(written['description'])

    def test_real_required_fields_still_update(self):
        recorded_updates = []

        def fake_get_folder(uid, folder_id):
            current = dict(EXISTING_FOLDER)
            if recorded_updates:
                current.update(recorded_updates[-1])
            return FolderEntity.model_construct(**current)

        def fake_update_folder(uid, folder_id, data):
            recorded_updates.append(data.model_dump(exclude_unset=True))
            return FolderEntity.model_construct(**EXISTING_FOLDER)

        with patch.object(folders_router.folders_db, 'get_folder', side_effect=fake_get_folder), patch.object(
            folders_router.folders_db, 'update_folder', side_effect=fake_update_folder
        ):

            req = UpdateFolderRequest.model_validate({'name': 'New Folder Name', 'color': '#1DA1F2'})
            result = folders_router.update_folder('folder-1', req, 'test-uid')

            self.assertEqual(result['name'], 'New Folder Name')
            self.assertEqual(len(recorded_updates), 1)
            written = recorded_updates[0]
            self.assertEqual(written['name'], 'New Folder Name')
            self.assertEqual(written['color'], '#1DA1F2')


if __name__ == '__main__':
    unittest.main()
