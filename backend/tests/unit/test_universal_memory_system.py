"""Universal memory authority and apply-state provisioning tests."""

from __future__ import annotations

from copy import deepcopy

import pytest

from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from utils.memory.memory_system import (
    MemorySystem,
    ensure_canonical_apply_control_state,
    resolve_memory_system,
)


class _Snapshot:
    def __init__(self, payload=None, *, exists=True):
        self._payload = deepcopy(payload)
        self.exists = exists

    def to_dict(self):
        return deepcopy(self._payload)


class _Ref:
    def __init__(self, db, path):
        self.db = db
        self.path = path

    def get(self):
        if self.path not in self.db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self.db.docs[self.path])

    def create(self, payload):
        if self.path in self.db.docs:
            from google.api_core.exceptions import AlreadyExists

            raise AlreadyExists("exists")
        self.db.docs[self.path] = deepcopy(payload)

    def set(self, payload, **_kwargs):
        self.db.docs[self.path] = deepcopy(payload)


class _Db:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def document(self, path):
        return _Ref(self, path)


class _UnreadableRef:
    def get(self):
        raise RuntimeError("transport unavailable")


class _UnreadableDb:
    def document(self, _path):
        return _UnreadableRef()


def test_arbitrary_authenticated_uids_are_canonical_without_a_code_list():
    assert resolve_memory_system("uid-never-seen") == MemorySystem.CANONICAL
    assert resolve_memory_system("uid-another-account") == MemorySystem.CANONICAL


@pytest.mark.parametrize("uid", ["", None, 42])
def test_invalid_identity_is_not_an_entitled_account(uid):
    assert resolve_memory_system(uid) == MemorySystem.LEGACY


def test_missing_apply_state_is_self_provisioned():
    db = _Db()
    control = ensure_canonical_apply_control_state("uid-arbitrary", db_client=db)
    assert control.uid == "uid-arbitrary"
    path = MemoryCollections(uid="uid-arbitrary").memory_apply_control_state
    assert MemoryControlState.model_validate(db.docs[path]) == control


def test_apply_state_transport_failure_is_classified_as_unavailable():
    with pytest.raises(RuntimeError, match="apply control state is unreadable"):
        ensure_canonical_apply_control_state("uid-unavailable", db_client=_UnreadableDb())


def test_malformed_apply_state_fails_closed_without_overwrite():
    uid = "uid-malformed"
    path = MemoryCollections(uid=uid).memory_apply_control_state
    db = _Db({path: {"uid": uid, "head_commit_id": ""}})
    with pytest.raises(RuntimeError, match="malformed"):
        ensure_canonical_apply_control_state(uid, db_client=db)
    assert db.docs[path]["head_commit_id"] == ""


def test_cross_uid_apply_state_fails_closed():
    uid = "uid-owner"
    path = MemoryCollections(uid=uid).memory_apply_control_state
    db = _Db(
        {
            path: MemoryControlState(
                uid="uid-other", head_commit_id="head0", account_generation=1, source_generation=1
            ).model_dump(mode="json")
        }
    )
    with pytest.raises(RuntimeError, match="uid mismatch"):
        ensure_canonical_apply_control_state(uid, db_client=db)
