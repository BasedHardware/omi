"""calendar_meetings.create_meeting must be idempotent for the same calendar event.

The router (routers/calendar_meetings.py::store_calendar_meeting) does a check-then-create:
it calls get_meeting_id_by_calendar_event() and only create_meeting() if nothing was found.
Under concurrency two same-event POSTs both pass that check and each called
_get_meetings_collection(uid).document() -> a RANDOM Firestore id, producing duplicate
meeting docs (TOCTOU).

The fix derives the document id deterministically from the natural key
(uid:calendar_source:calendar_event_id via document_id_from_seed), so concurrent creates
converge on a single document. It also only sets created_at when the doc does not already
exist, so a racing write does not reset it.

database/calendar_meetings.py imports google.cloud.firestore + database._client at module top,
so we import it under a meta-path stub finder and then inject a real deterministic
document_id_from_seed plus a fake meetings collection.
"""

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
import uuid
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

# Stub only the heavy dependencies of database/calendar_meetings.py — NOT the
# database package or calendar_meetings itself, so the real module loads from disk.
_STUB = ('database._client', 'utils', 'firebase_admin', 'google', 'sentry_sdk')


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from database import calendar_meetings as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


def _real_document_id_from_seed(seed: str) -> str:
    """The real implementation from database/_client.py: deterministic id from a seed."""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


class _FakeDoc:
    """A fake Firestore document reference that records writes for a fixed id."""

    def __init__(self, doc_id):
        self.id = doc_id
        self.set_calls = []  # list of (data_copy, merge)
        self._exists = False  # first creator sees a non-existent doc

    def get(self):
        snap = MagicMock()
        snap.exists = self._exists
        return snap

    def set(self, data, merge=False):
        # Record a shallow copy so later mutations don't rewrite history.
        self.set_calls.append((dict(data), merge))
        self._exists = True  # after the first write, the doc exists


class _FakeCollection:
    """Returns the SAME _FakeDoc for the same id (mirrors Firestore document(id) semantics),
    and a fresh random-id _FakeDoc when document() is called with no id."""

    def __init__(self):
        self.docs_by_id = {}
        self.auto_docs = []

    def document(self, doc_id=None):
        if doc_id is None:
            d = _FakeDoc(str(uuid.uuid4()))
            self.auto_docs.append(d)
            return d
        if doc_id not in self.docs_by_id:
            self.docs_by_id[doc_id] = _FakeDoc(doc_id)
        return self.docs_by_id[doc_id]


_MEETING = {
    'calendar_event_id': 'evt-123',
    'calendar_source': 'google_calendar',
    'title': 'Standup',
}


# `create=True` so the patch also succeeds against the PRE-FIX module (which never
# imports document_id_from_seed); then the RED comes from the actual duplicate-doc
# BEHAVIOR (random ids -> two distinct docs), not merely from a missing attribute.
_PATCH_SEED = dict(create=True, side_effect=_real_document_id_from_seed)


def test_concurrent_same_event_creates_converge_to_one_doc():
    """Two creates with identical calendar_event_id/source must land on ONE document
    (deterministic id), not two distinct random-id docs (the TOCTOU duplicate)."""
    coll = _FakeCollection()
    with patch.object(mod, '_get_meetings_collection', return_value=coll), patch.object(
        mod, 'document_id_from_seed', **_PATCH_SEED
    ):
        id1 = mod.create_meeting('u1', dict(_MEETING))
        id2 = mod.create_meeting('u1', dict(_MEETING))

    # Same deterministic id both times.
    assert id1 == id2
    # Exactly one underlying document was ever materialized.
    all_docs = list(coll.docs_by_id.values()) + coll.auto_docs
    distinct_ids = {d.id for d in all_docs}
    assert len(distinct_ids) == 1, f"expected one converged doc, got distinct ids {distinct_ids}"
    # No random-id (auto) docs were created — the create path used a seeded id.
    assert coll.auto_docs == [], "create path used a random .document() id instead of a deterministic one"


def test_deterministic_id_matches_natural_key_seed():
    """The id must be derived from uid:source:calendar_event_id (not random)."""
    coll = _FakeCollection()
    with patch.object(mod, '_get_meetings_collection', return_value=coll), patch.object(
        mod, 'document_id_from_seed', **_PATCH_SEED
    ):
        got = mod.create_meeting('u1', dict(_MEETING))

    expected = _real_document_id_from_seed('u1:google_calendar:evt-123')
    assert got == expected, f"id {got} is not derived from the natural-key seed (expected {expected})"


def test_created_at_not_overwritten_on_second_create():
    """The second (racing) create must NOT reset created_at, since the doc already exists."""
    coll = _FakeCollection()
    with patch.object(mod, '_get_meetings_collection', return_value=coll), patch.object(
        mod, 'document_id_from_seed', **_PATCH_SEED
    ):
        mod.create_meeting('u1', dict(_MEETING))
        mod.create_meeting('u1', dict(_MEETING))

    # Both creates must converge on the same single doc that was written twice.
    all_docs = list(coll.docs_by_id.values()) + coll.auto_docs
    converged = [d for d in all_docs if len(d.set_calls) == 2]
    assert len(converged) == 1, "the two creates did not converge on a single document (duplicate created)"
    doc = converged[0]
    first_data, _ = doc.set_calls[0]
    second_data, second_merge = doc.set_calls[1]
    # First create stamps created_at; second (racing) create must not include created_at.
    assert 'created_at' in first_data
    assert 'created_at' not in second_data, "racing create overwrote created_at"
    # And the racing write merges into the existing doc.
    assert second_merge is True
