from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from services.users import agent_vm_account_cleanup


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


@patch('services.users.agent_vm_account_cleanup.users_db')
@patch('services.users.agent_vm_account_cleanup.read_agent_vm_migration_journals')
@patch('services.users.agent_vm_account_cleanup._migration_reconcile_lease_active')
def test_delete_agent_vm_for_account_no_vm(
    mock_lease_active, mock_read_journals, mock_users_db
):
    uid = 'test-uid'
    mock_users_db.get_agent_vm.return_value = None
    mock_users_db.get_late_agent_vm_cleanup.return_value = None
    mock_read_journals.return_value = []
    mock_lease_active.return_value = False

    # Should just return without doing anything
    agent_vm_account_cleanup.delete_agent_vm_for_account(uid)

    mock_users_db.get_agent_vm.assert_called_once_with(uid)
    mock_read_journals.assert_called_once_with(uid)


@patch('services.users.agent_vm_account_cleanup.users_db')
@patch('services.users.agent_vm_account_cleanup.read_agent_vm_migration_journals')
@patch('services.users.agent_vm_account_cleanup._migration_reconcile_lease_active')
def test_delete_agent_vm_for_account_lease_active(
    mock_lease_active, mock_read_journals, mock_users_db
):
    uid = 'test-uid'
    mock_users_db.get_agent_vm.return_value = {'vmName': 'test-vm'}
    mock_read_journals.return_value = []
    mock_lease_active.return_value = True

    with pytest.raises(RuntimeError, match='Agent VM migration reconcile lease is active'):
        agent_vm_account_cleanup.delete_agent_vm_for_account(uid)


@patch('services.users.agent_vm_account_cleanup._gce_project_id')
@patch('services.users.agent_vm_account_cleanup.users_db')
@patch('services.users.agent_vm_account_cleanup.read_agent_vm_migration_journals')
@patch('services.users.agent_vm_account_cleanup._migration_reconcile_lease_active')
def test_delete_agent_vm_for_account_no_gce_project(
    mock_lease_active, mock_read_journals, mock_users_db, mock_gce_project_id
):
    uid = 'test-uid'
    mock_users_db.get_agent_vm.return_value = {'vmName': 'test-vm'}
    mock_read_journals.return_value = []
    mock_lease_active.return_value = False
    mock_gce_project_id.return_value = None

    with pytest.raises(RuntimeError, match='GCE project is not configured for account-deletion VM cleanup'):
        agent_vm_account_cleanup.delete_agent_vm_for_account(uid)


@patch('services.users.agent_vm_account_cleanup.google.auth.default')
@patch('services.users.agent_vm_account_cleanup.httpx.Client')
@patch('services.users.agent_vm_account_cleanup._cleanup_agent_vm_migration_resources')
@patch('services.users.agent_vm_account_cleanup._delete_current_agent_vm')
@patch('services.users.agent_vm_account_cleanup._load_agent_vm_migration_cleanup_plans')
@patch('services.users.agent_vm_account_cleanup._gce_project_id')
@patch('services.users.agent_vm_account_cleanup.users_db')
@patch('services.users.agent_vm_account_cleanup.read_agent_vm_migration_journals')
@patch('services.users.agent_vm_account_cleanup._migration_reconcile_lease_active')
def test_delete_agent_vm_for_account_success(
    mock_lease_active,
    mock_read_journals,
    mock_users_db,
    mock_gce_project_id,
    mock_load_plans,
    mock_delete_current,
    mock_cleanup_migration,
    mock_httpx_client,
    mock_google_auth,
):
    uid = 'test-uid'
    vm = {'vmName': 'test-vm'}
    mock_users_db.get_agent_vm.return_value = vm
    journals = []
    mock_read_journals.return_value = journals
    mock_lease_active.return_value = False
    mock_gce_project_id.return_value = 'test-project'

    mock_credentials = MagicMock()
    mock_credentials.token = 'test-token'
    mock_google_auth.return_value = (mock_credentials, 'project')

    mock_client = MagicMock()
    mock_httpx_client.return_value.__enter__.return_value = mock_client

    mock_plans = [{'plan': 'data'}]
    mock_load_plans.return_value = mock_plans

    agent_vm_account_cleanup.delete_agent_vm_for_account(uid)

    mock_credentials.refresh.assert_called_once()

    headers = {'Authorization': 'Bearer test-token'}

    mock_load_plans.assert_called_once_with(
        uid, journals, vm, 'test-project', mock_client, headers
    )

    mock_delete_current.assert_called_once_with(
        uid, vm, mock_plans, 'test-project', mock_client, headers, legacy_late_cleanup=False
    )

    mock_cleanup_migration.assert_called_once_with(
        uid, mock_plans, 'test-project', mock_client, headers
    )
