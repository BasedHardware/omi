"""Regression test for Person.deserialize_many_safe.

Several LLM prompt builders load people with
[Person(**p) for p in users_db.get_people_by_ids(...)]. A single malformed or legacy stored
person document (for example one missing the required name field) raised a ValidationError that
aborted the whole people lookup, which in turn broke memory extraction for that conversation.
Person.deserialize_many_safe skips the bad record and keeps the rest, mirroring
Message.deserialize_many_safe (#8882).
"""

from datetime import datetime, timezone

from models.other import Person

_GOOD = {"id": "p1", "name": "Alex"}
_GOOD_2 = {"id": "p2", "name": "Sam", "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
# Missing the required 'name' field -> Person(**record) raises ValidationError.
_MALFORMED = {"id": "p3"}


def test_skips_malformed_record_keeps_valid():
    people = Person.deserialize_many_safe([_GOOD, _MALFORMED, _GOOD_2])

    assert [p.id for p in people] == ["p1", "p2"]
    assert all(isinstance(p, Person) for p in people)


def test_on_error_called_for_each_skip():
    skipped = []
    people = Person.deserialize_many_safe(
        [_GOOD, _MALFORMED], on_error=lambda record, exc: skipped.append((record, exc))
    )

    assert [p.id for p in people] == ["p1"]
    assert len(skipped) == 1
    assert skipped[0][0] == _MALFORMED
    assert isinstance(skipped[0][1], Exception)


def test_all_valid_preserves_order():
    people = Person.deserialize_many_safe([_GOOD_2, _GOOD])

    assert [p.id for p in people] == ["p2", "p1"]


def test_empty_input_returns_empty_list():
    assert Person.deserialize_many_safe([]) == []
