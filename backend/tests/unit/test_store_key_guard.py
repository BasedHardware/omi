"""`ensure_id_segment` is the boundary that decides whether a document id is safe.

It had no direct test. It is the guard that stops a `/` in an id from addressing a different
document — path injection through a value that arrives from a request or from a stored row — and it
refuses rather than encodes, because an encoded id would not round-trip with the reads elsewhere
that address the same document by its raw id.

Its parameter is typed `object`, not `str`, and that is load-bearing: the ids reaching it come from
places where a declared type is a promise rather than a fact, and annotating `str` would make the
isinstance check dead to a type checker and delete the guard.
"""

import pytest

from database.store.keys import ensure_id_segment


@pytest.mark.parametrize('value', ['user-42', 'a', 'UUID-with-dashes-0000', 'dot.separated'])
def test_a_safe_segment_comes_back_unchanged(value):
    assert ensure_id_segment(value) == value


@pytest.mark.parametrize('value', ['a/b', '/leading', 'trailing/', 'users/1/items/2'])
def test_a_slash_is_refused_rather_than_encoded(value):
    with pytest.raises(ValueError):
        ensure_id_segment(value)


def test_an_empty_id_is_refused():
    with pytest.raises(ValueError):
        ensure_id_segment('')


@pytest.mark.parametrize('value', [None, 123, ['x'], {'a': 1}, b'bytes'])
def test_a_non_string_is_refused_at_runtime(value):
    """The annotation says `object` precisely so this stays reachable."""
    with pytest.raises(ValueError):
        ensure_id_segment(value)


def test_the_label_names_what_was_rejected():
    with pytest.raises(ValueError, match='person id'):
        ensure_id_segment('a/b', label='person id')
