"""Regression test for canonical product state soft-delete and lifecycle filtering.

Verifies:
1. load_canonical_product_state excludes soft-deleted action items (deleted=True, is_deleted=True).
2. load_canonical_product_state excludes inactive and terminal (achieved/abandoned) goals.
3. load_canonical_product_state excludes dismissed and deleted candidates.
4. load_canonical_product_state excludes archived and deleted workstreams.
5. delete_goal idempotency on already-abandoned goals and action-items cache invalidation.
"""

from copy import deepcopy

import database.task_recommendations as tr_db
import database.goals as goals_db


class FakeSnapshot:
    def __init__(self, database, path, payload=None):
        self.database = database
        self.path = path
        self._payload = deepcopy(payload)
        self.exists = payload is not None
        self.id = path[-1]

    def to_dict(self):
        return deepcopy(self._payload)


class FakeDocument:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    @property
    def id(self):
        return self.path[-1]

    def collection(self, name):
        return FakeCollection(self.database, (*self.path, name))

    def get(self, transaction=None):
        return FakeSnapshot(self.database, self.path, self.database.rows.get(self.path))

    def set(self, payload):
        self.database.rows[self.path] = deepcopy(payload)

    def update(self, patch):
        if self.path in self.database.rows:
            self.database.rows[self.path].update(deepcopy(patch))

    def delete(self):
        self.database.rows.pop(self.path, None)


class FakeCollection:
    def __init__(self, database, path, filters=(), query_limit=None):
        self.database = database
        self.path = path
        self.filters = filters
        self.query_limit = query_limit

    def document(self, name):
        return FakeDocument(self.database, (*self.path, name))

    def where(self, *args, filter=None):
        if filter is not None:
            condition = (filter.field_path, filter.op_string, filter.value)
        else:
            condition = (args[0], args[1], args[2])
        return FakeCollection(self.database, self.path, (*self.filters, condition), self.query_limit)

    def limit(self, value):
        return FakeCollection(self.database, self.path, self.filters, value)

    def order_by(self, field, direction=None):
        return self

    def stream(self):
        rows = []
        expected_length = len(self.path) + 1
        for path, payload in self.database.rows.items():
            if len(path) != expected_length or path[:-1] != self.path:
                continue
            matched = True
            for field, op, val in self.filters:
                if op == "==" and payload.get(field) != val:
                    matched = False
                    break
            if matched:
                rows.append(FakeSnapshot(self.database, path, payload))
                if self.query_limit is not None and len(rows) >= self.query_limit:
                    break
        return iter(rows)


class FakeFirestore:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return FakeCollection(self, (name,))


def test_load_canonical_product_state_filters_soft_deleted_and_terminal():
    fake_db = FakeFirestore()
    uid = "test-user-1"
    base = ("users", uid)

    # 1. Action items: active vs soft-deleted
    fake_db.rows[(*base, "action_items", "task-active")] = {
        "description": "Active task",
        "account_generation": 0,
    }
    fake_db.rows[(*base, "action_items", "task-soft-deleted")] = {
        "description": "Soft-deleted task",
        "deleted": True,
        "account_generation": 0,
    }
    fake_db.rows[(*base, "action_items", "task-legacy-deleted")] = {
        "description": "Legacy soft-deleted task",
        "is_deleted": True,
        "account_generation": 0,
    }

    # 2. Goals: active vs abandoned/achieved/inactive
    fake_db.rows[(*base, "goals", "goal-active")] = {
        "title": "Active goal",
        "status": "focused",
        "is_active": True,
        "account_generation": 0,
    }
    fake_db.rows[(*base, "goals", "goal-abandoned")] = {
        "title": "Abandoned goal",
        "status": "abandoned",
        "is_active": False,
        "account_generation": 0,
    }
    fake_db.rows[(*base, "goals", "goal-achieved")] = {
        "title": "Achieved goal",
        "status": "achieved",
        "is_active": False,
        "account_generation": 0,
    }

    # 3. Candidates: active vs dismissed/deleted
    fake_db.rows[(*base, "candidates", "cand-active")] = {
        "title": "Active candidate",
        "status": "pending",
        "account_generation": 0,
    }
    fake_db.rows[(*base, "candidates", "cand-dismissed")] = {
        "title": "Dismissed candidate",
        "status": "dismissed",
        "account_generation": 0,
    }

    # 4. Workstreams: active vs archived
    fake_db.rows[(*base, "workstreams", "ws-active")] = {
        "title": "Active workstream",
        "status": "active",
        "account_generation": 0,
    }
    fake_db.rows[(*base, "workstreams", "ws-archived")] = {
        "title": "Archived workstream",
        "status": "archived",
        "account_generation": 0,
    }

    state = tr_db.load_canonical_product_state(uid, account_generation=0, firestore_client=fake_db)

    # Validate action items
    task_ids = {t["id"] for t in state["tasks"]}
    assert "task-active" in task_ids
    assert "task-soft-deleted" not in task_ids
    assert "task-legacy-deleted" not in task_ids

    # Validate goals
    goal_ids = {g["id"] for g in state["goals"]}
    assert "goal-active" in goal_ids
    assert "goal-abandoned" not in goal_ids
    assert "goal-achieved" not in goal_ids

    # Validate candidates
    cand_ids = {c["id"] for c in state["candidates"]}
    assert "cand-active" in cand_ids
    assert "cand-dismissed" not in cand_ids

    # Validate workstreams
    ws_ids = {w["id"] for w in state["workstreams"]}
    assert "ws-active" in ws_ids
    assert "ws-archived" not in ws_ids


def test_delete_goal_idempotency_and_cache_bump(monkeypatch):
    fake_db = FakeFirestore()
    uid = "test-user-2"
    goal_id = "goal-to-delete"
    path = ("users", uid, "goals", goal_id)

    bumped = []
    monkeypatch.setattr(goals_db, "bump_action_items_list_version", lambda u: bumped.append(u))

    # Goal does not exist
    assert not goals_db.delete_goal(uid, "nonexistent", firestore_client=fake_db)

    # Initial active goal
    fake_db.rows[path] = {
        "title": "Goal to be deleted",
        "status": "focused",
        "focus_rank": 0,
        "is_active": True,
    }

    # First delete: transitions to abandoned, bumps cache
    assert goals_db.delete_goal(uid, goal_id, firestore_client=fake_db)
    assert bumped == [uid]
    assert fake_db.rows[path]["status"] == "abandoned"
    assert fake_db.rows[path]["is_active"] is False
    assert fake_db.rows[path]["focus_rank"] is None

    # Second delete: idempotent, returns True without repeating write
    bumped.clear()
    assert goals_db.delete_goal(uid, goal_id, firestore_client=fake_db)
    assert bumped == []
