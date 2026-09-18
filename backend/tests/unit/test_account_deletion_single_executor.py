"""One owner executes a wipe, and it is never a process pointed at production."""

from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from services.users import account_deletion
from utils import cloud_tasks


def _pending(uid: str = 'user-1') -> dict:
    return {'uid': uid, 'wipe_job_id': 'job-1', 'wipe_status': 'failed'}


def test_reconciliation_redispatches_and_never_executes(monkeypatch):
    """Reconciliation owns re-dispatch only; the OIDC handler owns execution."""
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit: [_pending()])
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(
        account_deletion,
        'background_wipe_user_data',
        lambda *args, **kwargs: pytest.fail('reconciliation must never execute a wipe'),
    )
    enqueued: list[str] = []
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', lambda job_id: enqueued.append(job_id))

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert enqueued == ['job-1']
    assert result['requeued'] == 1


def test_reconciliation_ignores_inline_mode(monkeypatch):
    """Inline mode is for local execution; it must not make the reconciler an executor."""
    monkeypatch.delenv('ACCOUNT_DELETION_DISPATCH_MODE', raising=False)
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit: [_pending()])
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda *args, **kwargs: pytest.fail('reconciliation must not schedule an in-process wipe'),
    )
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', lambda job_id: None)

    assert account_deletion.reconcile_pending_deletion_wipes()['requeued'] == 1


@pytest.mark.parametrize('variable', ['GOOGLE_CLOUD_PROJECT', 'SYNC_TASKS_PROJECT'])
def test_inline_execution_is_refused_against_production_data(monkeypatch, variable):
    """A local run with .env pointing at prod executed real wipes; the project is the honest test."""
    monkeypatch.delenv('GOOGLE_CLOUD_PROJECT', raising=False)
    monkeypatch.delenv('SYNC_TASKS_PROJECT', raising=False)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)
    monkeypatch.setenv(variable, 'based-hardware')

    with pytest.raises(RuntimeError, match='refusing inline account-deletion execution'):
        cloud_tasks.assert_inline_account_deletion_permitted()


def test_inline_execution_still_runs_against_a_non_production_project(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware-dev')
    monkeypatch.delenv('SYNC_TASKS_PROJECT', raising=False)

    cloud_tasks.assert_inline_account_deletion_permitted()


def test_enqueue_deletion_wipe_refuses_inline_dispatch_against_production(monkeypatch):
    monkeypatch.delenv('ACCOUNT_DELETION_DISPATCH_MODE', raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'based-hardware')
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda *args, **kwargs: pytest.fail('a production-pointed process must not run a wipe'),
    )

    with pytest.raises(RuntimeError, match='refusing inline account-deletion execution'):
        account_deletion.enqueue_deletion_wipe('user-1', 'job-1')


def test_startup_fails_when_the_configured_queue_does_not_exist(monkeypatch):
    """Env vars said 'configured' for a month while every dispatch 404'd."""
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'based-hardware')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'us-central1')
    monkeypatch.setenv('ACCOUNT_DELETION_TASKS_QUEUE', 'account-deletion')
    client = MagicMock()
    client.queue_path.return_value = 'projects/p/locations/l/queues/account-deletion'
    client.get_queue.side_effect = NotFound('Queue does not exist')

    with pytest.raises(RuntimeError, match='does not exist'):
        cloud_tasks.assert_account_deletion_queue_exists(client)


def test_an_unreachable_tasks_api_is_not_proof_of_absence(monkeypatch):
    """Availability is not absence: a transient error must not block startup."""
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'based-hardware')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'us-central1')
    monkeypatch.setenv('ACCOUNT_DELETION_TASKS_QUEUE', 'account-deletion')
    client = MagicMock()
    client.queue_path.return_value = 'projects/p/locations/l/queues/account-deletion'
    client.get_queue.side_effect = TimeoutError('deadline exceeded')

    cloud_tasks.assert_account_deletion_queue_exists(client)


def test_queue_probe_is_inert_without_configuration(monkeypatch):
    monkeypatch.delenv('SYNC_TASKS_PROJECT', raising=False)
    monkeypatch.delenv('ACCOUNT_DELETION_TASKS_QUEUE', raising=False)
    client = MagicMock()

    cloud_tasks.assert_account_deletion_queue_exists(client)

    client.get_queue.assert_not_called()
