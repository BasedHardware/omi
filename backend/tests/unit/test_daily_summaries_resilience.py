import os
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _setup_preflight_stubs():
    for p in ["google", "google.api_core", "google.cloud"]:
        _pkg(p)

    _exc = _mod("google.api_core.exceptions")
    if not hasattr(_exc, "NotFound"):
        _exc.NotFound = type("NotFound", (Exception,), {})
    if not hasattr(_exc, "InvalidArgument"):
        _exc.InvalidArgument = type("InvalidArgument", (Exception,), {})

    _fs = _mod("google.cloud.firestore")
    if not hasattr(_fs, "Query"):
        _fs.Query = MagicMock()
    if not hasattr(_fs, "Client"):
        _fs.Client = MagicMock
    if not hasattr(_fs, "transactional"):
        _fs.transactional = lambda fn: fn

    class _FakeFieldFilter:
        def __init__(self, field_path: str, op: str, value: Any):
            self.field_path = field_path
            self.op = op
            self.value = value

    if not hasattr(_fs, "FieldFilter"):
        _fs.FieldFilter = _FakeFieldFilter

    _fs_v1 = _mod("google.cloud.firestore_v1")
    if not hasattr(_fs_v1, "FieldFilter"):
        _fs_v1.FieldFilter = _FakeFieldFilter

    _fs_bq = _mod("google.cloud.firestore_v1.base_query")
    if not hasattr(_fs_bq, "FieldFilter"):
        _fs_bq.FieldFilter = _FakeFieldFilter

    _redis = _mod("redis")
    if not hasattr(_redis, "Redis"):
        _redis.Redis = MagicMock()


_setup_preflight_stubs()

import database.daily_summaries as daily_summaries


class _FakeSnapshot:
    def __init__(self, doc_id: str, data: Optional[Dict[str, Any]], reference: Any = None):
        self.id = doc_id
        self._data = data
        self.exists = data is not None
        self.reference = reference

    def to_dict(self) -> Optional[Dict[str, Any]]:
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store: Dict[str, Any], doc_id: str, path: str = ""):
        self._store = store
        self.id = doc_id
        self.path = path or f"documents/{doc_id}"

    def get(self, transaction: Any = None) -> _FakeSnapshot:
        return _FakeSnapshot(self.id, self._store.get(self.id), reference=self)

    def set(self, payload: Dict[str, Any], merge: bool = False) -> None:
        if merge and self.id in self._store:
            self._store[self.id].update(payload)
        else:
            self._store[self.id] = dict(payload)

    def update(self, values: Dict[str, Any]) -> None:
        if self.id not in self._store:
            raise KeyError(f"404 Not Found: {self.id}")
        self._store[self.id].update(values)

    def delete(self) -> None:
        self._store.pop(self.id, None)


class _FakeQuery:
    def __init__(self, store: Dict[str, Any], predicates: Optional[List[Any]] = None):
        self._store = store
        self._predicates = predicates or []
        self._limit: Optional[int] = None
        self._offset: int = 0

    def where(self, filter: Any = None) -> "_FakeQuery":
        q = _FakeQuery(self._store, self._predicates + [(filter.field_path, filter.op, filter.value)])
        q._limit = self._limit
        q._offset = self._offset
        return q

    def order_by(self, _field: str, direction: Any = None) -> "_FakeQuery":
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def offset(self, n: int) -> "_FakeQuery":
        self._offset = n
        return self

    def _matches(self, doc_data: Dict[str, Any]) -> bool:
        for field, op, val in self._predicates:
            current = doc_data.get(field)
            if op == "==" and current != val:
                return False
            elif op == ">=" and (current is None or current < val):
                return False
            elif op == "<=" and (current is None or current > val):
                return False
        return True

    def _matching(self) -> List[Any]:
        items = [(doc_id, data) for doc_id, data in self._store.items() if self._matches(data)]
        if self._offset:
            items = items[self._offset :]
        if self._limit is not None:
            items = items[: self._limit]
        return items

    def stream(self):
        for doc_id, data in self._matching():
            yield _FakeSnapshot(doc_id, data, reference=_FakeDocRef(self._store, doc_id))

    def count(self):
        total = len([1 for _, data in self._store.items() if self._matches(data)])
        return MagicMock(get=lambda: [[MagicMock(value=total)]])


class _FakeCollection(_FakeQuery):
    def __init__(self, store: Dict[str, Any], prefix: str = ""):
        super().__init__(store, [])
        self._prefix = prefix

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._store, doc_id, path=f"{self._prefix}/{doc_id}")


class _FakeUserRef:
    def __init__(self, collections: Dict[str, Dict[str, Any]]):
        self._collections = collections

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections.setdefault(name, {}), prefix=f"users/u1/{name}")


class _FakeTransaction:
    def __init__(self):
        self.writes = []

    def set(self, reference: Any, values: Dict[str, Any]) -> None:
        self.writes.append((reference, values))
        reference.set(values)

    def update(self, reference: Any, values: Dict[str, Any]) -> None:
        self.writes.append((reference, values))
        reference.update(values)


class _FakeDb:
    def __init__(self, summaries: Optional[Dict[str, Any]] = None, usage: Optional[Dict[str, Any]] = None):
        self._collections = {
            daily_summaries.DAILY_SUMMARIES_COLLECTION: summaries if summaries is not None else {},
            daily_summaries.DESKTOP_DAILY_USAGE_COLLECTION: usage if usage is not None else {},
        }
        self.last_transaction = None

    def collection(self, _name: str):
        mock_users = MagicMock()
        mock_users.document.return_value = _FakeUserRef(self._collections)
        return mock_users

    def transaction(self):
        t = _FakeTransaction()
        self.last_transaction = t
        return t


class TestDailySummariesResilience(unittest.TestCase):
    def _patch_db(self, fake_db: _FakeDb):
        return patch.object(daily_summaries, "db", fake_db)

    def test_create_daily_summary_validates_uid_and_data(self):
        """create_daily_summary raises ValueError on empty uid or non-dict data, auto-allocates missing id."""
        fake_db = _FakeDb()
        with self._patch_db(fake_db):
            with self.assertRaises(ValueError):
                daily_summaries.create_daily_summary("", {"headline": "Day 1"})
            with self.assertRaises(ValueError):
                daily_summaries.create_daily_summary("   ", {"headline": "Day 1"})
            with self.assertRaises(ValueError):
                daily_summaries.create_daily_summary("u1/traversal", {"headline": "Day 1"})
            with self.assertRaises(ValueError):
                daily_summaries.create_daily_summary("u1", "not a dict")  # type: ignore

            # Auto-allocates UUID when id is missing
            assigned_id = daily_summaries.create_daily_summary("u1", {"headline": "Great day"})
            self.assertTrue(bool(assigned_id))
            store = fake_db._collections[daily_summaries.DAILY_SUMMARIES_COLLECTION]
            self.assertIn(assigned_id, store)
            self.assertEqual(store[assigned_id]["headline"], "Great day")
            self.assertIn("created_at", store[assigned_id])

    def test_get_daily_summary_guards_empty_and_slash_ids(self):
        """get_daily_summary returns None on blank, whitespace, or slash-containing uid/summary_id."""
        summaries = {"s1": {"id": "s1", "headline": "Productive Monday"}}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db):
            self.assertIsNone(daily_summaries.get_daily_summary("", "s1"))
            self.assertIsNone(daily_summaries.get_daily_summary("   ", "s1"))
            self.assertIsNone(daily_summaries.get_daily_summary("u1", ""))
            self.assertIsNone(daily_summaries.get_daily_summary("u1", "   "))
            self.assertIsNone(daily_summaries.get_daily_summary("u/1", "s1"))
            self.assertIsNone(daily_summaries.get_daily_summary("u1", "s/1"))

            result = daily_summaries.get_daily_summary("u1", "s1")
            self.assertIsNotNone(result)
            self.assertEqual(result.get("headline"), "Productive Monday")

    def test_get_daily_summary_by_date_guards_empty_inputs(self):
        """get_daily_summary_by_date returns None on blank/invalid date or uid."""
        summaries = {"s1": {"id": "s1", "date": "2026-09-28", "headline": "Autumn Start"}}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db):
            self.assertIsNone(daily_summaries.get_daily_summary_by_date("", "2026-09-28"))
            self.assertIsNone(daily_summaries.get_daily_summary_by_date("u1", ""))
            self.assertIsNone(daily_summaries.get_daily_summary_by_date("u/1", "2026-09-28"))

            found = daily_summaries.get_daily_summary_by_date("u1", "2026-09-28")
            self.assertIsNotNone(found)
            self.assertEqual(found.get("headline"), "Autumn Start")

    def test_get_daily_summaries_clamps_limit_and_offset(self):
        """get_daily_summaries bounds limit to [1, 500] and offset to >= 0."""
        summaries = {f"s{i}": {"id": f"s{i}", "date": f"2026-09-{i:02d}"} for i in range(1, 10)}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db):
            self.assertEqual(daily_summaries.get_daily_summaries(""), [])
            self.assertEqual(daily_summaries.get_daily_summaries("u/1"), [])

            # limit clamping: limit <= 0 clamped to 1
            res_clamped = daily_summaries.get_daily_summaries("u1", limit=-5)
            self.assertEqual(len(res_clamped), 1)

            # negative offset clamped to 0
            res_all = daily_summaries.get_daily_summaries("u1", limit=100, offset=-10)
            self.assertEqual(len(res_all), 9)

            # date filtering
            res_filtered = daily_summaries.get_daily_summaries("u1", start_date="2026-09-03", end_date="2026-09-05")
            self.assertEqual(len(res_filtered), 3)

    def test_update_daily_summary_overwrites_in_place_preserving_id(self):
        """update_daily_summary returns False on invalid ids, preserves target id on success."""
        summaries = {"s1": {"id": "s1", "headline": "Old Headline"}}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db):
            self.assertFalse(daily_summaries.update_daily_summary("", "s1", {"headline": "New"}))
            self.assertFalse(daily_summaries.update_daily_summary("u1", "", {"headline": "New"}))
            self.assertFalse(daily_summaries.update_daily_summary("u1", "s/1", {"headline": "New"}))
            self.assertFalse(daily_summaries.update_daily_summary("u1", "s1", "invalid"))  # type: ignore

            success = daily_summaries.update_daily_summary(
                "u1", "s1", {"id": "fresh-uuid-from-generator", "headline": "New Headline"}
            )
            self.assertTrue(success)
            store = fake_db._collections[daily_summaries.DAILY_SUMMARIES_COLLECTION]
            self.assertEqual(store["s1"]["id"], "s1")
            self.assertEqual(store["s1"]["headline"], "New Headline")

    def test_delete_daily_summary_survives_redis_exceptions(self):
        """delete_daily_summary cleanly deletes from Firestore even if redis throws an exception."""
        summaries = {"s1": {"id": "s1"}}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db), patch.object(
            daily_summaries.redis_db, "remove_daily_summary_to_uid", side_effect=RuntimeError("Redis down")
        ):
            self.assertFalse(daily_summaries.delete_daily_summary("", "s1"))
            self.assertFalse(daily_summaries.delete_daily_summary("u1", "s/1"))

            # Must return True and delete from Firestore despite Redis failure
            deleted = daily_summaries.delete_daily_summary("u1", "s1")
            self.assertTrue(deleted)
            self.assertNotIn("s1", fake_db._collections[daily_summaries.DAILY_SUMMARIES_COLLECTION])

    def test_set_daily_summary_visibility_guards_inputs_and_missing_doc(self):
        """set_daily_summary_visibility guards empty inputs and handles missing documents gracefully."""
        summaries = {"s1": {"id": "s1", "visibility": "private"}}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db):
            self.assertFalse(daily_summaries.set_daily_summary_visibility("", "s1", "public"))
            self.assertFalse(daily_summaries.set_daily_summary_visibility("u1", "", "public"))
            self.assertFalse(daily_summaries.set_daily_summary_visibility("u1", "s1", ""))
            self.assertFalse(daily_summaries.set_daily_summary_visibility("u1", "s/1", "public"))

            # Success on existing doc
            self.assertTrue(daily_summaries.set_daily_summary_visibility("u1", "s1", "public"))
            self.assertEqual(summaries["s1"]["visibility"], "public")

            # Missing doc returns False without crashing
            self.assertFalse(daily_summaries.set_daily_summary_visibility("u1", "nonexistent", "public"))

    def test_get_summaries_count_handles_aggregation_and_empty_uid(self):
        """get_summaries_count returns 0 on invalid uid or counts existing summaries correctly."""
        summaries = {"s1": {"id": "s1"}, "s2": {"id": "s2"}}
        fake_db = _FakeDb(summaries=summaries)
        with self._patch_db(fake_db):
            self.assertEqual(daily_summaries.get_summaries_count(""), 0)
            self.assertEqual(daily_summaries.get_summaries_count("u/1"), 0)
            self.assertEqual(daily_summaries.get_summaries_count("u1"), 2)

    def test_upsert_desktop_daily_usage_merges_counters_by_max(self):
        """upsert_desktop_daily_usage applies max() over running counters and guards inputs."""
        usage = {
            "2026-09-28__dev-1": {
                "date": "2026-09-28",
                "client_device_id": "dev-1",
                "watching_seconds": 120,
                "listening_seconds": 300,
                "proactive_cards_shown": 5,
            }
        }
        fake_db = _FakeDb(usage=usage)
        with self._patch_db(fake_db):
            self.assertFalse(
                daily_summaries.upsert_desktop_daily_usage(
                    "", "2026-09-28", "America/New_York", "dev-1", {"watching_seconds": 150}
                )
            )
            self.assertFalse(
                daily_summaries.upsert_desktop_daily_usage(
                    "u1", "2026-09-28", "America/New_York", "dev/1", {"watching_seconds": 150}
                )
            )

            # Update: watching_seconds increases, listening_seconds is lower than existing (must stay 300)
            success = daily_summaries.upsert_desktop_daily_usage(
                "u1",
                "2026-09-28",
                "America/New_York",
                "dev-1",
                {
                    "watching_seconds": 200,
                    "listening_seconds": 100,
                    "proactive_cards_shown": 8,
                    "ptt_turns": -5,  # negative should be clamped to 0
                },
            )
            self.assertTrue(success)
            doc = usage["2026-09-28__dev-1"]
            self.assertEqual(doc["watching_seconds"], 200)
            self.assertEqual(doc["listening_seconds"], 300)  # max(300, 100)
            self.assertEqual(doc["proactive_cards_shown"], 8)
            self.assertEqual(doc["ptt_turns"], 0)

    def test_get_desktop_daily_usage_sums_all_devices(self):
        """get_desktop_daily_usage sums counters across multiple devices for the specified date."""
        usage = {
            "2026-09-28__laptop": {
                "date": "2026-09-28",
                "watching_seconds": 100,
                "listening_seconds": 200,
            },
            "2026-09-28__phone": {
                "date": "2026-09-28",
                "watching_seconds": 50,
                "listening_seconds": 150,
            },
            "2026-09-27__laptop": {  # different date, must be excluded
                "date": "2026-09-27",
                "watching_seconds": 999,
            },
        }
        fake_db = _FakeDb(usage=usage)
        with self._patch_db(fake_db):
            self.assertEqual(
                daily_summaries.get_desktop_daily_usage("", "2026-09-28"),
                {field: 0 for field in daily_summaries.DESKTOP_DAILY_USAGE_COUNTER_FIELDS},
            )

            totals = daily_summaries.get_desktop_daily_usage("u1", "2026-09-28")
            self.assertEqual(totals["watching_seconds"], 150)
            self.assertEqual(totals["listening_seconds"], 350)
            self.assertEqual(totals["proactive_cards_shown"], 0)


if __name__ == "__main__":
    unittest.main()
