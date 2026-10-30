"""A name lookup finds the existing person whatever casing their name was saved with."""

from copy import deepcopy
from types import SimpleNamespace

from database import person_aliases as people


class PeopleFirestore:
    """One owner's people. Like Firestore, an ``==`` filter compares strings exactly."""

    def __init__(self, rows):
        self.rows = rows
        self.reads = []

    def collection(self, name):
        assert name == 'users'
        return SimpleNamespace(
            document=lambda uid: SimpleNamespace(collection=lambda name: PeopleQuery(self, uid, name))
        )


class PeopleQuery:
    def __init__(self, db, uid, name, field_filter=None):
        assert name == 'people'
        self.db, self.uid, self.field_filter = db, uid, field_filter

    def where(self, *, filter):
        return PeopleQuery(self.db, self.uid, 'people', filter)

    def stream(self):
        rows = list(self.db.rows[self.uid].items())
        if self.field_filter is None:
            self.db.reads.append('scan')
        else:
            field, value = self.field_filter.field_path, self.field_filter.value
            assert self.field_filter.op_string == '=='
            self.db.reads.append((field, value))
            rows = [(person_id, row) for person_id, row in rows if row.get(field) == value]
        return iter([SimpleNamespace(id=person_id, to_dict=lambda row=deepcopy(row): row) for person_id, row in rows])


def test_lookup_finds_a_person_saved_with_other_casing():
    db = PeopleFirestore({'u1': {'p1': {'name': 'alice'}, 'p2': {'name': 'Mcdonald'}, 'p3': {'name': 'Mary  Jane '}}})

    assert people.find_person_by_name(db, 'u1', 'Alice') == {'name': 'alice', 'id': 'p1'}
    assert people.find_person_by_name(db, 'u1', 'McDonald') == {'name': 'Mcdonald', 'id': 'p2'}
    assert people.find_person_by_name(db, 'u1', 'mary jane') == {'name': 'Mary  Jane ', 'id': 'p3'}


def test_exact_match_wins_without_scanning_people():
    db = PeopleFirestore({'u1': {'p1': {'name': 'mark'}, 'p2': {'name': 'Mark'}}})

    assert people.find_person_by_name(db, 'u1', 'Mark') == {'name': 'Mark', 'id': 'p2'}
    assert db.reads == [('name', 'Mark')]


def test_case_insensitive_match_skips_dismissed_and_unnamed_people():
    db = PeopleFirestore(
        {'u1': {'p1': {'speech_samples': []}, 'p2': {'name': 'Alice', 'is_dismissed': True}, 'p3': {'name': 'ALICE'}}}
    )

    assert people.find_person_by_name(db, 'u1', 'alice') == {'name': 'ALICE', 'id': 'p3'}
    assert db.reads == [('name', 'alice'), 'scan']

    del db.rows['u1']['p3']
    assert people.find_person_by_name(db, 'u1', 'alice') is None
