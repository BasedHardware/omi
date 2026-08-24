from dataclasses import dataclass

from services import frame_request_retention
from database.frame_requests import FrameCleanupPage
from services.frame_request_retention import (
    _drain_due_pages,
    _load_user_page,
    _store_user_cursor,
)


@dataclass
class _User:
    id: str


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _UserDocument:
    def __init__(self, document_id, user):
        self.id = document_id
        self._user = user

    def get(self):
        if self._user is None:
            return _Snapshot()
        return _UserSnapshot(self._user)


class _UserSnapshot:
    def __init__(self, user):
        self.id = user.id
        self.exists = True

    def to_dict(self):
        return {"id": self.id}


class _StateDocument:
    def __init__(self, cursor_uid: str = ""):
        self.cursor_uid = cursor_uid
        self.retry_cursor_uid = ""
        self.writes = []
        self.retries = _RetryCollection()

    def get(self):
        return _Snapshot({"cursor_uid": self.cursor_uid, "retry_cursor_uid": self.retry_cursor_uid})

    def set(self, data, merge=False):
        self.writes.append((data, merge))
        self.cursor_uid = data["cursor_uid"]
        self.retry_cursor_uid = data.get("retry_cursor_uid", "")

    def collection(self, name):
        assert name == "retry_accounts"
        return self.retries


class _RetrySnapshot:
    def __init__(self, uid):
        self.id = uid


class _RetryDocument:
    def __init__(self, collection, uid):
        self.collection = collection
        self.uid = uid

    def set(self, _data, merge=False):
        assert merge is True
        self.collection.uids.add(self.uid)

    def delete(self):
        self.collection.uids.discard(self.uid)


class _RetryCollection:
    def __init__(self):
        self.uids = set()
        self._limit = 1000
        self._after = ""

    def order_by(self, *_args, **_kwargs):
        self._after = ""
        return self

    def limit(self, value):
        self._limit = value
        return self

    def start_after(self, cursor):
        self._after = cursor["__name__"].uid
        return self

    def stream(self):
        selected = [uid for uid in sorted(self.uids) if uid > self._after][: self._limit]
        return iter(_RetrySnapshot(uid) for uid in selected)

    def document(self, uid):
        return _RetryDocument(self, uid)


class _StateCollection:
    def __init__(self, document):
        self._document = document

    def document(self, _document_id):
        return self._document


class _UsersQuery:
    def __init__(self, users):
        self._users = users
        self._after = None
        self._limit = len(users)

    def order_by(self, *_args, **_kwargs):
        return self

    def start_after(self, cursor):
        document = cursor["__name__"]
        self._after = document.id
        return self

    def limit(self, value):
        self._limit = value
        return self

    def stream(self):
        users = self._users
        if self._after:
            users = [user for user in users if user.id > self._after]
        return iter(users[: self._limit])


class _UsersCollection:
    def __init__(self, users):
        self._users = users

    def order_by(self, *_args, **_kwargs):
        return _UsersQuery(self._users)

    def document(self, document_id):
        user = next((user for user in self._users if user.id == document_id), None)
        return _UserDocument(document_id, user)


class _Client:
    def __init__(self, users, cursor_uid=""):
        self.state = _StateDocument(cursor_uid)
        self.users = _UsersCollection([_User(uid) for uid in users])

    def collection(self, name):
        if name == "maintenance_state":
            return _StateCollection(self.state)
        assert name == "users"
        return self.users


def test_user_pagination_advances_and_wraps_without_repeating_first_page_forever():
    client = _Client(["a", "b", "c", "d", "e"])

    first, first_cursor, first_retries = _load_user_page(client, user_limit=2)
    assert [user.id for user in first] == ["a", "b"]
    assert first_cursor == "b"
    assert first_retries == []
    _store_user_cursor(client, first_cursor)

    second, second_cursor, _ = _load_user_page(client, user_limit=2)
    assert [user.id for user in second] == ["c", "d"]
    assert second_cursor == "d"
    _store_user_cursor(client, second_cursor)

    tail, tail_cursor, _ = _load_user_page(client, user_limit=2)
    assert [user.id for user in tail] == ["e"]
    assert tail_cursor is None
    _store_user_cursor(client, tail_cursor)

    wrapped, wrapped_cursor, _ = _load_user_page(client, user_limit=2)
    assert [user.id for user in wrapped] == ["a", "b"]
    assert wrapped_cursor == "b"
    assert all(merge is True for _, merge in client.state.writes)


def test_deleted_cursor_wraps_to_first_available_user():
    client = _Client(["a", "b"], cursor_uid="z")

    users, cursor, _ = _load_user_page(client, user_limit=1)

    assert [user.id for user in users] == ["a"]
    assert cursor == "a"


def test_retry_uids_are_served_without_pinning_population_cursor():
    client = _Client(["a", "b", "c"], cursor_uid="a")
    client.state.retries.uids = {"a"}

    users, cursor, deferred = _load_user_page(client, user_limit=2)

    assert [user.id for user in users] == ["a", "b"]
    assert cursor == "b"
    assert deferred == ["a"]
    _store_user_cursor(client, cursor)
    assert client.state.retries.uids == {"a"}


def test_retry_cursor_rotates_fairly_across_poison_accounts():
    client = _Client(["a", "b", "c", "d"])
    client.state.retries.uids = {"a", "b", "c", "d"}

    first, cursor, first_retry = _load_user_page(client, user_limit=2)
    assert first_retry == ["a"]
    assert [user.id for user in first] == ["a"]
    _store_user_cursor(client, cursor, first_retry[-1])

    second, _, second_retry = _load_user_page(client, user_limit=2)
    assert second_retry == ["b"]
    assert [user.id for user in second] == ["b"]


def test_account_failure_advances_population_and_persists_convergent_retry(monkeypatch):
    client = _Client(["a", "b", "c"])
    failing = {"a"}

    def prune(uid, **_kwargs):
        if uid in failing:
            raise RuntimeError("transient query outage")
        return 0

    monkeypatch.setattr(frame_request_retention, "prune_expired_frame_requests", prune)
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_frame_request_pixels",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_ambiguous_frame_upload_pixels",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        frame_request_retention,
        "cleanup_conversation_frame_deletion_outbox",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(frame_request_retention, "emit_posthog_event", lambda *_args, **_kwargs: None)

    degraded = frame_request_retention.run_frame_request_retention_maintenance(user_limit=2, firestore_client=client)
    assert degraded["accounts_with_errors"] == 1
    assert client.state.cursor_uid == "b"
    assert client.state.retries.uids == {"a"}

    failing.clear()
    recovered = frame_request_retention.run_frame_request_retention_maintenance(user_limit=2, firestore_client=client)
    assert recovered["accounts_with_errors"] == 0
    assert client.state.retries.uids == set()


def test_retry_queue_has_no_fixed_capacity_or_array_overwrite():
    client = _Client([])
    for index in range(5000):
        client.state.retries.document(f"uid-{index:04d}").set({}, merge=True)

    assert len(client.state.retries.uids) == 5000
    _store_user_cursor(client, "cursor")
    assert len(client.state.retries.uids) == 5000


def test_due_backlog_drains_every_full_page_without_increasing_query_limit():
    pages = iter([32, 32, 7])

    assert _drain_due_pages(lambda: next(pages), page_size=32) == (71, False)


def test_due_backlog_is_bounded_and_reports_more_work():
    assert _drain_due_pages(lambda: 32, page_size=32, max_pages=3) == (96, True)


def test_failed_cleanup_page_does_not_hide_due_backlog_or_overstate_cleaned_count():
    pages = iter([FrameCleanupPage(processed=32, cleaned=0), FrameCleanupPage(processed=3, cleaned=3)])

    assert _drain_due_pages(lambda: next(pages), page_size=32) == (3, False)
