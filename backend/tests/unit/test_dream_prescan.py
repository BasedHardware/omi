"""Shared Dream state-pass projections retain bounded reads and exclude voice data."""

from tests.unit.test_dream_cleanup_edits import UID
from utils import dream_prescan


class FakeSnapshot:
    def __init__(self, snapshot_id, row):
        self.id = snapshot_id
        self._row = row

    def to_dict(self):
        return self._row


class FakeQuery:
    def __init__(self, client, rows):
        self._client = client
        self._rows = list(rows)

    def select(self, fields):
        self._client.projections.append(list(fields))
        return self

    def where(self, *args, filter=None):
        self._client.filters.append(filter)
        return self

    def order_by(self, field, direction=None):
        return self

    def limit(self, count):
        self._client.limits.append(count)
        return self

    def stream(self, **kwargs):
        return iter([FakeSnapshot(row_id, row) for row_id, row in self._rows])


class FakeOwner:
    def __init__(self, client):
        self._client = client

    def collection(self, name):
        return FakeQuery(self._client, self._client.collections.get(name, []))


class FakeUsers:
    def __init__(self, client):
        self._client = client

    def document(self, uid):
        assert uid
        return FakeOwner(self._client)


class FakeClient:
    def __init__(self, collections=None):
        self.collections = collections or {}
        self.projections = []
        self.filters = []
        self.limits = []

    def collection(self, name):
        assert name == 'users'
        return FakeUsers(self)


def person(name, **extra):
    return {'name': name, **extra}


def test_people_projection_retains_bounds_and_protected_person_filter():
    client = FakeClient({'people': [('p1', person('Dana Nguyen')), ('p2', person('Protected', pinned=True))]})
    candidates, _junk = dream_prescan.scan_people(UID, client)
    assert [person_id for person_id, _row in candidates] == ['p1']
    assert client.limits == [dream_prescan.PEOPLE_LIMIT]
    assert 'speaker_embedding' not in client.projections[0]
    assert 'speech_samples' not in client.projections[0]
