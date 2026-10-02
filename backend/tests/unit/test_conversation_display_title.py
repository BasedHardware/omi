"""Response-only title projection, including the production HTTP read boundaries."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from utils.conversations import display_title


def row(**overrides):
    return {
        'id': 'synthetic-title-test',
        'created_at': datetime(2026, 10, 1, 15, 12, tzinfo=timezone.utc),
        'started_at': None,
        'finished_at': None,
        'status': 'completed',
        'discarded': False,
        'structured': {'title': '', 'overview': 'Keep these notes'},
        'transcript_segments': [],
        **overrides,
    }


@pytest.fixture(autouse=True)
def fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(display_title, 'record_fallback', lambda **kwargs: calls.append(kwargs))
    return calls


def test_shared_transcript_parity():
    fixture = json.loads(
        (Path(__file__).resolve().parents[3] / 'contracts/parity/deterministic_title.json').read_text()
    )
    for case in fixture['cases']:
        if case['expected_title'] is None:
            continue
        payload = row(transcript_segments=[{'text': text} for text in case['segments']])
        assert display_title.apply_display_title(payload)['structured']['title'] == case['expected_title'], case['name']


@pytest.mark.parametrize('raw', [[], b'unreadable-compressed-data', 'encrypted-data', None])
def test_no_decoded_text_uses_labelled_utc_date_without_mutating_shared_fields(raw, fallback):
    payload = row(transcript_segments=raw)
    structured = payload['structured']
    display_title.apply_display_title(payload)
    assert payload['structured']['title'] == 'Recording · 2026-10-01 15:12 UTC'
    assert payload['structured']['overview'] == 'Keep these notes'
    assert structured['title'] == ''
    assert payload['transcript_segments'] == raw
    assert 'summary_retryable' not in payload
    assert fallback == [
        dict(
            component='conversation_title',
            from_mode='none',
            to_mode='deterministic',
            reason='malformed_doc',
            outcome='degraded',
        )
    ]


@pytest.mark.parametrize(
    'overrides',
    [
        {'status': 'processing'},
        {'discarded': True},
        {'deleted': True},
        {'is_locked': True},
        {'structured': {'title': 'My title'}},
    ],
)
def test_ineligible_and_titled_rows_are_unchanged(overrides, fallback):
    payload = row(**overrides)
    before = deepcopy(payload)
    assert display_title.apply_display_title(payload) == before
    assert fallback == []


def test_user_title_wins_and_invalid_date_stays_readable(fallback):
    assert display_title.apply_display_title(row(user_title='User edit'))['structured']['title'] == 'User edit'
    assert fallback == []
    assert display_title.apply_display_title(row(created_at='invalid'))['structured']['title'] == 'Recording'
    payload = row(started_at='2026-10-01T08:12:00-07:00')
    assert display_title.apply_display_title(payload)['structured']['title'] == 'Recording · 2026-10-01 15:12 UTC'


@pytest.fixture
def router():
    import routers.conversations as module

    return module


@pytest.mark.parametrize('path', ['/v1/conversations', '/v1/conversations/synthetic-title-test'])
@pytest.mark.parametrize('with_transcript', [True, False])
def test_http_read_titles_response_without_writing_or_changing_raw_row(monkeypatch, path, router, with_transcript):

    stored = row(
        transcript_segments=(
            [{'text': 'Plan the release.', 'speaker': 'SPEAKER_00', 'start': 0, 'end': 1, 'is_user': False}]
            if with_transcript
            else []
        ),
        summary_retryable=True,
    )
    before = deepcopy(stored)
    monkeypatch.setattr(
        router.conversations_db, 'get_conversations_without_photos', lambda *args, **kwargs: [deepcopy(stored)]
    )
    monkeypatch.setattr(router.conversations_db, 'get_conversation', lambda *args, **kwargs: deepcopy(stored))
    monkeypatch.setattr(router, '_dispatch_first_open_work', lambda *args: None)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'synthetic-user'
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 200, response.text
    body = response.json()
    result = body[0] if isinstance(body, list) else body
    assert result['structured']['title'] == (
        'Plan the release.' if with_transcript else 'Recording · 2026-10-01 15:12 UTC'
    )
    assert result['summary_retryable'] is True
    assert stored == before
