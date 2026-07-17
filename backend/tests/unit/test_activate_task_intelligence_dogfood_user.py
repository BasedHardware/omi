from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/activate_task_intelligence_dogfood_user.py'


def load_script():
    spec = importlib.util.spec_from_file_location('activate_task_intelligence_dogfood_user', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script():
    return load_script()


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def get(self, transaction=None, timeout=None):
        del transaction
        self._db.read_timeouts.append(timeout)
        return _Snapshot(self._db.docs.get(self._path))


class _Transaction:
    def __init__(self, db):
        self._db = db

    def set(self, ref, payload):
        self._db.writes.append((ref._path, payload))
        self._db.docs[ref._path] = dict(payload)


class _Db:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.read_timeouts = []
        self.writes = []

    def document(self, path):
        return _Document(self, path)

    def transaction(self):
        return _Transaction(self)


class _Firestore:
    @staticmethod
    def transactional(function):
        return function


class _HttpResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        del exc_type
        del exc_value
        del traceback
        return False

    def read(self):
        return json.dumps(self._payload).encode('utf-8')


def test_missing_control_plans_explicit_read_at_default_generation(script):
    db = _Db()

    current = script.read_control(db, uid=script.TASK_INTELLIGENCE_DOGFOOD_UID)
    plan = script.build_activation_plan(script.TASK_INTELLIGENCE_DOGFOOD_UID, current)

    assert plan.current_control == {'workflow_mode': 'off', 'account_generation': 0}
    assert plan.target_control == {'workflow_mode': 'read', 'account_generation': 0}
    assert plan.canonical_memory_whitelisted is True
    assert db.read_timeouts == [script.DEFAULT_FIRESTORE_RPC_TIMEOUT_SECONDS]


def test_activation_preserves_existing_generation_and_is_idempotent(monkeypatch):
    script = load_script()
    monkeypatch.setattr(script, 'firestore', _Firestore())
    path = script.control_path(script.TASK_INTELLIGENCE_DOGFOOD_UID)
    db = _Db({path: {'workflow_mode': 'off', 'account_generation': 7}})

    assert script.apply_activation(
        db,
        uid=script.TASK_INTELLIGENCE_DOGFOOD_UID,
        expected_account_generation=7,
    )
    assert db.docs[path] == {'workflow_mode': 'read', 'account_generation': 7}
    assert not script.apply_activation(
        db,
        uid=script.TASK_INTELLIGENCE_DOGFOOD_UID,
        expected_account_generation=7,
    )
    assert len(db.writes) == 1


def test_activation_rejects_stale_generation_without_a_write(monkeypatch):
    script = load_script()
    monkeypatch.setattr(script, 'firestore', _Firestore())
    path = script.control_path(script.TASK_INTELLIGENCE_DOGFOOD_UID)
    db = _Db({path: {'workflow_mode': 'off', 'account_generation': 3}})

    with pytest.raises(RuntimeError, match='account generation changed'):
        script.apply_activation(
            db,
            uid=script.TASK_INTELLIGENCE_DOGFOOD_UID,
            expected_account_generation=2,
        )

    assert db.writes == []
    assert db.docs[path] == {'workflow_mode': 'off', 'account_generation': 3}


def test_tool_rejects_any_non_dogfood_uid():
    script = load_script()

    with pytest.raises(ValueError, match='restricted'):
        script.build_activation_plan('another-user', script.TaskWorkflowControl())


def test_gcloud_user_transport_uses_current_document_precondition_and_never_reports_token():
    script = load_script()
    requests = []
    current_document = {
        'fields': {
            'workflow_mode': {'stringValue': 'off'},
            'account_generation': {'integerValue': '7'},
        },
        'updateTime': '2026-07-12T00:00:00.000000Z',
    }

    def http_open(request, timeout):
        requests.append((request, timeout))
        return _HttpResponse(current_document)

    snapshot = script.read_control_with_gcloud_user_token(
        firestore_project='based-hardware',
        uid=script.TASK_INTELLIGENCE_DOGFOOD_UID,
        rpc_timeout_seconds=5,
        http_open=http_open,
        access_token='short-lived-token',
    )
    assert snapshot.control == script.TaskWorkflowControl(workflow_mode='off', account_generation=7)

    assert script.apply_activation_with_gcloud_user_token(
        firestore_project='based-hardware',
        uid=script.TASK_INTELLIGENCE_DOGFOOD_UID,
        expected_account_generation=7,
        current=snapshot,
        rpc_timeout_seconds=5,
        http_open=http_open,
        access_token='short-lived-token',
    )

    patch_request, timeout = requests[-1]
    assert patch_request.method == 'PATCH'
    assert timeout == 5
    assert 'currentDocument.updateTime=2026-07-12T00%3A00%3A00.000000Z' in patch_request.full_url
    assert b'"workflow_mode": {"stringValue": "read"}' in patch_request.data
    assert b'"account_generation": {"integerValue": "7"}' in patch_request.data
    assert b'chat_first_ui_enabled' not in patch_request.data
    assert b'short-lived-token' not in patch_request.data
