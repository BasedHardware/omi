from datetime import datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, ValidationError

from models.conversation import SetConversationActionItemsStateRequest, SetConversationEventsStateRequest
from utils.request_validation import (
    HistoryDays,
    ImageChunkEnvelope,
    MAX_IMAGE_CHUNK_TOTAL,
    NonNegativeOffset,
    PositiveLimit,
    parse_form_json,
    parse_sync_filename_timestamp,
    validate_calendar_date,
)


class _FormPayload(BaseModel):
    name: str = Field(min_length=1)
    count: int = Field(ge=1)


def test_parse_form_json_validates_model_json():
    payload = parse_form_json(_FormPayload, '{"name":"omi","count":2}', 'app_data')

    assert payload == _FormPayload(name='omi', count=2)


@pytest.mark.parametrize('raw_value', ['not-json', '[]', '{"name":"omi","count":0}'])
def test_parse_form_json_rejects_invalid_form_json(raw_value):
    with pytest.raises(HTTPException) as exc_info:
        parse_form_json(_FormPayload, raw_value, 'app_data')

    assert exc_info.value.status_code == 422
    assert 'app_data' in exc_info.value.detail


def test_parse_form_json_dict_rejects_non_object_json():
    with pytest.raises(HTTPException) as exc_info:
        parse_form_json(dict, '[1, 2, 3]', 'persona_data')

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize('value', ['2024-01-01', '2024-02-29'])
def test_validate_calendar_date_accepts_real_dates(value):
    assert validate_calendar_date(value) == value


@pytest.mark.parametrize('value', ['2024-02-30', '2024-13-01', 'not-a-date'])
def test_validate_calendar_date_rejects_invalid_dates(value):
    with pytest.raises(HTTPException) as exc_info:
        validate_calendar_date(value)

    assert exc_info.value.status_code == 422


@pytest.mark.parametrize('suffix', ['1704067200', '1704067200000'])
def test_parse_sync_filename_timestamp_accepts_seconds_and_millis(suffix):
    assert parse_sync_filename_timestamp(f'audio_{suffix}.bin') == 1_704_067_200
    assert parse_sync_filename_timestamp(f'/tmp/vad/{suffix}.wav') == 1_704_067_200


def test_parse_sync_filename_timestamp_accepts_fractional_vad_segment_names():
    assert parse_sync_filename_timestamp('/tmp/vad/1704067200.0.wav') == 1_704_067_200
    assert parse_sync_filename_timestamp('/tmp/vad/1704067200.5.wav') == 1_704_067_200.5


@pytest.mark.parametrize(
    'filename',
    [
        'audio_not-a-timestamp.bin',
        'audio_0.bin',
        'audio_999999999999999999999999.bin',
    ],
)
def test_parse_sync_filename_timestamp_rejects_invalid_or_out_of_range_values(filename):
    with pytest.raises(ValueError):
        parse_sync_filename_timestamp(filename)


def test_parse_sync_filename_timestamp_rejects_future_values():
    future = int(datetime.now(timezone.utc).timestamp()) + 3600

    with pytest.raises(ValueError):
        parse_sync_filename_timestamp(f'audio_{future}.bin')


@pytest.mark.parametrize(
    'payload',
    [
        {'id': 'img', 'index': -1, 'total': 2, 'data': 'a'},
        {'id': 'img', 'index': 2, 'total': 2, 'data': 'a'},
        {'id': 'img', 'index': 0, 'total': 0, 'data': 'a'},
        {'id': '', 'index': 0, 'total': 1, 'data': 'a'},
        {'id': 'img', 'index': 0, 'total': 1, 'data': ''},
    ],
)
def test_image_chunk_envelope_rejects_invalid_boundaries(payload):
    with pytest.raises(ValidationError):
        ImageChunkEnvelope.model_validate(payload)


def test_image_chunk_envelope_rejects_inconsistent_cached_total():
    chunk = ImageChunkEnvelope(id='img', index=1, total=2, data='b')

    with pytest.raises(ValueError):
        chunk.validate_against_cached_total(3)


def test_image_chunk_envelope_allows_mobile_photo_chunk_counts_above_legacy_cap():
    chunk = ImageChunkEnvelope(id='img', index=300, total=512, data='b')

    assert chunk.total == 512
    assert MAX_IMAGE_CHUNK_TOTAL >= 512


def test_parallel_action_item_arrays_must_have_matching_lengths():
    with pytest.raises(ValidationError):
        SetConversationActionItemsStateRequest(items_idx=[0, 1], values=[True])


def test_parallel_event_arrays_must_have_matching_lengths():
    with pytest.raises(ValidationError):
        SetConversationEventsStateRequest(events_idx=[0], values=[True, False])


def test_common_query_contracts_reject_invalid_values_before_endpoint_runs():
    app = FastAPI()
    calls = []

    @app.get('/items')
    def items(limit: PositiveLimit = 100, offset: NonNegativeOffset = 0, days: HistoryDays = 30):
        calls.append((limit, offset, days))
        return {'ok': True}

    client = TestClient(app)

    assert client.get('/items?limit=1&offset=0&days=1').status_code == 200
    for query in ['limit=0', 'limit=1001', 'offset=-1', 'days=0', 'days=366']:
        response = client.get(f'/items?{query}')
        assert response.status_code == 422

    assert calls == [(1, 0, 1)]
