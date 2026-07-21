"""Behavioral contracts for the shared Firestore read boundary."""

from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import patch

import pytest
from pydantic import BaseModel

import database.read_boundary as read_boundary


class _Record(BaseModel):
    id: str
    count: int


@dataclass
class _Reference:
    path: str


class _Snapshot:
    def __init__(self, document_id: str, payload: object, *, exists: bool = True):
        self.id = document_id
        self._payload = payload
        self.exists = exists
        self.reference = _Reference(f'users/test/items/{document_id}')

    def to_dict(self):
        return self._payload


def test_parse_snapshot_or_none_injects_document_id_and_redacts_input(caplog, monkeypatch):
    secret = 'private task description must never be logged'

    with patch.object(read_boundary, 'record_fallback') as fallback:
        parsed = read_boundary.parse_snapshot_or_none(_Record, _Snapshot('valid', {'count': 1}), document_id_field='id')
        malformed = read_boundary.parse_snapshot_or_none(_Record, _Snapshot('bad', {'description': secret}))

    assert parsed == _Record(id='valid', count=1)
    assert malformed is None
    assert fallback.call_count == 1
    assert fallback.call_args.kwargs == {
        'component': 'firestore_read',
        'from_mode': 'firestore_document',
        'to_mode': 'skip_malformed_document',
        'reason': 'malformed_doc',
        'outcome': 'degraded',
        'log': read_boundary.logger,
    }
    assert 'users/test/items/bad' in caplog.text
    assert secret not in caplog.text
    assert 'validation_fields=' in caplog.text
    assert 'validation_types=' in caplog.text


def test_parse_snapshots_drops_each_malformed_snapshot_and_keeps_valid_entries(monkeypatch):
    with patch.object(read_boundary, 'record_fallback') as fallback:
        parsed = read_boundary.parse_snapshots(
            _Record,
            [
                _Snapshot('one', {'id': 'one', 'count': 1}),
                _Snapshot('bad', {'id': 'bad'}),
                _Snapshot('two', {'id': 'two', 'count': 2}),
            ],
        )

    assert parsed == [_Record(id='one', count=1), _Record(id='two', count=2)]
    assert fallback.call_count == 1


def test_iter_parsed_snapshots_is_lazy_and_drops_malformed_entries(monkeypatch):
    snapshots = iter([_Snapshot('one', {'id': 'one', 'count': 1}), _Snapshot('bad', {'id': 'bad'})])

    with patch.object(read_boundary, 'record_fallback') as fallback:
        parsed = read_boundary.iter_parsed_snapshots(_Record, snapshots)

        assert isinstance(parsed, Iterator)
        assert next(parsed) == _Record(id='one', count=1)
        assert fallback.call_count == 0
        assert list(parsed) == []
        assert fallback.call_count == 1


def test_parse_snapshot_strict_raises_typed_error_without_fallback(monkeypatch):
    with patch.object(read_boundary, 'record_fallback') as fallback:
        with pytest.raises(read_boundary.MalformedDocError, match='users/test/items/bad') as error:
            read_boundary.parse_snapshot_strict(_Record, _Snapshot('bad', {'id': 'bad'}))

    assert error.value.error_types == ('missing',)
    assert error.value.error_fields == ('count',)
    assert fallback.call_count == 0


def test_boundary_converts_type_error_from_payload_transform_to_fail_open(monkeypatch):
    with patch.object(read_boundary, 'record_fallback') as fallback:
        result = read_boundary.parse_snapshot_or_none(
            _Record,
            _Snapshot('bad', {'id': 'bad', 'count': 1}),
            payload_from_snapshot=lambda _snapshot: None,  # type: ignore[return-value]
        )

    assert result is None
    assert fallback.call_count == 1
