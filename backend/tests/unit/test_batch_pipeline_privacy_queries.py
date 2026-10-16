"""Boundaries for the single-field batch privacy/retention query builders."""

import logging
import sys
from types import SimpleNamespace

import pytest

from database import batch_pipeline_privacy_queries as queries


class RecordingCollection:
    """Minimal Firestore collection stand-in that records the path it was built with."""

    def __init__(self, client, path):
        self.client = client
        self.path = path
        self.filters = []
        self.appended = None

    def where(self, filter=None):
        self.filters.append(filter)
        return self

    def start_after(self, cursor):
        self.appended = cursor
        return self

    def limit(self, bound):
        self.client.limits.append(bound)
        return self

    def stream(self, transaction=None):
        self.client.streams.append({'path': self.path, 'transaction': transaction})
        if self.client.fail_stream:
            raise RuntimeError('synthetic Firestore timeout')
        return [f'{self.path}/row']


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


@pytest.mark.parametrize(
    'value,expected',
    [
        ('  owner  ', 'owner'),
        ('owner', 'owner'),
    ],
)
def test_identifier_is_stripped_of_surrounding_whitespace(value, expected):
    assert queries.sanitize_identifier(value, 'namespace') == expected


@pytest.mark.parametrize('value', ['', '   ', None, 7, True])
def test_identifier_rejects_empty_or_non_string_values(value):
    with pytest.raises(ValueError, match='namespace must be a non-empty string'):
        queries.sanitize_identifier(value, 'namespace')


@pytest.mark.parametrize('value,expected', [(0, 1), (1, 1), (250, 100), (100, 100)])
def test_limit_is_clamped_to_the_documented_ceiling(value, expected):
    assert queries.bounded_limit(value) == expected


def test_limit_rejects_non_integer_and_boolean_values():
    with pytest.raises(ValueError, match='limit must be an integer'):
        queries.bounded_limit(True)


def test_owner_documents_builds_a_sanitized_parenthesized_path_and_clamps_page_size():
    client = RecordingClient()
    queries.owner_documents(client, ' batch_pipeline_prod ', ' jobs ', ' owner-key ', limit=250)
    assert client.collections[0].path == 'batch_pipeline_prod_jobs'
    assert client.limits == [100]
    assert client.streams[0]['path'] == 'batch_pipeline_prod_jobs'


def test_owner_documents_honors_an_explicit_smaller_page_size():
    client = RecordingClient()
    queries.owner_documents(client, 'ns', 'jobs', 'owner', limit=25)
    assert client.limits == [25]


def test_transactional_reads_forward_the_caller_client_and_transaction():
    client = RecordingClient()
    transaction = object()
    queries.segment_artifacts(client, 'ns', 'segment', transaction)
    assert client.streams == [{'path': 'ns_artifacts', 'transaction': transaction}]


@pytest.mark.parametrize(
    'call',
    [
        lambda client: queries.owner_documents(client, 'ns', 'jobs', 'owner'),
        lambda client: queries.predecessor_documents(client, 'ns', 'segment', None),
        lambda client: queries.segment_artifacts(client, 'ns', 'segment', None),
        lambda client: queries.due_artifacts(client, 'ns', 'now'),
    ],
)
def test_stream_failures_degrade_to_an_empty_page_instead_of_crashing_the_sweep(call):
    client = RecordingClient(fail_stream=True)
    assert call(client) == []


def test_stream_failure_is_logged_not_swallowed_silently(caplog):
    client = RecordingClient(fail_stream=True)
    with caplog.at_level(logging.WARNING, logger='database.batch_pipeline_privacy_queries'):
        queries.due_artifacts(client, 'ns', 'now')
    assert 'batch privacy query stream failed' in caplog.text


def test_client_falls_back_to_the_shared_client_when_omitted(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(queries, 'get_firestore_client', lambda: client, raising=False)
    sentinel = RecordingClient()
    monkeypatch.setitem(__import__('sys').modules, 'database._client', sentinel)
    assert queries.resolve_client(None) is client
