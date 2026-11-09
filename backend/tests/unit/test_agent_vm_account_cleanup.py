from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='module')
def agent_vm_account_cleanup():
    stubs = {
        name: AutoMockModule(name) for name in ('database', 'database.users', 'database.account_deletion_transitions')
    }
    stubs['database'].__path__ = []
    with stub_modules(stubs):
        yield load_module_fresh(
            'services.users.agent_vm_account_cleanup',
            str(BACKEND_DIR / 'services' / 'users' / 'agent_vm_account_cleanup.py'),
        )


def test_gce_project_id_precedence(agent_vm_account_cleanup):
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


def test_owner_disk_label(agent_vm_account_cleanup):
    uid = 'test-user-id'
    expected_hash = agent_vm_account_cleanup.hashlib.sha256(uid.encode('utf-8')).hexdigest()[:20]
    assert agent_vm_account_cleanup._owner_disk_label(uid) == expected_hash


def test_delete_agent_vm_for_account_no_vm(agent_vm_account_cleanup):
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


def test_delete_agent_vm_for_account_lease_active(agent_vm_account_cleanup):
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


def test_delete_agent_vm_for_account_no_gce_project(agent_vm_account_cleanup):
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


def test_delete_agent_vm_for_account_success(agent_vm_account_cleanup):
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


@pytest.mark.parametrize(
    'expires_at',
    [
        pytest.param(10**400, id='huge-int'),
        pytest.param(-(10**400), id='huge-negative-int'),
        pytest.param('9' * 400, id='huge-numeric-string'),
        pytest.param(float('inf'), id='inf'),
        pytest.param(float('nan'), id='nan'),
        pytest.param('not-a-number', id='non-numeric-string'),
    ],
)
def test_migration_reconcile_lease_malformed_expiry_is_ambiguous(agent_vm_account_cleanup, expires_at):
    vm = {'reconcile': {'lease': {'expiresAt': expires_at}}}

    with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is ambiguous'):
        agent_vm_account_cleanup._migration_reconcile_lease_active(vm, [{}], now=1000.0)


@pytest.mark.parametrize('expires_at, expected', [(2000, True), ('2000.5', True), (500, False)])
def test_migration_reconcile_lease_finite_expiry_is_evaluated(agent_vm_account_cleanup, expires_at, expected):
    vm = {'reconcile': {'lease': {'expiresAt': expires_at}}}

    assert agent_vm_account_cleanup._migration_reconcile_lease_active(vm, [{}], now=1000.0) is expected


def test_delete_agent_vm_for_account_oversized_lease_expiry_raises_controlled_error(agent_vm_account_cleanup):
    vm = {'vmName': 'test-vm', 'reconcile': {'lease': {'expiresAt': 10**400}}}
    with (
        patch.object(agent_vm_account_cleanup, 'users_db') as mock_users_db,
        patch.object(agent_vm_account_cleanup, 'read_agent_vm_migration_journals') as mock_read_journals,
        patch.object(agent_vm_account_cleanup, '_gce_project_id') as mock_gce_project_id,
    ):
        mock_users_db.get_agent_vm.return_value = vm
        mock_read_journals.return_value = [{}]

        with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is ambiguous'):
            agent_vm_account_cleanup.delete_agent_vm_for_account('test-uid')

        mock_gce_project_id.assert_not_called()
