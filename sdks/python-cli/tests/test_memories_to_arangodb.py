#!/usr/bin/env python3
"""Unit tests for ArangoDB memory exporter."""

import json
import pytest
from memories_to_arangodb import ArangoDBExporter


@pytest.fixture
def sample_memory():
    return {
        'id': 'test-memory-123',
        'type': 'memory',
        'timestamp': 1625097600,
        'content': 'Sample memory content',
        'metadata': {
            'tags': ['test', 'sample'],
            'source': 'wearable'
        }
    }


def test_escape_string():
    exporter = ArangoDBExporter('test')
    assert exporter.escape_string('hello\"world') == '"hello\\\"world"'
    assert exporter.escape_string('simple') == '"simple"'


def test_format_array():
    exporter = ArangoDBExporter('test')
    assert exporter.format_array([1, 2, 3]) == '[1, 2, 3]'
    assert exporter.format_array(['a', 'b\"c']) == '[
        "a",
        "b\\\"c"
    ]'


def test_generate_aql(sample_memory):
    exporter = ArangoDBExporter('memories')
    aql = exporter.generate_aql(sample_memory)
    assert 'UPSERT "test-memory-123" IN memories' in aql
    assert 'type: "memory"' in aql
    assert 'content: "Sample memory content"' in aql
    assert 'metadata: {"tags": ["test", "sample"], "source": "wearable"}' in aql


def test_deduplication():
    exporter = ArangoDBExporter('memories')
    sample_memory = {
        'id': 'duplicate-id',
        'type': 'memory',
        'content': 'content'
    }
    exporter.generate_aql(sample_memory)  # First insertion
    assert exporter.generate_aql(sample_memory) == ""  # Duplicate skipped


def test_missing_id():
    exporter = ArangoDBExporter('memories')
    with pytest.raises(ValueError, match="Memory must contain 'id' field"):
        exporter.generate_aql({'type': 'memory', 'content': 'no id'})


def test_force_overwrite():
    exporter = ArangoDBExporter('memories', force=True)
    sample_memory = {
        'id': 'forced-id',
        'type': 'memory',
        'content': 'content'
    }
    assert exporter.generate_aql(sample_memory) != ""  # Allowed with --force
    assert exporter.generate_aql(sample_memory) != ""  # Second call also allowed