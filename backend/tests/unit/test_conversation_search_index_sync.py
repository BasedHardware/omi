"""The missing writer for the Typesense `conversations` collection (ADR-0064).

search.py only READS that collection; upstream fills it from a pipeline that is not in this codebase, so
on-prem it was permanently empty and the app's conversation search and DATE BROWSE had nothing to find.

The two rules worth testing hardest are about the bound, because getting them wrong is worse than being
slow: a truncated run must SAY so, and a truncated run must NOT prune (pruning is "delete what the scan
did not see", so pruning a partial scan deletes live conversations from the index).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from utils.conversations import search_index_sync as sync


class _Record:
    def __init__(self, path, data):
        self.path = path
        self.data = data


class _FakeDocuments:
    def __init__(self, store):
        self._store = store

    def upsert(self, document):
        self._store[document['id']] = document
        return document

    def export(self):
        return '\n'.join(json.dumps(d) for d in self._store.values())

    def __getitem__(self, doc_id):
        store = self._store

        class _Handle:
            def delete(self):
                store.pop(doc_id, None)

        return _Handle()


class _FakeCollection:
    def __init__(self, store, schema):
        self.documents = _FakeDocuments(store)
        self._schema = schema

    def retrieve(self):
        if self._schema is None:
            raise RuntimeError('not found')
        return self._schema


class _FakeCollections:
    def __init__(self, store, schema=None, documents=None):
        self._store = store
        self._schema = schema
        self._documents = documents
        self.created = []

    def __getitem__(self, name):
        collection = _FakeCollection(self._store, self._schema)
        if self._documents is not None:
            collection.documents = self._documents
        return collection

    def create(self, schema):
        self.created.append(schema)
        self._schema = schema


class _FakeClient:
    def __init__(self, store=None, schema=None, documents=None):
        self.collections = _FakeCollections(store if store is not None else {}, schema, documents)


class _FakeStore:
    """Pages by document-name keyset, like the real query_group."""

    def __init__(self, records):
        self._records = list(records)

    def query_group(self, group, *, limit=None, start_after=None, **_kw):
        assert group == 'conversations'
        rows = self._records
        if start_after is not None:
            rows = [r for r in rows if r.path > start_after]
        return rows[: limit or len(rows)]


def _conv(uid, cid, *, title='morning notes', overview='espresso and a plan', discarded=False, locked=False):
    base = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    return _Record(
        f'users/{uid}/conversations/{cid}',
        {
            'created_at': base,
            'started_at': base,
            'finished_at': base,
            'discarded': discarded,
            'is_locked': locked,
            'structured': {'title': title, 'overview': overview},
        },
    )


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setenv('TYPESENSE_HOST', 'typesense')
    monkeypatch.setenv('TYPESENSE_API_KEY', 'k')


# --- the document contract with search.py -------------------------------------------------------


def test_the_document_carries_exactly_what_search_reads():
    doc = sync.build_conversation_search_document('u1', 'c1', _conv('u1', 'c1').data)
    assert doc is not None
    # dotted keys are FLAT on purpose: verified against the pinned image that Typesense treats a dotted
    # name as one field when nested mode is off, which is the shape search.py's query_by asks for.
    assert doc['structured.title'] == 'morning notes'
    assert doc['structured.overview'] == 'espresso and a plan'
    assert doc['id'] == 'c1' and doc['userId'] == 'u1'
    assert isinstance(doc['created_at'], int) and isinstance(doc['started_at'], int)
    assert doc['discarded'] is False and doc['is_locked'] is False


def test_a_conversation_missing_a_timestamp_is_not_indexed():
    """search.py does int(doc['created_at']) and SKIPS the hit on failure — an unrenderable hit is worse
    than an absent one, so it is rejected here instead."""
    data = _conv('u1', 'c1').data | {'finished_at': None}
    assert sync.build_conversation_search_document('u1', 'c1', data) is None


def test_a_missing_structured_block_is_empty_strings_not_a_crash():
    data = {'created_at': 1, 'started_at': 1, 'finished_at': 1}
    doc = sync.build_conversation_search_document('u1', 'c1', data)
    assert doc is not None and doc['structured.title'] == '' and doc['structured.overview'] == ''


def test_a_boolean_is_not_a_timestamp():
    """bool is an int in Python; `discarded: True` must not become created_at=1."""
    data = _conv('u1', 'c1').data | {'created_at': True}
    assert sync.build_conversation_search_document('u1', 'c1', data) is None


def test_the_owner_comes_from_the_path():
    assert sync.uid_and_id_from_path('users/u9/conversations/c9') == ('u9', 'c9')
    assert sync.uid_and_id_from_path('users/u9/memories/m1') == (None, None)
    assert sync.uid_and_id_from_path('conversations/c9') == (None, None)


# --- the reconcile ------------------------------------------------------------------------------


def test_a_full_pass_indexes_everything_and_prunes_what_is_gone():
    indexed = {'stale-1': {'id': 'stale-1'}}
    client = _FakeClient(store=indexed, schema=sync.CONVERSATIONS_SCHEMA)
    store = _FakeStore([_conv('u1', 'c1'), _conv('u1', 'c2'), _conv('u2', 'c3')])

    report = sync.reconcile_conversation_search_index(store=store, client=client, page_size=2)

    assert (report.scanned, report.indexed, report.pruned) == (3, 3, 1)
    assert report.truncated is False and report.errors == []
    assert set(indexed) == {'c1', 'c2', 'c3'}, 'the stale document survived the prune'


def test_a_truncated_pass_says_so_and_refuses_to_prune():
    """The rule that matters: pruning a partial scan would delete live conversations."""
    indexed = {'c1': {'id': 'c1'}, 'c2': {'id': 'c2'}, 'c3': {'id': 'c3'}}
    client = _FakeClient(store=indexed, schema=sync.CONVERSATIONS_SCHEMA)
    store = _FakeStore([_conv('u1', f'c{i}') for i in range(1, 6)])

    report = sync.reconcile_conversation_search_index(store=store, client=client, page_size=2, max_documents=2)

    assert report.truncated is True
    assert report.pruned == 0
    assert 'truncated' in (report.prune_skipped_reason or '')
    assert set(indexed) >= {'c1', 'c2', 'c3'}, 'a partial scan pruned live documents'


def test_one_bad_document_does_not_abort_the_pass():
    class _Flaky(_FakeDocuments):
        def upsert(self, document):
            if document['id'] == 'c2':
                raise RuntimeError('typesense rejected it')
            return super().upsert(document)

    indexed: dict = {}
    client = _FakeClient(store=indexed, schema=sync.CONVERSATIONS_SCHEMA, documents=_Flaky(indexed))
    store = _FakeStore([_conv('u1', 'c1'), _conv('u1', 'c2'), _conv('u1', 'c3')])

    report = sync.reconcile_conversation_search_index(store=store, client=client, page_size=10)

    assert report.indexed == 2 and len(report.errors) == 1
    assert set(indexed) == {'c1', 'c3'}


def test_the_collection_is_created_when_absent():
    client = _FakeClient(schema=None)
    sync.reconcile_conversation_search_index(store=_FakeStore([]), client=client)
    assert client.collections.created and client.collections.created[0]['name'] == 'conversations'


def test_an_incompatible_existing_collection_names_the_missing_field():
    """A collection made by another writer that lacks a query_by field makes every search fail with
    Typesense's own "could not find a field" — say which field instead."""
    client = _FakeClient(schema={'fields': [{'name': 'userId'}, {'name': 'created_at'}]})
    with pytest.raises(RuntimeError, match=r'structured\.overview'):
        sync.reconcile_conversation_search_index(store=_FakeStore([]), client=client)


def test_it_refuses_to_run_with_no_typesense(monkeypatch):
    monkeypatch.delenv('TYPESENSE_API_KEY', raising=False)
    with pytest.raises(RuntimeError, match='TYPESENSE_HOST/TYPESENSE_API_KEY'):
        sync.reconcile_conversation_search_index(store=_FakeStore([]), client=_FakeClient())


def test_the_cap_is_configurable(monkeypatch):
    monkeypatch.setenv(sync.MAX_DOCUMENTS_ENV, '3')
    client = _FakeClient(schema=sync.CONVERSATIONS_SCHEMA)
    store = _FakeStore([_conv('u1', f'c{i}') for i in range(1, 10)])
    report = sync.reconcile_conversation_search_index(store=store, client=client, page_size=2)
    assert report.scanned == 3 and report.truncated is True
