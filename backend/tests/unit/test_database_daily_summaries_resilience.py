import pytest
from backend.database.daily_summaries import (
    validate_daily_summary_input,
    validate_pagination_input
)
from fastapi import HTTPException

@pytest.mark.parametrize('uid, expected_error', [
    ('', 'uid must be a non-empty string'),
    (None, 'uid must be a non-empty string'),
    (123, 'uid must be a non-empty string'),
    ('  ', 'uid must be a non-empty string'),
])
def test_validate_uid(uid, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_daily_summary_input(uid=uid, summary_id='test', date='2023-01-01', client_device_id='test')
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('summary_id, expected_error', [
    ('', 'summary_id must be a non-empty string'),
    (None, 'summary_id must be a non-empty string'),
    (123, 'summary_id must be a non-empty string'),
])
def test_validate_summary_id(summary_id, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_daily_summary_input(uid='test', summary_id=summary_id, date='2023-01-01', client_device_id='test')
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('date, expected_error', [
    ('invalid-date', 'date must be in YYYY-MM-DD format'),
    (None, 'date must be in YYYY-MM-DD format'),
    ('2023-13-01', 'date must be in YYYY-MM-DD format'),
])
def test_validate_date(date, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_daily_summary_input(uid='test', summary_id='test', date=date, client_device_id='test')
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('client_device_id, expected_error', [
    ('', 'client_device_id must be a non-empty string'),
    (None, 'client_device_id must be a non-empty string'),
    (123, 'client_device_id must be a non-empty string'),
])
def test_validate_client_device_id(client_device_id, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_daily_summary_input(uid='test', summary_id='test', date='2023-01-01', client_device_id=client_device_id)
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('summary_data, expected_error', [
    ('invalid', 'summary_data must be a dictionary or None'),
    (123, 'summary_data must be a dictionary or None'),
])
def test_validate_summary_data(summary_data, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_daily_summary_input(
            uid='test', summary_id='test', date='2023-01-01',
            client_device_id='test', summary_data=summary_data
        )
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('counters, expected_error', [
    ({'invalid': 'str'}, 'counters\[invalid\] must be int or float'),
    ({'valid': 'str'}, 'counters\[valid\] must be int or float'),
])
def test_validate_counters(counters, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_daily_summary_input(
            uid='test', summary_id='test', date='2023-01-01',
            client_device_id='test', counters=counters
        )
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('limit, expected_error', [
    (0, 'limit must be between 1 and 100'),
    (101, 'limit must be between 1 and 100'),
    (-1, 'limit must be between 1 and 100'),
])
def test_validate_limit(limit, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_pagination_input(limit=limit, offset=0)
    assert expected_error in str(excinfo.value.detail)

@pytest.mark.parametrize('offset, expected_error', [
    (-1, 'offset must be >= 0'),
])
def test_validate_offset(offset, expected_error):
    with pytest.raises(HTTPException) as excinfo:
        validate_pagination_input(limit=10, offset=offset)
    assert expected_error in str(excinfo.value.detail)

def test_valid_inputs():
    input_data = {
        'uid': 'test_uid',
        'summary_id': 'test_summary',
        'date': '2023-01-01',
        'client_device_id': 'test_device',
        'summary_data': {'key': 'value'},
        'counters': {'count': 10}
    }
    result = validate_daily_summary_input(**input_data)
    assert result.uid == 'test_uid'
    assert result.summary_id == 'test_summary'

    pagination_data = {'limit': 50, 'offset': 10}
    result = validate_pagination_input(**pagination_data)
    assert result.limit == 50
    assert result.offset == 10
