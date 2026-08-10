import importlib.abc
import importlib.machinery
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _AutoMockModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUB_PREFIXES = (
    'database',
    'firebase_admin',
    'google.cloud',
    'google.api_core',
    'pinecone',
    'typesense',
    'utils',
)


def _should_stub(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix + '.') for prefix in _STUB_PREFIXES)


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self._created: set[str] = set()

    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
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
    from services.users import agent_vm_account_cleanup  # noqa: E402
    from services.users import account_deletion  # noqa: E402
finally:
    # Remove the meta-path finder and clear *only* the modules that the
    # stub finder actually created. Broadly deleting every module matching
    # _STUB_PREFIXES (database, utils, …) would also evict real project
    # modules imported by other tests collected in the same pytest process.
    sys.meta_path.remove(_finder)
    for _name in list(_finder._created):
        sys.modules.pop(_name, None)
    # The imported service module itself was loaded against the MagicMock
    # stubs (its globals hold MagicMock objects for users_db, stripe_utils,
    # etc.). Pop it — along with its parent packages — so a later test that
    # imports the real service reloads it with production dependencies
    # instead of reusing this mock-backed copy.
    for _svc_name in (
        'services.users.account_deletion',
        'services.users.agent_vm_account_cleanup',
        'services.users',
        'services',
    ):
        sys.modules.pop(_svc_name, None)


def _new_wipe_intent(job_id='job-1'):
    return {'wipe_job_id': job_id, 'dispatch_claimed': True}


class _ComputeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


class _ComputeClient:
    def __init__(self, *, instances=None, disks=None, delete_statuses=None, post_statuses=None, no_operation=False):
        self.instances = dict(instances or {})
        self.disks = dict(disks or {})
        self.delete_statuses = dict(delete_statuses or {})
        self.post_statuses = dict(post_statuses or {})
        self.no_operation = no_operation
        self.get_calls = []
        self.delete_calls = []
        self.post_calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, url, **_kwargs):
        self.get_calls.append(url)
        if '/operations/' in url:
            return _ComputeResponse(payload={'status': 'DONE'})
        if '/instances/' in url:
            name = url.rsplit('/', 1)[-1]
            payload = self.instances.get(name)
        elif '/disks/' in url:
            name = url.rsplit('/', 1)[-1]
            payload = self.disks.get(name)
        else:
            raise AssertionError(f'unexpected GET {url}')
        return _ComputeResponse(200, payload) if payload is not None else _ComputeResponse(404)

    def delete(self, url, **_kwargs):
        self.delete_calls.append(url)
        status_code = next(
            (status for suffix, status in self.delete_statuses.items() if url.endswith(suffix)),
            200,
        )
        if status_code != 404:
            if '/instances/' in url:
                instance_name = url.rsplit('/', 1)[-1]
                self.instances.pop(instance_name, None)
                for disk in self.disks.values():
                    users = disk.get('users')
                    if isinstance(users, list):
                        disk['users'] = [
                            user for user in users if not str(user).endswith(f'/instances/{instance_name}')
                        ]
            elif '/disks/' in url:
                self.disks.pop(url.rsplit('/', 1)[-1], None)
        payload = {} if self.no_operation else {'name': 'cleanup-operation'}
        return _ComputeResponse(status_code, payload)

    def post(self, url, *, json=None, **_kwargs):
        self.post_calls.append((url, json))
        status_code = next(
            (status for suffix, status in self.post_statuses.items() if url.endswith(suffix)),
            200,
        )
        if status_code == 200 and url.endswith('/setLabels'):
            name = url.split('/instances/', 1)[-1].split('/', 1)[0]
            if name in self.instances and isinstance(json, dict):
                self.instances[name]['labels'] = dict(json.get('labels') or {})
        payload = {} if self.no_operation else {'name': 'label-operation'}
        return _ComputeResponse(status_code, payload)


def _migration_journal(*, reused_state_disk=True, with_source_clone=False, missing_resource_ids=False):
    migration_id = 'a' * 24
    journal = {
        'migrationId': migration_id,
        'oldVmName': 'omi-agent-old',
        'oldZone': 'us-central1-a',
        'oldInstanceId': '101',
        'candidateVmName': 'omi-agent-old-m-' + migration_id[:12],
        'candidateInstanceId': '202',
        'stateDiskName': 'omi-agent-state-' + migration_id[:16],
        'stateDiskId': '303',
        'stateDiskReused': reused_state_disk,
        'sourceCloneDiskName': '',
        'sourceCloneDiskId': '',
    }
    if with_source_clone:
        journal.update(
            {
                'stateDiskReused': False,
                'sourceCloneDiskName': 'omi-agent-source-' + migration_id[:16],
                'sourceCloneDiskId': '404',
            }
        )
    if missing_resource_ids:
        journal.pop('candidateInstanceId')
        journal.pop('stateDiskId')
        if with_source_clone:
            journal.pop('sourceCloneDiskId')
    return journal


def _configure_compute_cleanup(monkeypatch, client):
    credentials = SimpleNamespace(token='test-token', refresh=lambda _request: None)
    monkeypatch.setenv('GCE_PROJECT_ID', 'test-project')
    monkeypatch.setattr(agent_vm_account_cleanup.google.auth, 'default', lambda **_kwargs: (credentials, None))
    monkeypatch.setattr(agent_vm_account_cleanup.httpx, 'Client', lambda **_kwargs: client)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'clear_late_agent_vm_cleanup', MagicMock())


@pytest.fixture(autouse=True)
def _stub_new_external_cleanup_boundaries(monkeypatch):
    monkeypatch.setattr(account_deletion, 'delete_agent_vm_for_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_account_credentials', MagicMock())


def test_agent_vm_account_cleanup_deletes_mid_migration_candidate_and_reused_state_disk(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal()
    owner_label = agent_vm_account_cleanup._owner_disk_label(uid)
    client = _ComputeClient(
        instances={
            journal['oldVmName']: {
                'id': journal['oldInstanceId'],
                'labels': {
                    'omi-agent-owner': owner_label,
                    'omi-agent-migration': journal['migrationId'],
                },
            },
            journal['candidateVmName']: {
                'id': journal['candidateInstanceId'],
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-predecessor': journal['oldInstanceId'],
                },
            },
        },
        disks={
            journal['stateDiskName']: {
                'id': journal['stateDiskId'],
                'labels': {'omi-agent-role': 'state', 'omi-agent-owner': owner_label},
                'users': [],
            }
        },
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {'vmName': journal['oldVmName'], 'zone': journal['oldZone']},
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == [
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/instances/{journal['oldVmName']}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/instances/{journal['candidateVmName']}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/disks/{journal['stateDiskName']}",
    ]


def test_agent_vm_account_cleanup_accepts_relabelled_candidate_from_completed_journal(monkeypatch):
    uid = 'migration-owner'
    owner_label = agent_vm_account_cleanup._owner_disk_label(uid)
    completed = _migration_journal()
    completed.update(
        {
            'migrationId': 'a' * 24,
            'oldVmName': 'omi-agent-original',
            'oldInstanceId': '101',
            'candidateVmName': 'omi-agent-current',
            'candidateInstanceId': '202',
            'state': 'completed',
        }
    )
    in_progress = _migration_journal()
    in_progress.update(
        {
            'migrationId': 'b' * 24,
            'oldVmName': 'omi-agent-current',
            'oldInstanceId': '202',
            'candidateVmName': 'omi-agent-next',
            'candidateInstanceId': '404',
            'state': 'candidate_creating',
        }
    )
    client = _ComputeClient(
        instances={
            completed['candidateVmName']: {
                'id': completed['candidateInstanceId'],
                'labels': {
                    'omi-agent-owner': owner_label,
                    'omi-agent-migration': in_progress['migrationId'],
                    'omi-agent-predecessor': in_progress['oldInstanceId'],
                },
            },
            in_progress['candidateVmName']: {
                'id': in_progress['candidateInstanceId'],
                'labels': {
                    'omi-agent-owner': owner_label,
                    'omi-agent-migration': in_progress['migrationId'],
                    'omi-agent-predecessor': in_progress['oldInstanceId'],
                },
            },
        },
        disks={
            completed['stateDiskName']: {
                'id': completed['stateDiskId'],
                'labels': {'omi-agent-role': 'state', 'omi-agent-owner': owner_label},
                'users': [
                    f"projects/test-project/zones/{completed['oldZone']}/instances/{in_progress['candidateVmName']}"
                ],
            }
        },
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(
        agent_vm_account_cleanup,
        'read_agent_vm_migration_journals',
        lambda _uid: [completed, in_progress],
    )
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {
            'vmName': in_progress['candidateVmName'],
            'zone': completed['oldZone'],
            'instanceId': in_progress['candidateInstanceId'],
        },
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == [
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{completed['oldZone']}/instances/{in_progress['candidateVmName']}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{completed['oldZone']}/instances/{completed['candidateVmName']}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{completed['oldZone']}/disks/{completed['stateDiskName']}",
    ]


def test_agent_vm_account_cleanup_refuses_foreign_candidate_identity(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal()
    client = _ComputeClient(
        instances={
            journal['candidateVmName']: {
                'id': '999',
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-predecessor': journal['oldInstanceId'],
                },
            }
        }
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: None)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    with pytest.raises(RuntimeError, match='identity is ambiguous'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == []


def test_agent_vm_account_cleanup_treats_provider_404s_as_idempotent(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal(with_source_clone=True)
    owner_label = agent_vm_account_cleanup._owner_disk_label(uid)
    client = _ComputeClient(
        instances={
            journal['candidateVmName']: {
                'id': journal['candidateInstanceId'],
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-predecessor': journal['oldInstanceId'],
                },
            }
        },
        disks={
            journal['stateDiskName']: {
                'id': journal['stateDiskId'],
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-role': 'state',
                    'omi-agent-owner': owner_label,
                },
                'users': [],
            },
            journal['sourceCloneDiskName']: {
                'id': journal['sourceCloneDiskId'],
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-role': 'source',
                    'omi-agent-owner': owner_label,
                },
                'users': [],
            },
        },
        delete_statuses={
            f"/instances/{journal['oldVmName']}": 404,
            f"/instances/{journal['candidateVmName']}": 404,
            f"/disks/{journal['stateDiskName']}": 404,
            f"/disks/{journal['sourceCloneDiskName']}": 404,
        },
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {'vmName': journal['oldVmName'], 'zone': journal['oldZone']},
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert len(client.delete_calls) == 3


def test_agent_vm_account_cleanup_keeps_normal_auto_delete_vm_path(monkeypatch):
    uid = 'normal-owner'
    vm_name = 'omi-agent-normal'
    zone = 'us-central1-a'
    instance_url = f'https://compute.googleapis.com/compute/v1/projects/test-project/zones/{zone}/instances/{vm_name}'
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '505',
                'labels': {'omi-agent-owner': agent_vm_account_cleanup._owner_disk_label(uid)},
            }
        }
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {'vmName': vm_name, 'zone': zone, 'instanceId': '505', 'stateDisk': {'autoDelete': True}},
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.get_calls == [
        instance_url,
        'https://compute.googleapis.com/compute/v1/projects/test-project/zones/us-central1-a/operations/cleanup-operation',
    ]
    assert client.delete_calls == [instance_url]


@pytest.mark.parametrize(
    ('vm_update', 'instance'),
    [
        ({'instanceId': '505'}, {'id': '506', 'labels': {'omi-agent-owner': 'owner'}}),
        ({}, {'id': '505', 'labels': {'omi-agent-owner': 'owner'}}),
        ({'instanceId': '505'}, {'id': '505', 'labels': {}}),
    ],
)
def test_agent_vm_account_cleanup_refuses_stale_or_missing_current_identity(monkeypatch, vm_update, instance):
    uid = 'normal-owner'
    vm_name = 'omi-agent-normal'
    zone = 'us-central1-a'
    client = _ComputeClient(instances={vm_name: instance})
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {'vmName': vm_name, 'zone': zone, **vm_update},
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    with pytest.raises(RuntimeError, match='identity is ambiguous'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == []


def test_agent_vm_account_cleanup_treats_current_vm_404_as_idempotent(monkeypatch):
    uid = 'normal-owner'
    vm_name = 'omi-agent-normal'
    client = _ComputeClient()
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {'vmName': vm_name, 'zone': 'us-central1-a', 'instanceId': '505'},
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == []


def test_agent_vm_account_cleanup_retries_late_vm_from_durable_instance_id_after_user_purge(monkeypatch):
    uid = 'late-owner'
    vm_name = 'omi-agent-late'
    zone = 'us-central1-a'
    instance_url = f'https://compute.googleapis.com/compute/v1/projects/test-project/zones/{zone}/instances/{vm_name}'
    owner_label = agent_vm_account_cleanup._owner_disk_label(uid)
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '707',
                'labels': {'omi-agent-owner': owner_label},
            }
        }
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: None)
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_late_agent_vm_cleanup',
        lambda _uid: {'vmName': vm_name, 'zone': zone, 'instanceId': '707'},
    )

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == [instance_url]


def test_agent_vm_account_cleanup_upgrades_pre_fence_late_record_after_user_purge(monkeypatch):
    uid = 'LegacyOwnerUid'
    vm_name = f'omi-agent-{uid[:12].lower()}'
    zone = 'us-central1-a'
    instance_url = f'https://compute.googleapis.com/compute/v1/projects/test-project/zones/{zone}/instances/{vm_name}'
    client = _ComputeClient(instances={vm_name: {'id': '808'}})
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: None)
    reads = iter(
        [
            {'vmName': vm_name, 'zone': zone},
            {'vmName': vm_name, 'zone': zone, 'expectedInstanceId': '808'},
        ]
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: next(reads))
    adopted = MagicMock(return_value=True)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'adopt_legacy_late_agent_vm_cleanup', adopted)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    adopted.assert_called_once_with(uid, vm_name, zone, '808')
    assert client.delete_calls == [instance_url]


def test_agent_vm_account_cleanup_deletes_legacy_vm_from_exact_firestore_token(monkeypatch):
    uid = 'legacy-owner'
    vm_name = 'omi-agent-legacy'
    zone = 'us-central1-a'
    instance_url = f'https://compute.googleapis.com/compute/v1/projects/test-project/zones/{zone}/instances/{vm_name}'
    vm = {'vmName': vm_name, 'zone': zone, 'authToken': 'legacy-token'}
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '606',
                'metadata': {'items': [{'key': 'auth-token', 'value': 'legacy-token'}]},
            }
        }
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: vm)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.post_calls == []
    assert client.delete_calls == [instance_url]


def test_agent_vm_account_cleanup_rejects_legacy_vm_with_foreign_owner_label(monkeypatch):
    uid = 'legacy-owner'
    vm_name = 'omi-agent-legacy'
    zone = 'us-central1-a'
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '606',
                'labels': {'omi-agent-owner': 'foreign-owner'},
                'metadata': {'items': [{'key': 'auth-token', 'value': 'legacy-token'}]},
            }
        }
    )
    vm = {'vmName': vm_name, 'zone': zone, 'authToken': 'legacy-token'}
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: vm)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    with pytest.raises(RuntimeError, match='owner identity is ambiguous'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == []


def test_agent_vm_account_cleanup_refuses_legacy_vm_with_mismatched_metadata_token(monkeypatch):
    uid = 'legacy-owner'
    vm_name = 'omi-agent-legacy'
    zone = 'us-central1-a'
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '606',
                'labels': {},
                'labelFingerprint': 'legacy-fingerprint',
                'metadata': {'items': [{'key': 'auth-token', 'value': 'foreign-token'}]},
            }
        }
    )
    vm = {'vmName': vm_name, 'zone': zone, 'authToken': 'legacy-token'}
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: vm)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    with pytest.raises(RuntimeError, match='auth-token identity is ambiguous'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.post_calls == []
    assert client.delete_calls == []


def test_agent_vm_account_cleanup_refuses_legacy_firestore_identity_race(monkeypatch):
    uid = 'legacy-owner'
    vm_name = 'omi-agent-legacy'
    zone = 'us-central1-a'
    initial_vm = {'vmName': vm_name, 'zone': zone, 'authToken': 'legacy-token'}
    raced_vm = {'vmName': vm_name, 'zone': zone, 'authToken': 'replacement-token'}
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '606',
                'labels': {},
                'labelFingerprint': 'legacy-fingerprint',
                'metadata': {'items': [{'key': 'auth-token', 'value': 'legacy-token'}]},
            }
        }
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    get_agent_vm = iter([initial_vm, raced_vm])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: next(get_agent_vm))
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    with pytest.raises(RuntimeError, match='identity changed during cleanup'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.post_calls == []
    assert client.delete_calls == []


def test_agent_vm_account_cleanup_refuses_legacy_provider_identity_race(monkeypatch):
    uid = 'legacy-owner'
    vm_name = 'omi-agent-legacy'
    zone = 'us-central1-a'
    vm = {'vmName': vm_name, 'zone': zone, 'authToken': 'legacy-token'}
    client = _ComputeClient(
        instances={
            vm_name: {
                'id': '606',
                'labels': {},
                'metadata': {'items': [{'key': 'auth-token', 'value': 'legacy-token'}]},
            }
        }
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: vm)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    original_get = client.get
    instance_reads = 0

    def raced_get(url, **kwargs):
        nonlocal instance_reads
        response = original_get(url, **kwargs)
        if url.endswith(f'/instances/{vm_name}'):
            instance_reads += 1
            if instance_reads == 1:
                client.instances[vm_name] = {
                    'id': '607',
                    'labels': {},
                    'metadata': {'items': [{'key': 'auth-token', 'value': 'legacy-token'}]},
                }
        return response

    monkeypatch.setattr(client, 'get', raced_get)

    with pytest.raises(RuntimeError, match='identity changed during cleanup'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.post_calls == []
    assert client.delete_calls == []


def test_agent_vm_account_cleanup_blocks_active_migration_lease(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal(missing_resource_ids=True, with_source_clone=True)
    client = _ComputeClient()
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {
            'vmName': journal['oldVmName'],
            'zone': journal['oldZone'],
            'reconcile': {
                'migration': {'migrationId': journal['migrationId']},
                'lease': {'owner': 'migration-worker', 'expiresAt': 2_000_000_001},
            },
        },
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)
    monkeypatch.setattr(agent_vm_account_cleanup.time, 'time', lambda: 2_000_000_000)

    with pytest.raises(RuntimeError, match='reconcile lease is active'):
        agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.get_calls == []
    assert client.delete_calls == []


def test_agent_vm_account_cleanup_adopts_expired_incomplete_resource_ids(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal(missing_resource_ids=True, with_source_clone=True)
    owner_label = agent_vm_account_cleanup._owner_disk_label(uid)
    client = _ComputeClient(
        instances={
            journal['candidateVmName']: {
                'id': '202',
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-predecessor': journal['oldInstanceId'],
                },
            }
        },
        disks={
            journal['stateDiskName']: {
                'id': '303',
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-role': 'state',
                    'omi-agent-owner': owner_label,
                },
                'users': [],
            },
            journal['sourceCloneDiskName']: {
                'id': '404',
                'labels': {
                    'omi-agent-migration': journal['migrationId'],
                    'omi-agent-role': 'source',
                    'omi-agent-owner': owner_label,
                },
                'users': [],
            },
        },
    )
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: None)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == [
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/instances/{journal['candidateVmName']}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/disks/{journal['stateDiskName']}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/disks/{journal['sourceCloneDiskName']}",
    ]


def test_agent_vm_account_cleanup_accepts_absent_incomplete_resources(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal(missing_resource_ids=True, with_source_clone=True)
    client = _ComputeClient()
    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_agent_vm', lambda _uid: None)
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == []


def test_agent_vm_account_cleanup_accepts_active_predecessor_before_migration_label_update(monkeypatch):
    uid = 'migration-owner'
    journal = _migration_journal()
    journal.pop('candidateInstanceId')
    journal.pop('stateDiskId')
    old_vm_name = journal['oldVmName']
    state_disk_name = journal['stateDiskName']
    old_instance = {
        'id': journal['oldInstanceId'],
        'labels': {'omi-agent-owner': agent_vm_account_cleanup._owner_disk_label(uid)},
        'metadata': {'items': [{'key': 'auth-token', 'value': 'active-token'}]},
        'disks': [
            {
                'source': f"projects/test-project/zones/{journal['oldZone']}/disks/{state_disk_name}",
                'autoDelete': True,
            }
        ],
    }
    client = _ComputeClient(
        instances={old_vm_name: old_instance},
        disks={
            state_disk_name: {
                'id': '303',
                'labels': {
                    'omi-agent-role': 'state',
                    'omi-agent-owner': agent_vm_account_cleanup._owner_disk_label(uid),
                },
                'users': [],
            }
        },
    )

    _configure_compute_cleanup(monkeypatch, client)
    monkeypatch.setattr(agent_vm_account_cleanup, 'read_agent_vm_migration_journals', lambda _uid: [journal])
    monkeypatch.setattr(
        agent_vm_account_cleanup.users_db,
        'get_agent_vm',
        lambda _uid: {
            'vmName': old_vm_name,
            'zone': journal['oldZone'],
            'instanceId': journal['oldInstanceId'],
            'authToken': 'active-token',
        },
    )
    monkeypatch.setattr(agent_vm_account_cleanup.users_db, 'get_late_agent_vm_cleanup', lambda _uid: None)

    agent_vm_account_cleanup._delete_agent_vm_for_account_impl(uid)

    assert client.delete_calls == [
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/instances/{old_vm_name}",
        f"https://compute.googleapis.com/compute/v1/projects/test-project/zones/{journal['oldZone']}/disks/{state_disk_name}",
    ]


def test_background_wipe_blocks_user_data_purge_when_agent_vm_cleanup_fails(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(
        account_deletion, 'delete_agent_vm_for_account', MagicMock(side_effect=RuntimeError('identity is ambiguous'))
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    delete_user_data = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', delete_user_data)

    assert account_deletion.background_wipe_user_data('uid1') is False

    delete_user_data.assert_not_called()
    account_deletion.auth.delete_account.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')


def test_start_account_deletion_preserves_order_and_enqueues_background_wipe(monkeypatch):
    calls = []
    monkeypatch.setattr(
        account_deletion.users_db,
        'set_user_deletion_feedback',
        lambda uid, reason, details: calls.append(('feedback', uid, reason, details)),
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_intent',
        lambda uid: calls.append(('wipe_intent', uid)) or _new_wipe_intent(),
    )
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: calls.append(('enqueue', executor, target, uid)),
    )

    result = account_deletion.start_account_deletion('uid1', reason='unused', reason_details='details')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    assert calls == [
        ('wipe_intent', 'uid1'),
        ('feedback', 'uid1', 'unused', 'details'),
        ('enqueue', account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1'),
    ]


def test_start_account_deletion_enqueues_cloud_task_when_enabled(monkeypatch):
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value=_new_wipe_intent())
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock(return_value=True))
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.start_account_deletion('uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    enqueue.assert_called_once_with('job-1')
    submit.assert_not_called()


def test_start_account_deletion_accepts_durable_intent_when_cloud_task_enqueue_fails(monkeypatch):
    """A queue NotFound must leave every irreversible boundary untouched.

    The persisted marker is deliberately retained as ``failed`` so the
    reconciler can recover delivery later; queue dispatch is an acceleration.
    """
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value=_new_wipe_intent())
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock(return_value=True))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    monkeypatch.setattr(
        account_deletion, 'enqueue_account_deletion_wipe', MagicMock(side_effect=Exception('tasks down'))
    )
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.start_account_deletion('uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    account_deletion.users_db.mark_user_deletion_wipe_started.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    account_deletion.auth.delete_account.assert_not_called()
    account_deletion.users_db.get_user_subscription.assert_not_called()
    submit.assert_not_called()


def test_start_account_deletion_tolerates_feedback_failure_and_missing_firebase_user(monkeypatch):
    """Feedback failures are tolerated, but marker and billing checks must succeed."""
    monkeypatch.setattr(
        account_deletion.users_db, 'set_user_deletion_feedback', MagicMock(side_effect=Exception('db down'))
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_intent',
        MagicMock(return_value=_new_wipe_intent()),
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_started',
        MagicMock(return_value=True),
    )
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock(side_effect=Exception('USER_NOT_FOUND')))
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    result = account_deletion.start_account_deletion('uid1', reason='reason')

    assert result['status'] == 'ok'
    account_deletion.stripe_utils.cancel_subscription.assert_not_called()
    submit.assert_called_once_with(
        account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1'
    )


def test_start_account_deletion_blocks_when_subscription_lookup_fails(monkeypatch):
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value=_new_wipe_intent())
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock(return_value=True))
    monkeypatch.setattr(
        account_deletion.users_db, 'get_user_subscription', MagicMock(side_effect=Exception('read down'))
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_billing_failed', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    result = account_deletion.start_account_deletion('uid1')

    assert result['status'] == 'ok'
    account_deletion.users_db.mark_user_deletion_billing_failed.assert_not_called()
    account_deletion.users_db.get_user_subscription.assert_not_called()
    account_deletion.auth.delete_account.assert_not_called()
    submit.assert_called_once()


def test_start_account_deletion_blocks_when_stripe_cancel_returns_none(monkeypatch):
    sub = types.SimpleNamespace(stripe_subscription_id='sub_123')
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value=_new_wipe_intent())
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock(return_value=True))
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=sub))
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_billing_failed', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    result = account_deletion.start_account_deletion('uid1')

    assert result['status'] == 'ok'
    account_deletion.users_db.mark_user_deletion_billing_failed.assert_not_called()
    account_deletion.users_db.get_user_subscription.assert_not_called()
    account_deletion.stripe_utils.cancel_subscription.assert_not_called()
    account_deletion.auth.delete_account.assert_not_called()
    submit.assert_called_once()


def test_start_account_deletion_raises_when_marker_persist_fails(monkeypatch):
    """If the durable intent cannot be written, the deletion must NOT proceed."""
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(side_effect=Exception('firestore down'))
    )
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    feedback = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'set_user_deletion_feedback', feedback)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    try:
        account_deletion.start_account_deletion('uid1', reason='unused')
    except Exception as exc:
        assert 'intent' in str(exc).lower() or 'deletion-wipe' in str(exc).lower()
    else:
        raise AssertionError('expected intent failure to raise')

    # Firebase user must NOT be deleted if the intent failed.
    account_deletion.auth.delete_account.assert_not_called()
    feedback.assert_not_called()
    submit.assert_not_called()


def test_start_account_deletion_raises_when_atomic_pending_intent_fails_before_auth(monkeypatch):
    """Do not enqueue or report success unless the atomic pending marker exists."""
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(side_effect=Exception('db down'))
    )
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    try:
        account_deletion.start_account_deletion('uid1')
    except Exception as exc:
        assert 'intent' in str(exc).lower()
    else:
        raise AssertionError('expected pending marker failure to raise')

    account_deletion.auth.delete_account.assert_not_called()
    submit.assert_not_called()


def test_start_account_deletion_never_calls_firebase_in_the_request_thread(monkeypatch):
    """Firebase deletion belongs only to the claimed durable worker."""
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_intent', MagicMock(return_value=_new_wipe_intent())
    )
    mark_started = MagicMock(return_value=True)
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', mark_started)
    cancel_wipe = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'cancel_user_deletion_wipe', cancel_wipe)
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock(side_effect=Exception('permission denied')))
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    result = account_deletion.start_account_deletion('uid1')

    assert result['status'] == 'ok'
    submit.assert_called_once()
    account_deletion.users_db.mark_user_deletion_wipe_intent.assert_called_once_with('uid1')
    cancel_wipe.assert_not_called()
    mark_started.assert_not_called()
    account_deletion.auth.delete_account.assert_not_called()


def test_start_account_deletion_writes_pending_authority_before_dispatch(monkeypatch):
    """The durable marker exists before the queue acceleration attempt."""
    call_log = []
    intent_mock = MagicMock(side_effect=lambda uid: call_log.append('intent') or _new_wipe_intent())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_intent', intent_mock)
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        MagicMock(side_effect=lambda *_args: call_log.append('enqueue')),
    )
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)

    account_deletion.start_account_deletion('uid1')

    assert call_log == ['intent', 'enqueue']
    intent_mock.assert_called_once_with('uid1')


def test_start_account_deletion_joins_existing_wipe_without_dispatch(monkeypatch):
    """A retry joins the durable authority without resetting or re-enqueueing it."""
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_intent',
        MagicMock(return_value={'wipe_job_id': 'job-running', 'dispatch_claimed': False}),
    )
    mark_started = MagicMock()
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', mark_started)
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_deletion_wipe', enqueue)

    result = account_deletion.start_account_deletion('uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    mark_started.assert_not_called()
    enqueue.assert_not_called()


def test_start_account_deletion_does_not_dispatch_when_atomic_claim_loses(monkeypatch):
    """Only the atomic intent transaction winner dispatches."""
    monkeypatch.setattr(
        account_deletion.users_db,
        'mark_user_deletion_wipe_intent',
        MagicMock(return_value={'wipe_job_id': 'job-new', 'dispatch_claimed': False}),
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_started', MagicMock(return_value=False))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_deletion_wipe', enqueue)

    result = account_deletion.start_account_deletion('uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    enqueue.assert_not_called()


def test_background_wipe_user_data_preserves_order(monkeypatch):
    calls = []
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_running', lambda uid: calls.append(('running', uid))
    )
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', lambda uid: None)
    monkeypatch.setattr(account_deletion, 'delete_agent_vm_for_account', lambda uid: calls.append(('agent_vm', uid)))
    monkeypatch.setattr(account_deletion, 'delete_account_credentials', lambda uid: calls.append(('credentials', uid)))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', lambda uid: calls.append(('auth', uid)))
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', lambda uid: calls.append(('twilio', uid)))
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        lambda uid: calls.append(('purge', uid))
        or {
            'required_failures': [],
            'best_effort_failures': [],
            'vectors_deleted': 0,
            'recordings_deleted': 0,
        },
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'delete_user_data',
        lambda uid: calls.append(('firestore', uid)) or {'status': 'ok'},
    )
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_completed', lambda uid: calls.append(('wipe_done', uid))
    )

    account_deletion.background_wipe_user_data('uid1')

    assert calls == [
        ('running', 'uid1'),
        ('agent_vm', 'uid1'),
        ('credentials', 'uid1'),
        ('auth', 'uid1'),
        ('twilio', 'uid1'),
        ('purge', 'uid1'),
        ('firestore', 'uid1'),
        ('wipe_done', 'uid1'),
    ]


def test_background_wipe_defers_completion_for_late_vm_cleanup(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(
            return_value={
                'required_failures': [],
                'best_effort_failures': [],
                'vectors_deleted': 0,
                'recordings_deleted': 0,
            }
        ),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock(return_value={'status': 'ok'}))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock(return_value=False))

    assert account_deletion.background_wipe_user_data('uid1') is False


def _stub_wipe_steps_after_billing(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(
            return_value={
                'required_failures': [],
                'best_effort_failures': [],
                'vectors_deleted': 0,
                'recordings_deleted': 0,
            }
        ),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock(return_value={'status': 'ok'}))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock(return_value=True))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_billing_failed', MagicMock())
    monkeypatch.setattr(account_deletion.time, 'sleep', lambda *_: None)


def test_background_wipe_proceeds_when_subscription_is_already_canceled(monkeypatch):
    """#11289: Stripe rejects cancel_at_period_end on a canceled subscription.

    The billing step owns the goal state (not billing), so an already-canceled subscription
    must satisfy it. Otherwise the wipe fails, the reconciler re-enqueues it every 5 minutes,
    and the user's data is never deleted.
    """
    _stub_wipe_steps_after_billing(monkeypatch)
    monkeypatch.setattr(
        account_deletion.users_db,
        'get_user_subscription',
        MagicMock(return_value=SimpleNamespace(stripe_subscription_id='sub_123')),
    )
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.stripe_utils, 'is_subscription_terminal', MagicMock(return_value=True))

    assert account_deletion.background_wipe_user_data('uid1') is True

    account_deletion.stripe_utils.is_subscription_terminal.assert_called_once_with('sub_123')
    account_deletion.users_db.delete_user_data.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_billing_failed.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_not_called()


def test_background_wipe_still_fails_when_subscription_is_not_terminal(monkeypatch):
    """A cancel that failed while the subscription can still bill stays a hard failure."""
    _stub_wipe_steps_after_billing(monkeypatch)
    monkeypatch.setattr(
        account_deletion.users_db,
        'get_user_subscription',
        MagicMock(return_value=SimpleNamespace(stripe_subscription_id='sub_123')),
    )
    monkeypatch.setattr(account_deletion.stripe_utils, 'cancel_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.stripe_utils, 'is_subscription_terminal', MagicMock(return_value=False))

    assert account_deletion.background_wipe_user_data('uid1') is False

    account_deletion.users_db.delete_user_data.assert_not_called()
    account_deletion.auth.delete_account.assert_not_called()
    account_deletion.users_db.mark_user_deletion_billing_failed.assert_called_once()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')


def test_gce_project_uses_deployed_google_cloud_project(monkeypatch):
    for name in ('GCE_PROJECT_ID', 'FIREBASE_PROJECT_ID', 'GCP_PROJECT_ID'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'deployed-project')

    assert agent_vm_account_cleanup._gce_project_id() == 'deployed-project'


def test_background_wipe_user_data_swallows_failures(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock(side_effect=Exception('twilio down')))
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    account_deletion.background_wipe_user_data('uid1')

    account_deletion.purge_derived_user_data.assert_not_called()
    account_deletion.users_db.delete_user_data.assert_not_called()
    # On failure, mark as failed (not completed) so a reconciliation worker can retry.
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_not_called()


def test_background_wipe_fails_closed_when_running_marker_persist_fails(monkeypatch):
    """Without a running marker, a second worker could not be fenced safely."""
    monkeypatch.setattr(
        account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock(side_effect=Exception('firestore down'))
    )
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(account_deletion, 'purge_derived_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    assert account_deletion.background_wipe_user_data('uid1') is False

    account_deletion.delete_user_caller_ids.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')


def test_purge_derived_user_data_isolates_backends_and_reloads_conversation_ids(monkeypatch):
    calls = []
    conversation_calls = iter([['c1'], ['c2']])
    monkeypatch.setattr(
        account_deletion,
        'get_conversation_ids',
        lambda uid: calls.append(('get_conversations', uid)) or next(conversation_calls),
    )
    monkeypatch.setattr(account_deletion, 'get_memory_ids', lambda uid: calls.append(('get_memories', uid)) or ['m1'])
    monkeypatch.setattr(
        account_deletion, 'get_action_item_ids', lambda uid: calls.append(('get_actions', uid)) or ['a1']
    )
    monkeypatch.setattr(
        account_deletion, 'get_screen_activity_ids', lambda uid: calls.append(('get_screen', uid)) or ['s1']
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_conversation_vectors_batch',
        lambda uid, ids: calls.append(('delete_conversation_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_transcript_chunk_vectors_batch',
        lambda uid, ids, **kwargs: calls.append(('delete_transcript_vectors', uid, ids, kwargs)) or 2,
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_memory_vectors_batch',
        lambda uid, ids: calls.append(('delete_memory_vectors', uid, ids)) or 1,
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_action_item_vectors_batch',
        lambda uid, ids: calls.append(('delete_action_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion,
        'delete_screen_activity_vectors',
        lambda uid, ids: calls.append(('delete_screen_vectors', uid, ids)),
    )
    monkeypatch.setattr(
        account_deletion, 'delete_all_conversation_recordings', lambda uid: calls.append(('recordings', uid)) or 3
    )
    monkeypatch.setattr(
        account_deletion,
        'purge_canonical_derived_user_data',
        MagicMock(return_value={'vector_ids': ['canonical-1', 'canonical-2']}),
    )

    result = account_deletion.purge_derived_user_data('uid1')

    assert calls == [
        ('get_conversations', 'uid1'),
        ('delete_conversation_vectors', 'uid1', ['c1']),
        ('get_conversations', 'uid1'),
        ('delete_transcript_vectors', 'uid1', ['c2'], {'raise_on_failure': True}),
        ('get_memories', 'uid1'),
        ('delete_memory_vectors', 'uid1', ['m1']),
        ('get_actions', 'uid1'),
        ('delete_action_vectors', 'uid1', ['a1']),
        ('get_screen', 'uid1'),
        ('delete_screen_vectors', 'uid1', ['s1']),
        ('recordings', 'uid1'),
    ]
    assert result == {
        'required_failures': [],
        'best_effort_failures': [],
        'vectors_deleted': 8,
        'recordings_deleted': 3,
    }


def test_purge_derived_user_data_continues_after_each_failure(monkeypatch):
    monkeypatch.setattr(account_deletion, 'get_conversation_ids', MagicMock(side_effect=Exception('read down')))
    monkeypatch.setattr(account_deletion, 'delete_conversation_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_transcript_chunk_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'get_memory_ids', MagicMock(return_value=['m1']))
    monkeypatch.setattr(
        account_deletion, 'delete_memory_vectors_batch', MagicMock(side_effect=Exception('pinecone down'))
    )
    monkeypatch.setattr(account_deletion, 'get_action_item_ids', MagicMock(return_value=['a1']))
    monkeypatch.setattr(account_deletion, 'delete_action_item_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'get_screen_activity_ids', MagicMock(return_value=['s1']))
    monkeypatch.setattr(account_deletion, 'delete_screen_activity_vectors', MagicMock())
    monkeypatch.setattr(
        account_deletion, 'delete_all_conversation_recordings', MagicMock(side_effect=Exception('gcs down'))
    )
    monkeypatch.setattr(
        account_deletion, 'purge_canonical_derived_user_data', MagicMock(side_effect=Exception('canonical down'))
    )

    result = account_deletion.purge_derived_user_data('uid1')

    assert account_deletion.get_conversation_ids.call_count == 2
    account_deletion.delete_conversation_vectors_batch.assert_not_called()
    account_deletion.delete_transcript_chunk_vectors_batch.assert_not_called()
    account_deletion.delete_memory_vectors_batch.assert_called_once_with('uid1', ['m1'])
    account_deletion.delete_action_item_vectors_batch.assert_called_once_with('uid1', ['a1'])
    account_deletion.delete_screen_activity_vectors.assert_called_once_with('uid1', ['s1'])
    account_deletion.delete_all_conversation_recordings.assert_called_once_with('uid1')
    account_deletion.purge_canonical_derived_user_data.assert_called_once_with('uid1')
    assert [failure['operation'] for failure in result['required_failures']] == [
        'conversation_vectors',
        'transcript_chunk_vectors',
        'memory_vectors',
        'conversation_recordings',
        'canonical_derived_data',
    ]
    assert result['best_effort_failures'] == []


def test_purge_derived_user_data_fails_required_vectors_when_index_missing(monkeypatch):
    monkeypatch.setattr(account_deletion.vector_db, 'index', None)
    monkeypatch.setattr(account_deletion, 'get_conversation_ids', MagicMock(return_value=['c1']))
    monkeypatch.setattr(account_deletion, 'get_memory_ids', MagicMock(return_value=['m1']))
    monkeypatch.setattr(account_deletion, 'get_action_item_ids', MagicMock(return_value=['a1']))
    monkeypatch.setattr(account_deletion, 'get_screen_activity_ids', MagicMock(return_value=['s1']))
    monkeypatch.setattr(account_deletion, 'delete_conversation_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_transcript_chunk_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_memory_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_action_item_vectors_batch', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_screen_activity_vectors', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_all_conversation_recordings', MagicMock())
    monkeypatch.setattr(account_deletion, 'purge_canonical_derived_user_data', MagicMock())

    result = account_deletion.purge_derived_user_data('uid1')

    assert [failure['operation'] for failure in result['required_failures']] == [
        'conversation_vectors',
        'transcript_chunk_vectors',
        'memory_vectors',
        'action_item_vectors',
        'screen_activity_vectors',
    ]
    account_deletion.delete_conversation_vectors_batch.assert_not_called()
    account_deletion.delete_transcript_chunk_vectors_batch.assert_not_called()
    account_deletion.delete_memory_vectors_batch.assert_not_called()
    account_deletion.delete_action_item_vectors_batch.assert_not_called()
    account_deletion.delete_screen_activity_vectors.assert_not_called()


def test_background_wipe_user_data_does_not_complete_when_required_derived_purge_fails(monkeypatch):
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(return_value={'required_failures': [{'operation': 'memory_vectors', 'error': 'down'}]}),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    account_deletion.background_wipe_user_data('uid1')

    account_deletion.users_db.delete_user_data.assert_not_called()
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_not_called()


def test_background_wipe_user_data_does_not_complete_when_firestore_wipe_returns_error(monkeypatch):
    """A normal structured wipe failure is terminally unsafe, not success."""
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(return_value={'required_failures': [], 'best_effort_failures': []}),
    )
    monkeypatch.setattr(
        account_deletion.users_db,
        'delete_user_data',
        MagicMock(return_value={'status': 'error', 'message': 'root user document missing'}),
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    assert account_deletion.background_wipe_user_data('uid1') is False

    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    account_deletion.users_db.mark_user_deletion_wipe_completed.assert_not_called()


def test_background_wipe_emits_bounded_completion_telemetry(monkeypatch):
    emit = MagicMock()
    monotonic = MagicMock(side_effect=[100.0, 102.3456])
    monkeypatch.setattr(account_deletion.time, 'monotonic', monotonic)
    monkeypatch.setattr(account_deletion, 'emit_posthog_event', emit)
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(
            return_value={
                'required_failures': [],
                'best_effort_failures': [],
                'vectors_deleted': 7,
                'recordings_deleted': 2,
            }
        ),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock(return_value={'status': 'ok'}))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    assert account_deletion.background_wipe_user_data('uid1') is True

    emit.assert_called_once_with(
        'omi-service:account-deletion',
        'Account Deletion Wipe Completed',
        {
            'duration_seconds': 2.346,
            'vectors_deleted': 7,
            'recordings_deleted': 2,
            'required_failure_count': 0,
            'best_effort_failure_count': 0,
            'failed_operations': [],
            '$process_person_profile': False,
        },
    )
    props = emit.call_args.args[2]
    assert 'uid' not in props
    assert 'uid1' not in str(props)
    assert emit.call_args.args[0] != 'uid1'


def test_deletion_telemetry_never_uses_deleted_uid_as_distinct_id(monkeypatch):
    """Account-deletion completion must not re-identify the wiped Firebase UID in PostHog."""
    emit = MagicMock()
    monkeypatch.setattr(account_deletion, 'emit_posthog_event', emit)
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(return_value={'required_failures': [], 'best_effort_failures': []}),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock(return_value={'status': 'ok'}))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_completed', MagicMock())

    deleted_uid = 'firebase-user-to-wipe'
    assert account_deletion.background_wipe_user_data(deleted_uid) is True

    distinct_id, event, properties = emit.call_args.args
    assert distinct_id == 'omi-service:account-deletion'
    assert distinct_id != deleted_uid
    assert event == 'Account Deletion Wipe Completed'
    assert properties.get('$process_person_profile') is False
    assert deleted_uid not in str(properties)
    assert 'uid' not in properties
    assert 'user_id' not in properties


def test_background_wipe_emits_failed_operations_and_attempt_context(monkeypatch):
    emit = MagicMock()
    monkeypatch.setattr(account_deletion, 'emit_posthog_event', emit)
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_running', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'get_user_subscription', MagicMock(return_value=None))
    monkeypatch.setattr(account_deletion.auth, 'delete_account', MagicMock())
    monkeypatch.setattr(account_deletion, 'delete_user_caller_ids', MagicMock())
    monkeypatch.setattr(
        account_deletion,
        'purge_derived_user_data',
        MagicMock(
            return_value={
                'required_failures': [{'operation': 'memory_vectors', 'error': 'secret provider body'}],
                'best_effort_failures': [],
                'vectors_deleted': 0,
                'recordings_deleted': 0,
            }
        ),
    )
    monkeypatch.setattr(account_deletion.users_db, 'delete_user_data', MagicMock())
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())

    assert account_deletion.background_wipe_user_data('uid1', retry_count=2, terminal=True) is False

    emit.assert_called_once_with(
        'omi-service:account-deletion',
        'Account Deletion Wipe Failed',
        {
            'failed_operations': ['memory_vectors'],
            'retry_count': 2,
            'terminal': True,
            '$process_person_profile': False,
        },
    )
    assert 'secret provider body' not in str(emit.call_args)
    assert emit.call_args.args[0] != 'uid1'
    assert 'uid1' not in str(emit.call_args.args[2])


def test_reconcile_pending_deletion_wipes_re_enqueues(monkeypatch):
    pending = [
        {'uid': 'uid1', 'wipe_status': 'pending', 'wipe_job_id': 'job-1'},
        {'uid': 'uid2', 'wipe_status': 'failed', 'wipe_job_id': 'job-2'},
    ]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append((executor, target, uid)),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 2, 'skipped': 0}
    assert len(enqueued) == 2
    assert enqueued[0] == (account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid1')
    assert enqueued[1] == (account_deletion.cleanup_executor, account_deletion.background_wipe_user_data, 'uid2')


def test_reconcile_emits_failure_when_stale_running_wipe_is_reclaimed(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'running', 'wipe_job_id': 'job-1'}]
    emit = MagicMock()
    monkeypatch.setattr(account_deletion, 'emit_posthog_event', emit)
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion, 'submit_with_context', MagicMock())

    assert account_deletion.reconcile_pending_deletion_wipes() == {'requeued': 1, 'skipped': 0}

    emit.assert_called_once_with(
        'omi-service:account-deletion',
        'Account Deletion Wipe Failed',
        {
            'failed_operations': ['stale_running_wipe'],
            'retry_count': 0,
            'terminal': False,
            '$process_person_profile': False,
        },
    )
    assert emit.call_args.args[0] != 'uid1'


def test_reconcile_pending_deletion_wipes_enqueues_cloud_tasks(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'failed', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    enqueue.assert_called_once_with('job-1')
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_backfills_missing_job_id(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'pending'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    ensure = MagicMock(return_value='job-recovered')
    monkeypatch.setattr(account_deletion.users_db, 'ensure_deletion_wipe_job_id', ensure)
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    ensure.assert_called_once_with('uid1')
    enqueue.assert_called_once_with('job-recovered')
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_marks_failed_when_job_id_recovery_fails(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'pending'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(
        account_deletion.users_db,
        'ensure_deletion_wipe_job_id',
        MagicMock(side_effect=Exception('job id backfill down')),
    )
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    enqueue = MagicMock()
    monkeypatch.setattr(account_deletion, 'enqueue_account_deletion_wipe', enqueue)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    enqueue.assert_not_called()
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_skips_cloud_enqueue_failure(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_status': 'failed', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion, 'is_account_deletion_dispatch_enabled', MagicMock(return_value=True))
    monkeypatch.setattr(
        account_deletion, 'enqueue_account_deletion_wipe', MagicMock(side_effect=Exception('tasks down'))
    )
    monkeypatch.setattr(account_deletion.users_db, 'mark_user_deletion_wipe_failed', MagicMock())
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    account_deletion.users_db.mark_user_deletion_wipe_failed.assert_called_once_with('uid1')
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_skips_already_claimed(monkeypatch):
    """Wipes already claimed by another worker are skipped (no double-enqueue)."""
    pending = [
        {'uid': 'uid1', 'wipe_status': 'pending', 'wipe_job_id': 'job-1'},
        {'uid': 'uid2', 'wipe_status': 'failed', 'wipe_job_id': 'job-2'},
    ]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    # uid1 claimable, uid2 already claimed by another worker.
    monkeypatch.setattr(
        account_deletion.users_db,
        'claim_deletion_wipe',
        lambda uid: uid if uid == 'uid1' else None,
    )
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append(uid),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 1}
    assert enqueued == ['uid1']


def test_reconcile_pending_deletion_wipes_skips_claim_exception(monkeypatch):
    """Claim exceptions are logged and skipped, not propagated."""
    pending = [{'uid': 'uid1', 'wipe_status': 'pending'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(
        account_deletion.users_db,
        'claim_deletion_wipe',
        MagicMock(side_effect=Exception('txn conflict')),
    )
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 1}
    submit.assert_not_called()


def test_reconcile_pending_deletion_wipes_skips_missing_uid(monkeypatch):
    pending = [{'uid': 'uid1', 'wipe_job_id': 'job-1'}, {'wipe_status': 'pending'}]  # second record has no uid
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append(uid),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 1}
    assert enqueued == ['uid1']


def test_reconcile_pending_deletion_wipes_handles_query_error(monkeypatch):
    monkeypatch.setattr(
        account_deletion.users_db,
        'get_pending_deletion_wipes',
        MagicMock(side_effect=Exception('firestore down')),
    )
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 0, 'skipped': 0, 'error': 1}
    submit.assert_not_called()


def test_reconcile_recovers_deleting_auth_when_user_gone(monkeypatch):
    """Stale 'deleting_auth' record with Firebase user deleted → recovered."""
    pending = [{'uid': 'uid1', 'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', lambda uid: uid)
    monkeypatch.setattr(account_deletion.auth, 'get_user', MagicMock(side_effect=Exception('USER_NOT_FOUND')))
    enqueued = []
    monkeypatch.setattr(
        account_deletion,
        'submit_with_context',
        lambda executor, target, uid: enqueued.append(uid),
    )

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    assert enqueued == ['uid1']


def test_reconcile_recovers_deleting_auth_when_user_exists(monkeypatch):
    """Legacy durable intent is recovered even while Firebase auth still exists."""
    pending = [{'uid': 'uid1', 'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    # get_user succeeds → user exists
    monkeypatch.setattr(account_deletion.auth, 'get_user', MagicMock(return_value=object()))
    claim = MagicMock(return_value='uid1')
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', claim)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    claim.assert_called_once_with('uid1')
    submit.assert_called_once()


def test_reconcile_does_not_query_auth_for_legacy_durable_intent(monkeypatch):
    """Recovery authority is the marker, not an indeterminate Auth lookup."""
    pending = [{'uid': 'uid1', 'wipe_status': 'deleting_auth', 'wipe_job_id': 'job-1'}]
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda limit=100: pending)
    # Indeterminate error — not USER_NOT_FOUND
    monkeypatch.setattr(account_deletion.auth, 'get_user', MagicMock(side_effect=Exception('internal error')))
    claim = MagicMock(return_value='uid1')
    monkeypatch.setattr(account_deletion.users_db, 'claim_deletion_wipe', claim)
    submit = MagicMock()
    monkeypatch.setattr(account_deletion, 'submit_with_context', submit)

    result = account_deletion.reconcile_pending_deletion_wipes()

    assert result == {'requeued': 1, 'skipped': 0}
    claim.assert_called_once_with('uid1')
    submit.assert_called_once()
    account_deletion.auth.get_user.assert_not_called()
