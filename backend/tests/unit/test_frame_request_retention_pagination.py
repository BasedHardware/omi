from dataclasses import dataclass

from services.frame_request_retention import _load_user_page, _store_user_cursor


@dataclass
class _User:
    id: str


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _StateDocument:
    def __init__(self, cursor_uid: str = ""):
        self.cursor_uid = cursor_uid
        self.writes = []

    def get(self):
        return _Snapshot({"cursor_uid": self.cursor_uid})

    def set(self, data, merge=False):
        self.writes.append((data, merge))
        self.cursor_uid = data["cursor_uid"]


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
        self._after = cursor["__name__"]
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
        return document_id


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

    first, first_cursor = _load_user_page(client, user_limit=2)
    assert [user.id for user in first] == ["a", "b"]
    assert first_cursor == "b"
    _store_user_cursor(client, first_cursor)

    second, second_cursor = _load_user_page(client, user_limit=2)
    assert [user.id for user in second] == ["c", "d"]
    assert second_cursor == "d"
    _store_user_cursor(client, second_cursor)

    tail, tail_cursor = _load_user_page(client, user_limit=2)
    assert [user.id for user in tail] == ["e"]
    assert tail_cursor is None
    _store_user_cursor(client, tail_cursor)

    wrapped, wrapped_cursor = _load_user_page(client, user_limit=2)
    assert [user.id for user in wrapped] == ["a", "b"]
    assert wrapped_cursor == "b"
    assert all(merge is True for _, merge in client.state.writes)


def test_deleted_cursor_wraps_to_first_available_user():
    client = _Client(["a", "b"], cursor_uid="z")

    users, cursor = _load_user_page(client, user_limit=1)

    assert [user.id for user in users] == ["a"]
    assert cursor == "a"
