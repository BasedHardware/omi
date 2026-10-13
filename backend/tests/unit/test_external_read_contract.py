"""Behavioral coverage for additive Developer API pagination and UTC contracts."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from utils.external_read_contract import pagination_headers, reject_unknown_query, utc_window


def test_unknown_query_is_rejected_without_echoing_input():
    with pytest.raises(HTTPException) as exc:
        reject_unknown_query(SimpleNamespace(query_params={'query-secret': 'private'}), {'limit'})
    assert exc.value.status_code == 400
    assert 'secret' not in exc.value.detail and 'private' not in exc.value.detail
    reject_unknown_query(SimpleNamespace(query_params={'limit': '20'}), {'limit'})
    # Widely used cache-busters are inert for these read endpoints and have
    # historically been accepted by the permissive query parser.
    reject_unknown_query(
        SimpleNamespace(query_params={'_': '1700000000', 'cacheBust': 'refresh'}),
        {'limit'},
    )


def test_array_pagination_headers_report_limit_and_continuation():
    response = SimpleNamespace(headers={})
    pagination_headers(response, limit=200, has_more=True, next_offset=200, next_cursor='opaque')
    assert response.headers == {
        'X-Omi-Effective-Limit': '200',
        'X-Omi-Has-More': 'true',
        'X-Omi-Next-Offset': '200',
        'X-Omi-Next-Cursor': 'opaque',
    }
    terminal = SimpleNamespace(headers={})
    pagination_headers(terminal, limit=200, has_more=False, next_offset=200)
    assert terminal.headers['X-Omi-Has-More'] == 'false'
    assert 'X-Omi-Next-Offset' not in terminal.headers


def test_naive_dates_mean_utc_and_offsets_preserve_instants():
    start, end = utc_window(datetime(2026, 10, 1), datetime(2026, 10, 2, tzinfo=timezone(timedelta(hours=7))))
    assert start.tzinfo == timezone.utc
    assert end.timestamp() == datetime(2026, 10, 1, 17, tzinfo=timezone.utc).timestamp()
    with pytest.raises(HTTPException) as exc:
        utc_window(end, start)
    assert exc.value.status_code == 400
