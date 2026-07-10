"""Contract tests for shared Firestore in-memory fakes used in WS-B/WS-I tests."""

from __future__ import annotations

import pytest
from google.api_core.exceptions import NotFound

from tests.unit.test_ws_b_short_term_lifecycle import _DocRef as WsBDocRef
from tests.unit.test_ws_i_write_convergence import _DocRef as WsIDocRef


class _MinimalDb:
    def __init__(self):
        self.docs = {}


@pytest.mark.parametrize("doc_ref_cls", [WsBDocRef, WsIDocRef])
def test_doc_ref_get_set_update_merge_contract(doc_ref_cls):
    db = _MinimalDb()
    ref = doc_ref_cls(db, "users/uid1/doc1")

    snap = ref.get()
    assert snap.exists is False

    ref.set({"a": 1, "b": 2})
    snap = ref.get()
    assert snap.exists is True
    assert snap.to_dict() == {"a": 1, "b": 2}

    ref.update({"b": 3, "c": 4})
    snap = ref.get()
    assert snap.to_dict() == {"a": 1, "b": 3, "c": 4}

    ref.set({"d": 5}, merge=True)
    snap = ref.get()
    assert snap.to_dict() == {"a": 1, "b": 3, "c": 4, "d": 5}

    ref.set({"x": 10})
    snap = ref.get()
    assert snap.to_dict() == {"x": 10}


@pytest.mark.parametrize("doc_ref_cls", [WsBDocRef, WsIDocRef])
def test_doc_ref_update_raises_on_missing_doc(doc_ref_cls):
    db = _MinimalDb()
    ref = doc_ref_cls(db, "missing/path")
    with pytest.raises(NotFound):
        ref.update({"a": 1})
