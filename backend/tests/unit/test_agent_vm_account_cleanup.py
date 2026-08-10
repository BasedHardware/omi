from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


class _AutoMockModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self._created = set()

    def find_spec(self, name, path=None, target=None):
        if name == 'database' or name.startswith('database.') or name == 'utils' or name.startswith('utils.'):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        self._created.add(spec.name)
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


_finder = _StubFinder()
sys.meta_path.insert(0, _finder)
try:
    agent_vm_account_cleanup = importlib.import_module('services.users.agent_vm_account_cleanup')
finally:
    sys.meta_path.remove(_finder)
    for _name in _finder._created:
        sys.modules.pop(_name, None)
    for _name in ('services.users.agent_vm_account_cleanup', 'services.users', 'services'):
        sys.modules.pop(_name, None)


def test_gce_project_id_precedence():
    with patch.dict(
        os.environ,
        {
            'GCE_PROJECT_ID': 'gce-project',
            'GOOGLE_CLOUD_PROJECT': 'google-cloud-project',
            'FIREBASE_PROJECT_ID': 'firebase-project',
            'GCP_PROJECT_ID': 'gcp-project',
        },
    ):
        assert agent_vm_account_cleanup._gce_project_id() == 'gce-project'

    with patch.dict(
        os.environ,
        {
            'GOOGLE_CLOUD_PROJECT': 'google-cloud-project',
            'FIREBASE_PROJECT_ID': 'firebase-project',
            'GCP_PROJECT_ID': 'gcp-project',
        },
        clear=True,
    ):
        assert agent_vm_account_cleanup._gce_project_id() == 'google-cloud-project'

    with patch.dict(
        os.environ,
        {
            'FIREBASE_PROJECT_ID': 'firebase-project',
            'GCP_PROJECT_ID': 'gcp-project',
        },
        clear=True,
    ):
        assert agent_vm_account_cleanup._gce_project_id() == 'firebase-project'

    with patch.dict(
        os.environ,
        {
            'GCP_PROJECT_ID': 'gcp-project',
        },
        clear=True,
    ):
        assert agent_vm_account_cleanup._gce_project_id() == 'gcp-project'

    with patch.dict(os.environ, {}, clear=True):
        assert agent_vm_account_cleanup._gce_project_id() is None


def test_owner_disk_label():
    uid = 'test-user-id'
    expected_hash = agent_vm_account_cleanup.hashlib.sha256(uid.encode('utf-8')).hexdigest()[:20]
    assert agent_vm_account_cleanup._owner_disk_label(uid) == expected_hash


def test_delete_agent_vm_for_account_no_vm():
    uid = 'test-uid'
    with (
        patch.object(agent_vm_account_cleanup, 'users_db') as mock_users_db,
        patch.object(agent_vm_account_cleanup, 'read_agent_vm_migration_journals') as mock_read_journals,
        patch.object(agent_vm_account_cleanup, '_migration_reconcile_lease_active') as mock_lease_active,
    ):
        mock_users_db.get_agent_vm.return_value = None
        mock_users_db.get_late_agent_vm_cleanup.return_value = None
        mock_read_journals.return_value = []
        mock_lease_active.return_value = False

        # Should just return without doing anything
        agent_vm_account_cleanup.delete_agent_vm_for_account(uid)

        mock_users_db.get_agent_vm.assert_called_once_with(uid)
        mock_read_journals.assert_called_once_with(uid)


def test_delete_agent_vm_for_account_lease_active():
    uid = 'test-uid'
    with (
        patch.object(agent_vm_account_cleanup, 'users_db') as mock_users_db,
        patch.object(agent_vm_account_cleanup, 'read_agent_vm_migration_journals') as mock_read_journals,
        patch.object(agent_vm_account_cleanup, '_migration_reconcile_lease_active') as mock_lease_active,
    ):
        mock_users_db.get_agent_vm.return_value = {'vmName': 'test-vm'}
        mock_read_journals.return_value = []
        mock_lease_active.return_value = True

        with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is active'):
            agent_vm_account_cleanup.delete_agent_vm_for_account(uid)


def test_delete_agent_vm_for_account_no_gce_project():
    uid = 'test-uid'
    with (
        patch.object(agent_vm_account_cleanup, '_gce_project_id') as mock_gce_project_id,
        patch.object(agent_vm_account_cleanup, 'users_db') as mock_users_db,
        patch.object(agent_vm_account_cleanup, 'read_agent_vm_migration_journals') as mock_read_journals,
        patch.object(agent_vm_account_cleanup, '_migration_reconcile_lease_active') as mock_lease_active,
    ):
        mock_users_db.get_agent_vm.return_value = {'vmName': 'test-vm'}
        mock_read_journals.return_value = []
        mock_lease_active.return_value = False
        mock_gce_project_id.return_value = None

        with pytest.raises(RuntimeError, match='GCE project is not configured for account-deletion VM cleanup'):
            agent_vm_account_cleanup.delete_agent_vm_for_account(uid)


def test_delete_agent_vm_for_account_success():
    uid = 'test-uid'
    vm = {'vmName': 'test-vm'}
    with (
        patch.object(agent_vm_account_cleanup, 'google') as mock_google,
        patch.object(agent_vm_account_cleanup, 'httpx') as mock_httpx,
        patch.object(agent_vm_account_cleanup, '_cleanup_agent_vm_migration_resources') as mock_cleanup_migration,
        patch.object(agent_vm_account_cleanup, '_delete_current_agent_vm') as mock_delete_current,
        patch.object(agent_vm_account_cleanup, '_load_agent_vm_migration_cleanup_plans') as mock_load_plans,
        patch.object(agent_vm_account_cleanup, '_gce_project_id') as mock_gce_project_id,
        patch.object(agent_vm_account_cleanup, 'users_db') as mock_users_db,
        patch.object(agent_vm_account_cleanup, 'read_agent_vm_migration_journals') as mock_read_journals,
        patch.object(agent_vm_account_cleanup, '_migration_reconcile_lease_active') as mock_lease_active,
    ):
        mock_users_db.get_agent_vm.return_value = vm
        journals = []
        mock_read_journals.return_value = journals
        mock_lease_active.return_value = False
        mock_gce_project_id.return_value = 'test-project'

        mock_credentials = MagicMock()
        mock_credentials.token = 'test-token'
        mock_google.auth.default.return_value = (mock_credentials, 'project')

        mock_client = MagicMock()
        mock_httpx.Client.return_value.__enter__.return_value = mock_client

        mock_plans = [{'plan': 'data'}]
        mock_load_plans.return_value = mock_plans

        agent_vm_account_cleanup.delete_agent_vm_for_account(uid)

        mock_google.auth.default.assert_called_once_with(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        mock_credentials.refresh.assert_called_once()

        headers = {'Authorization': 'Bearer test-token'}

        mock_load_plans.assert_called_once_with(uid, journals, vm, 'test-project', mock_client, headers)

        mock_delete_current.assert_called_once_with(
            uid, vm, mock_plans, 'test-project', mock_client, headers, legacy_late_cleanup=False
        )

        mock_cleanup_migration.assert_called_once_with(uid, mock_plans, 'test-project', mock_client, headers)
