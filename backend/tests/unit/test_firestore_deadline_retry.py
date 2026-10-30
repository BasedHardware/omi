"""Real-SDK regression for deadline mapping on budgeted Firestore streams.

google-cloud-firestore 2.20.0's ``Query._retry_query_after_exception`` and
``AggregationQuery._retry_query_after_exception`` require a ``Retry`` object:
on every mid-stream ``GoogleAPICallError`` they evaluate
``retry._predicate(exc)``; with ``retry=None`` that attribute lookup itself
raises ``AttributeError`` and masks the real transport failure. Budgeted list
reads therefore pass ``database.firestore_retry.FIRESTORE_NO_RETRY``, an
explicit policy whose predicate rejects every error, so a stream cut by the
budget-derived deadline surfaces as ``ListReadBudgetExhausted('deadline')``
after exactly one RPC attempt while non-deadline errors propagate unchanged.

The tests below build a real ``firestore.Client`` on anonymous credentials
and a synthetic project, and stub only the transport seam
(``client._firestore_api``): query prep, the stream generator, snapshot
decoding, and the SDK's own retry hook all run for real. No network, no
emulator, no user data.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest
from google.api_core.exceptions import DeadlineExceeded, PermissionDenied, ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers
from google.cloud.firestore_v1.aggregation import AggregationQuery
from google.cloud.firestore_v1.query import Query
from google.cloud.firestore_v1.types import document as document_pb
from google.cloud.firestore_v1.types import firestore as firestore_pb

import database.action_items as action_items_db
import database.users as users_db
from database.firestore_retry import FIRESTORE_NO_RETRY
from utils.other.list_budget import (
    OMI_LIST_TRUNCATED_HEADER,
    OMI_LIST_TRUNCATED_VALUE,
    ListReadBudget,
    ListReadBudgetExhausted,
    apply_truncation_header,
    budgeted_stream_iter,
    budgeted_stream_list,
)

_UID = 'synthetic-uid'
_ITEMS_PATH = f'users/{_UID}/items'


class _SyntheticApi:
    """Only seam the real SDK talks to: the gapic surface behind ``client._firestore_api``.

    ``run_query`` / ``run_aggregation_query`` record their call kwargs and hand
    back an iterator of real response protos followed by the configured
    mid-stream failure, so the SDK's ``_make_stream`` consumes it through the
    real ``_retry_query_after_exception`` hook.
    """

    def __init__(self):
        self.run_query_calls: List[dict] = []
        self.run_aggregation_calls: List[dict] = []
        self.query_responses: List[Any] = []
        self.query_error: Optional[BaseException] = None
        self.aggregation_responses: List[Any] = []
        self.aggregation_error: Optional[BaseException] = None

    @staticmethod
    def _replay(responses, error):
        for response in responses:
            yield response
        if error is not None:
            raise error

    def run_query(self, request=None, metadata=None, **kwargs):
        self.run_query_calls.append({'request': request, 'metadata': metadata, **kwargs})
        return self._replay(self.query_responses, self.query_error)

    def run_aggregation_query(self, request=None, metadata=None, **kwargs):
        self.run_aggregation_calls.append({'request': request, 'metadata': metadata, **kwargs})
        return self._replay(self.aggregation_responses, self.aggregation_error)


def _client() -> tuple:
    client = firestore.Client(project='synthetic-deadline-project', credentials=AnonymousCredentials())
    api = _SyntheticApi()
    client._firestore_api_internal = api
    return client, api


def _items_query(client) -> Query:
    return client.collection('users').document(_UID).collection('items')._query()


def _document_response(client, doc_id: str, data: dict):
    name = f"{client._database_string}/documents/{_ITEMS_PATH}/{doc_id}"
    return firestore_pb.RunQueryResponse(document=document_pb.Document(name=name, fields=_helpers.encode_dict(data)))


def _budget(seconds: float = 24.0) -> ListReadBudget:
    return ListReadBudget(deadline_monotonic=seconds, clock=lambda: 0.0)


def _spy_retry_hook(monkeypatch, query_class) -> List[dict]:
    calls: List[dict] = []
    original = query_class._retry_query_after_exception

    def spy(self, exc, retry, transaction):
        calls.append({'exc': exc, 'retry': retry})
        return original(self, exc, retry, transaction)

    monkeypatch.setattr(query_class, '_retry_query_after_exception', spy)
    return calls


def _assert_truncation_header(budget: ListReadBudget) -> None:
    headers: dict = {}
    apply_truncation_header(headers, budget)
    assert headers[OMI_LIST_TRUNCATED_HEADER] == OMI_LIST_TRUNCATED_VALUE


def test_no_retry_policy_rejects_every_error():
    for error in (
        DeadlineExceeded('d'),
        ServiceUnavailable('u'),
        PermissionDenied('p'),
        ValueError('v'),
    ):
        assert FIRESTORE_NO_RETRY._predicate(error) is False


@pytest.mark.parametrize('docs_before_deadline', [0, 2])
def test_budgeted_stream_list_deadline_maps_to_typed_exhaustion(monkeypatch, docs_before_deadline):
    client, api = _client()
    api.query_responses = [
        _document_response(client, f'doc-{index}', {'n': index, 'completed': False})
        for index in range(docs_before_deadline)
    ]
    api.query_error = DeadlineExceeded('budget-derived rpc deadline')
    hook_calls = _spy_retry_hook(monkeypatch, Query)
    budget = _budget()

    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        budgeted_stream_list(_items_query(client), budget)

    assert excinfo.value.reason == 'deadline'
    assert [snapshot.id for snapshot in excinfo.value.partial_snapshots] == [
        f'doc-{index}' for index in range(docs_before_deadline)
    ]
    assert budget.truncated and budget.exhaustion_reason == 'deadline'
    assert budget.docs_scanned == docs_before_deadline
    # One RPC attempt: the no-retry policy declined the stream restart after
    # the SDK's own retry hook ran.
    assert len(api.run_query_calls) == 1
    assert len(hook_calls) == 1
    assert isinstance(hook_calls[0]['exc'], DeadlineExceeded)
    assert hook_calls[0]['retry'] is FIRESTORE_NO_RETRY
    assert api.run_query_calls[0]['retry'] is FIRESTORE_NO_RETRY
    assert api.run_query_calls[0]['timeout'] == pytest.approx(24.0)
    _assert_truncation_header(budget)


@pytest.mark.parametrize('docs_before_deadline', [0, 2])
def test_budgeted_stream_iter_deadline_keeps_prefix_then_exhausts(monkeypatch, docs_before_deadline):
    client, api = _client()
    api.query_responses = [
        _document_response(client, f'doc-{index}', {'n': index, 'completed': False})
        for index in range(docs_before_deadline)
    ]
    api.query_error = DeadlineExceeded('budget-derived rpc deadline')
    hook_calls = _spy_retry_hook(monkeypatch, Query)
    budget = _budget()

    yielded = []
    with pytest.raises(ListReadBudgetExhausted) as excinfo:
        for snapshot in budgeted_stream_iter(_items_query(client), budget):
            yielded.append(snapshot)

    assert excinfo.value.reason == 'deadline'
    assert [snapshot.id for snapshot in yielded] == [f'doc-{index}' for index in range(docs_before_deadline)]
    assert budget.truncated and budget.exhaustion_reason == 'deadline'
    assert budget.docs_scanned == docs_before_deadline
    assert len(api.run_query_calls) == 1
    assert len(hook_calls) == 1
    assert isinstance(hook_calls[0]['exc'], DeadlineExceeded)
    assert hook_calls[0]['retry'] is FIRESTORE_NO_RETRY
    _assert_truncation_header(budget)


@pytest.mark.parametrize(
    'stream_fn',
    [budgeted_stream_list, budgeted_stream_iter],
    ids=['list', 'iter'],
)
@pytest.mark.parametrize(
    'error',
    [ServiceUnavailable('transient transport'), PermissionDenied('denied')],
    ids=['service-unavailable', 'permission-denied'],
)
def test_budgeted_streams_reraise_nondeadline_errors_unchanged(monkeypatch, stream_fn, error):
    client, api = _client()
    api.query_responses = [_document_response(client, 'doc-0', {'n': 0})]
    api.query_error = error
    hook_calls = _spy_retry_hook(monkeypatch, Query)
    budget = _budget()

    yielded = []
    with pytest.raises(type(error)) as excinfo:
        for snapshot in stream_fn(_items_query(client), budget):
            yielded.append(snapshot)

    # The SDK hook ran, declined, and re-raised the original error object:
    # no truncation mapping, no restart.
    assert excinfo.value is error
    assert not budget.truncated
    assert len(api.run_query_calls) == 1
    assert len(hook_calls) == 1
    assert hook_calls[0]['exc'] is error
    assert hook_calls[0]['retry'] is FIRESTORE_NO_RETRY


def test_count_query_reraises_deadline_through_real_aggregation(monkeypatch):
    client, api = _client()
    api.aggregation_error = DeadlineExceeded('aggregation rpc deadline')
    hook_calls = _spy_retry_hook(monkeypatch, AggregationQuery)
    budget = _budget()

    with pytest.raises(DeadlineExceeded):
        action_items_db._count_query(_items_query(client), budget=budget)

    # _count_query owns no deadline mapping; the harvest handler below marks
    # the budget. One attempt, predicate declined, original error surfaced.
    assert not budget.truncated
    assert len(api.run_aggregation_calls) == 1
    assert len(hook_calls) == 1
    assert hook_calls[0]['retry'] is FIRESTORE_NO_RETRY


def test_aggregation_deadline_marks_budget_and_skips_legacy_scan(monkeypatch):
    client, api = _client()
    api.aggregation_error = DeadlineExceeded('aggregation rpc deadline')
    hook_calls = _spy_retry_hook(monkeypatch, AggregationQuery)
    budget = _budget()

    base_query_calls = []

    def base_query_fn():
        query = _items_query(client)
        base_query_calls.append(query)
        return query

    active = [
        {
            'id': 'a-2',
            'completed': False,
            'due_at': None,
            'created_at': datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
        {
            'id': 'a-1',
            'completed': False,
            'due_at': None,
            'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
    ]
    seen = {item['id'] for item in active}

    result, total_docs = action_items_db._harvest_legacy_docs(base_query_fn, budget, 5, seen, list(active), True)

    # The deadline reached the legacy-probe handler: budget marked, no further
    # legacy scan, and the already-fetched active prefix is preserved.
    assert [item['id'] for item in result] == ['a-2', 'a-1']
    assert budget.truncated and budget.exhaustion_reason == 'deadline'
    assert len(base_query_calls) == 1
    assert len(api.run_aggregation_calls) == 1
    assert len(hook_calls) == 1
    assert hook_calls[0]['retry'] is FIRESTORE_NO_RETRY
    assert total_docs == 0


def test_users_bounded_setting_read_uses_shared_no_retry_policy(monkeypatch):
    captured = {}

    class _Ref:
        def get(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(to_dict=lambda: {'meeting_note_screenshots_enabled': False})

    class _Db:
        def collection(self, name):
            assert name == 'users'
            return self

        def document(self, uid):
            assert uid == _UID
            return _Ref()

    monkeypatch.setattr(users_db, 'db', _Db())
    assert users_db.get_meeting_note_screenshots_enabled(_UID, rpc_timeout=1.5) is False
    assert captured == {'timeout': 1.5, 'retry': FIRESTORE_NO_RETRY}
