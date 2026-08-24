from types import SimpleNamespace

from utils.memory import canonical_short_term_maintenance_cron as cron


class _Snapshot:
    def __init__(self, uid, payload=None):
        self.id = uid
        self._payload = payload or {}

    def to_dict(self):
        return self._payload


class _Ref:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def get(self):
        value = self.store.get(self.path)
        return SimpleNamespace(exists=value is not None, to_dict=lambda: value)

    def set(self, value, merge=False):
        current = dict(self.store.get(self.path, {})) if merge else {}
        current.update(value)
        self.store[self.path] = current


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.field = None
        self.after = ""
        self.page_size = None

    def where(self, *args, **kwargs):
        field_filter = kwargs.get("filter")
        if field_filter is not None:
            self.field = (field_filter.field_path, field_filter.op_string, field_filter.value)
        elif len(args) >= 3:
            self.field = (args[0], args[1], args[2])
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, count):
        self.page_size = count
        return self

    def stream(self):
        rows = list(self.rows)
        if self.field and self.field[0] == "__name__" and self.field[1] == ">":
            rows = [row for row in rows if row.id > self.field[2]]
        rows.sort(key=lambda row: row.id)
        return rows[: self.page_size]


class _Users:
    def __init__(self, rows):
        self.rows = rows

    def where(self, *args, **kwargs):
        return _Query(self.rows).where(*args, **kwargs)


class _Db:
    def __init__(self):
        self.store = {}
        self.users = _Users([_Snapshot(uid, {"onboarding": {"completed": True}}) for uid in "abcd"])

    def document(self, path):
        return _Ref(self.store, path)

    def collection(self, path):
        assert path == "users"
        return self.users


def test_daily_sweep_inventory_reserves_onboarding_and_advances_separate_cursor(monkeypatch):
    db = _Db()
    monkeypatch.setattr(
        cron,
        "bounded_canonical_memory_uid_inventory",
        lambda *_args, **_kwargs: ("canonical-a", "canonical-b"),
    )
    first = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4)
    second = cron.bounded_daily_memory_sweep_uid_inventory(db, limit=4)

    assert first == ("canonical-a", "canonical-b", "a", "b")
    assert second == ("canonical-a", "canonical-b", "c", "d")
    assert db.store[cron.DAILY_MEMORY_SWEEP_ONBOARDING_INVENTORY_CURSOR_PATH]["last_uid"] == "d"
