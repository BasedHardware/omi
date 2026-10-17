"""Hermetic unit tests for batch privacy and retention query builders."""

import pytest
from google.cloud.firestore_v1 import FieldFilter

from database import batch_pipeline_privacy_queries as queries


class RecordingCollection:
    """Minimal Firestore collection test double recording path, filters, and stream calls."""

    def __init__(self, client, path):
        self.client = client
        self.path = path
        self.filters = []
        self.cursor = None

    def where(self, filter=None):
        self.filters.append(filter)
        return self

    def start_after(self, cursor):
        self.cursor = cursor
        return self

    def limit(self, bound):
        self.client.limits.append(bound)
        return self

    def stream(self, transaction=None):
        self.client.streams.append({'path': self.path, 'transaction': transaction})
        if self.client.fail_stream:
            raise RuntimeError('synthetic Firestore timeout')
        return [f'{self.path}/doc_1', f'{self.path}/doc_2']


class RecordingClient:
    def __init__(self, fail_stream=False):
        self.collections = []
        self.limits = []
        self.streams = []
        self.fail_stream = fail_stream

    def collection(self, path):
        collection = RecordingCollection(self, path)
        self.collections.append(collection)
        return collection


# --- Identifier Sanitization Tests ---


@pytest.mark.parametrize(
    'value,expected',
    [
        ('  batch_pipeline_prod  ', 'batch_pipeline_prod'),
        ('jobs', 'jobs'),
        (' owner_key_123 ', 'owner_key_123'),
        ('segment_abc', 'segment_abc'),
    ],
)
def test_identifier_is_stripped_of_surrounding_whitespace(value, expected):
    assert queries.sanitize_identifier(value, 'test_field') == expected


@pytest.mark.parametrize(
    'value',
    [
        '',
        '   ',
        None,
        7,
        True,
        False,
        [],
        {},
    ],
)
def test_identifier_rejects_empty_or_non_string_values(value):
    with pytest.raises(ValueError, match='test_field must be a non-empty string'):
        queries.sanitize_identifier(value, 'test_field')


# --- Bounded Limit Tests ---


@pytest.mark.parametrize(
    'value,expected',
    [
        (0, 1),
        (-10, 1),
        (1, 1),
        (50, 50),
        (100, 100),
        (101, 100),
        (500, 100),
    ],
)
def test_limit_is_clamped_to_documented_ceiling(value, expected):
    assert queries.bounded_limit(value) == expected


@pytest.mark.parametrize('value', [True, False, '100', 12.5, None, [], {}])
def test_limit_rejects_non_integer_and_boolean_values(value):
    with pytest.raises(ValueError, match='limit must be an integer'):
        queries.bounded_limit(value)


# --- Client Validation Tests ---


@pytest.mark.parametrize(
    'builder_call',
    [
        lambda: queries.owner_documents(None, 'ns', 'jobs', 'owner'),
        lambda: queries.predecessor_documents(None, 'ns', 'seg_1', object()),
        lambda: queries.segment_artifacts(None, 'ns', 'seg_1', object()),
        lambda: queries.due_artifacts(None, 'ns', '2026-10-17T00:00:00Z'),
    ],
)
def test_builders_reject_none_client(builder_call):
    with pytest.raises(ValueError, match='client must not be None'):
        builder_call()


# --- Query Construction & Forwarding Tests ---


def test_owner_documents_builds_sanitized_collection_and_clamps_limit():
    client = RecordingClient()
    docs = queries.owner_documents(client, '  batch_prod  ', '  jobs  ', '  user_key  ', limit=300)
    assert len(client.collections) == 1
    assert client.collections[0].path == 'batch_prod_jobs'
    assert client.limits == [100]
    assert len(client.collections[0].filters) == 1
    filter_obj = client.collections[0].filters[0]
    assert isinstance(filter_obj, FieldFilter)
    assert filter_obj.field_path == 'owner_key'
    assert filter_obj.op_string == '=='
    assert filter_obj.value == 'user_key'
    assert len(docs) == 2


def test_owner_documents_honors_cursor_after():
    client = RecordingClient()
    sentinel_cursor = object()
    queries.owner_documents(client, 'ns', 'jobs', 'user_key', after=sentinel_cursor)
    assert client.collections[0].cursor is sentinel_cursor


def test_owner_documents_honors_smaller_page_size():
    client = RecordingClient()
    queries.owner_documents(client, 'ns', 'jobs', 'user_key', limit=42)
    assert client.limits == [42]


def test_predecessor_documents_builds_sanitized_query_and_forwards_transaction():
    client = RecordingClient()
    transaction = object()
    docs = queries.predecessor_documents(client, '  batch_prod  ', '  segment_99  ', transaction)
    assert client.collections[0].path == 'batch_prod_jobs'
    assert client.limits == [1]
    filters = client.collections[0].filters
    assert len(filters) == 2
    assert filters[0].field_path == 'next'
    assert filters[0].value == 'segment_99'
    assert filters[1].field_path == 'state'
    assert filters[1].value == 'ready'
    assert client.streams == [{'path': 'batch_prod_jobs', 'transaction': transaction}]
    assert len(docs) == 2


def test_segment_artifacts_builds_sanitized_query_and_forwards_transaction():
    client = RecordingClient()
    transaction = object()
    docs = queries.segment_artifacts(client, '  batch_prod  ', '  segment_99  ', transaction)
    assert client.collections[0].path == 'batch_prod_artifacts'
    assert client.limits == [256]
    filters = client.collections[0].filters
    assert len(filters) == 1
    assert filters[0].field_path == 'segment_id'
    assert filters[0].value == 'segment_99'
    assert client.streams == [{'path': 'batch_prod_artifacts', 'transaction': transaction}]
    assert len(docs) == 2


def test_due_artifacts_builds_sanitized_query_with_bounded_limit():
    client = RecordingClient()
    timestamp = '2026-10-17T12:00:00Z'
    docs = queries.due_artifacts(client, '  batch_prod  ', timestamp, limit=50)
    assert client.collections[0].path == 'batch_prod_artifacts'
    assert client.limits == [50]
    filters = client.collections[0].filters
    assert len(filters) == 1
    assert filters[0].field_path == 'cleanup_after'
    assert filters[0].op_string == '<='
    assert filters[0].value == timestamp
    assert client.streams == [{'path': 'batch_prod_artifacts', 'transaction': None}]
    assert len(docs) == 2


# --- Crash-and-Retry Safety Invariant Tests ---


@pytest.mark.parametrize(
    'builder_call',
    [
        lambda client: queries.owner_documents(client, 'ns', 'jobs', 'owner'),
        lambda client: queries.predecessor_documents(client, 'ns', 'seg_1', object()),
        lambda client: queries.segment_artifacts(client, 'ns', 'seg_1', object()),
        lambda client: queries.due_artifacts(client, 'ns', '2026-10-17T00:00:00Z'),
    ],
)
def test_stream_errors_propagate_to_preserve_crash_and_retry_semantics(builder_call):
    """Stream exceptions must NOT be swallowed into empty lists.

    In purge_batch_owner, an empty list signals end-of-data and marks privacy purge
    complete. Propagating stream errors ensures transient failures crash and trigger
    safe retries rather than silently leaving un-erased user data behind.
    """
    failing_client = RecordingClient(fail_stream=True)
    with pytest.raises(RuntimeError, match='synthetic Firestore timeout'):
        builder_call(failing_client)
