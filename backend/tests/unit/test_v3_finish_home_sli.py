from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import finish_home_readback as readback
from utils.conversations.v3 import finish_home_sli as sli

START = datetime(2026, 11, 26, tzinfo=timezone.utc)
THROUGH = START + timedelta(days=1, minutes=1)


def test_cut_is_scoped_and_retry_uses_the_same_opaque_key(monkeypatch, caplog):
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: uid == 'owner')
    request = SimpleNamespace(
        headers={
            sli.HEADER: f'pendant,{uuid4()},{int(datetime.now(timezone.utc).timestamp() * 1000)}',
            sli.APP_CHANNEL_HEADER: 'beta',
        },
    )
    monkeypatch.delenv('CONVERSATIONS_V3_FINISH_HOME_SLI', raising=False)
    assert sli.from_request('owner', request) is None
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    assert sli.from_request('outsider', request) is None
    assert (
        sli.from_request('owner', SimpleNamespace(headers={**request.headers, sli.APP_CHANNEL_HEADER: 'store'})) is None
    )
    with caplog.at_level('INFO'):
        for _ in range(2):
            finish = sli.from_request('owner', request)
            assert finish is not None
            assert finish.basis == 'client_cut'
            finish.bind('recording-id')
    events = [json.loads(record.message.split(readback.MARKER)[1]) for record in caplog.records]
    assert [e['stage'] for e in events] == ['cut', 'binding', 'cut', 'binding']
    assert events[0]['source'] == 'pendant'
    assert events[:2] == events[2:]
    assert 'owner' not in caplog.text
    assert 'recording-id' not in caplog.text
    assert request.headers[sli.HEADER] not in caplog.text


def test_legacy_finish_requires_a_bound_recording(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: True)
    request = SimpleNamespace(headers={sli.APP_CHANNEL_HEADER: 'beta'})
    with caplog.at_level('INFO'):
        finish = sli.from_request('owner', request)
        assert finish is not None
        assert not caplog.records
        finish.bind('recording-id')
    records = [json.loads(record.message.split(readback.MARKER)[1]) for record in caplog.records]
    assert records[0]['source'] == 'unknown'
    assert records[0]['basis'] == 'server_cut'
    assert records[0]['finish'] == records[1]['finish']


def test_readback_keeps_missing_and_late_finishes_in_the_cohort():
    def event(stage, elapsed, **fields):
        return {'stage': stage, 'observed_at': START + timedelta(seconds=elapsed), **fields}

    def cut(finish, at, source, basis='client_cut'):
        return event(
            'cut', at + 1, cut_at=(START + timedelta(seconds=at)).isoformat(), finish=finish, source=source, basis=basis
        )

    events = [
        cut('a', 0, 'app'),
        cut('a', 0, 'app'),
        cut('b', 20, 'pendant'),
        cut('c', 500, 'unknown'),
        cut('d', 560, 'unknown', 'server_cut'),
        cut('next-day', 86400, 'app'),
        event('binding', 5, finish='a', recording='a-rec'),
        event('binding', 7, finish='a', recording='wrong-rec'),
        event('route', 8, recording='a-rec', route='batch'),
        event('route', 40, recording='a-rec', route='fast'),
        event('summary', 42, card='a-card'),  # Previous notes on a reused card.
        event('window', 45, recording='a-rec', card='a-card'),
        event('summary', 60, card='a-card'),
        event('summary', 100, card='a-card'),
        event('binding', 25, finish='b', recording='b-rec'),
        event('route', 30, recording='b-rec', route='batch'),
        event('route', 35, recording='b-rec', route='held'),
        event('window', 85, recording='b-rec', card='b-card'),
        event('summary', 120, card='b-card'),
        event('binding', 565, finish='d', recording='d-rec'),
        event('window', 575, recording='d-rec', card='d-card'),
        event('summary', 580, card='d-card'),
    ]
    result = readback.readback(reversed(events), START, THROUGH)
    assert result['totals'] == {
        'finishes': 4,
        'within_60s': 1,
        'late': 1,
        'unmatched': 1,
        'timing_unknown': 1,
        'matched_client_cut_p95_seconds': 100,
        'p95_seconds': None,
        'p95_at_or_below_60s': False,
    }
    assert [(row['route'], row['source']) for row in result['by_route_source']] == [
        ('fast', 'app'),
        ('held', 'pendant'),
        ('unknown', 'unknown'),
    ]
    assert result['by_route_source'][0]['p95_seconds'] == 60
    with pytest.raises(ValueError, match='full 60 seconds'):
        readback.readback(events, START, THROUGH - timedelta(microseconds=1))


def test_all_finish_p95_counts_right_censored_finishes():
    assert readback.counts([(50, True)] * 19 + [(None, True)], 60)['p95_seconds'] == 50
    assert readback.counts([(70, True)] * 19 + [(None, True)], 60)['p95_seconds'] is None
