"""Deleting a folder must relocate its conversations to the default folder.

``delete_folder(uid, folder_id)`` with no ``move_to_folder_id`` promises (per its
docstring) to move the folder's conversations to the default folder. It selects that
folder with ``next((f for f in folders if f.get('is_default')), None)``.

``initialize_system_folders`` used to compute the flag as
``folder_config['category_mapping'] == 'other'``, but SYSTEM_FOLDERS only defines the
mappings ``work``/``personal``/``social`` — never ``other``. So every folder was written
with ``is_default=False``, the lookup always returned ``None``, the move block was
skipped entirely, and the conversations kept a ``folder_id`` pointing at a folder that
had just been deleted: invisible in every folder listing and 404 on fetch.
"""

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _install_google_stubs() -> None:
    """Stand in for google.cloud only when it is genuinely unavailable.

    CI installs the real client library; this keeps the test runnable in a minimal
    environment without shadowing the real package where it exists.
    """
    try:  # pragma: no cover - depends on the environment
        from google.cloud import firestore  # noqa: F401
        from google.cloud.firestore_v1 import FieldFilter  # noqa: F401

        return
    except ImportError:
        pass

    google_pkg = sys.modules.setdefault('google', _AutoMockModule('google'))
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    cloud_pkg = _AutoMockModule('google.cloud')
    cloud_pkg.__path__ = []  # type: ignore[attr-defined]
    firestore_v1 = _AutoMockModule('google.cloud.firestore_v1')
    firestore_v1.FieldFilter = MagicMock()  # type: ignore[attr-defined]
    sys.modules['google.cloud'] = cloud_pkg
    sys.modules['google.cloud.firestore'] = _AutoMockModule('google.cloud.firestore')
    sys.modules['google.cloud.firestore_v1'] = firestore_v1


_install_google_stubs()
sys.modules.setdefault('database._client', _AutoMockModule('database._client'))

import database.folders as folders_db  # noqa: E402


@pytest.fixture
def provisioned(monkeypatch):
    """The folders the REAL initialize_system_folders writes, with a fresh user.

    Driving the production function (rather than restating its logic here) is what makes
    these assertions a regression test for the is_default computation itself.
    """
    folders_ref = MagicMock()
    folders_ref.limit.return_value.stream.return_value = []  # no existing folders
    db = MagicMock()
    db.collection.return_value.document.return_value.collection.return_value = folders_ref
    monkeypatch.setattr(folders_db, 'db', db)
    return folders_db.initialize_system_folders('uid')


@pytest.fixture
def firestore(monkeypatch):
    """Mock Firestore, capturing the folder_id each conversation is reassigned to."""
    batch = MagicMock()
    moved = []
    batch.update.side_effect = lambda ref, payload: moved.append(payload['folder_id'])

    conversation = MagicMock()
    db = MagicMock()
    db.batch.return_value = batch
    user_ref = db.collection.return_value.document.return_value
    user_ref.collection.return_value.where.return_value.stream.return_value = [conversation]

    monkeypatch.setattr(folders_db, 'db', db)
    monkeypatch.setattr(folders_db, 'update_folder_conversation_count', MagicMock())
    return db, moved


class TestSystemFolderDefaultFlag:
    """Assertions against the folders initialize_system_folders actually writes."""

    def test_exactly_one_provisioned_folder_is_marked_default(self, provisioned):
        defaults = [f['name'] for f in provisioned if f['is_default']]
        assert len(defaults) == 1, f"expected exactly one default folder, got {defaults}"

    def test_default_folder_is_where_the_other_category_lands(self, provisioned):
        # The delete_folder docstring calls it "the default 'Other' folder"; the 'other'
        # category maps to a real system folder, and that folder is the default.
        default = next(f for f in provisioned if f['is_default'])
        assert default['category_mapping'] == folders_db.CATEGORY_TO_FOLDER_MAPPING['other']

    def test_no_system_folder_uses_the_literal_other_mapping(self):
        # The reason the original `== 'other'` comparison could never be True.
        assert all(cfg['category_mapping'] != 'other' for cfg in folders_db.SYSTEM_FOLDERS)


class TestDeleteFolderRelocatesConversations:
    @staticmethod
    def _work_id(provisioned):
        return next(f['id'] for f in provisioned if f['category_mapping'] == 'work')

    @staticmethod
    def _default_id(provisioned):
        return next(f['id'] for f in provisioned if f['is_default'])

    def test_conversations_move_to_default_when_no_target_given(self, monkeypatch, provisioned, firestore):
        _db, moved = firestore
        monkeypatch.setattr(folders_db, 'get_folders', lambda uid: provisioned)

        assert folders_db.delete_folder('uid', self._work_id(provisioned)) is True

        assert moved == [self._default_id(provisioned)], "conversation was not relocated to the default folder"

    def test_falls_back_when_legacy_folders_have_flag_unset(self, monkeypatch, provisioned, firestore):
        # Users provisioned before the fix have is_default=False on every folder.
        _db, moved = firestore
        legacy = [{**f, 'is_default': False} for f in provisioned]
        monkeypatch.setattr(folders_db, 'get_folders', lambda uid: legacy)

        folders_db.delete_folder('uid', self._work_id(provisioned))

        expected = next(
            f['id'] for f in provisioned if f['category_mapping'] == folders_db.CATEGORY_TO_FOLDER_MAPPING['other']
        )
        assert moved == [expected], "legacy folders left the conversation orphaned"

    def test_never_targets_the_folder_being_deleted(self, monkeypatch, provisioned, firestore):
        # Deleting the default folder itself must not move conversations into it.
        _db, moved = firestore
        monkeypatch.setattr(folders_db, 'get_folders', lambda uid: provisioned)
        default_id = self._default_id(provisioned)

        folders_db.delete_folder('uid', default_id)

        assert default_id not in moved, "conversations were moved into the folder being deleted"

    def test_explicit_target_is_respected(self, monkeypatch, provisioned, firestore):
        _db, moved = firestore
        monkeypatch.setattr(folders_db, 'get_folders', lambda uid: provisioned)
        social_id = next(f['id'] for f in provisioned if f['category_mapping'] == 'social')

        folders_db.delete_folder('uid', self._work_id(provisioned), move_to_folder_id=social_id)

        assert moved == [social_id]
