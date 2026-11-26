from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts import finish_home_readback as readback
from utils.conversations.v3 import finish_home_sli as sli, outline
from utils.conversations.v3.finish import deliberate_finish

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
    assert [record['stage'] for record in records] == ['legacy_candidate']
    assert records[0]['source'] == 'unknown'
    assert records[0]['basis'] == 'server_cut'
    assert 'owner' not in caplog.text
    assert 'recording-id' not in caplog.text


def test_client_cut_uses_the_same_key_as_finish_header(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    cut_id = str(uuid4())
    cut_at = datetime.now(timezone.utc)
    with caplog.at_level('INFO'):
        sli.observe_client_cut('owner', cut_id, cut_at, 'app')
    event = json.loads(caplog.records[0].message.split(readback.MARKER)[1])
    assert event['stage'] == 'cut'
    assert event['finish'] == sli._key('finish', 'owner', cut_id.replace('-', ''))
    assert event['source'] == 'app'
    assert event['basis'] == 'client_cut'
    assert 'owner' not in caplog.text
    assert cut_id not in caplog.text


def test_readback_only_admits_proven_legacy_candidates():
    def event(stage, seconds, **fields):
        return {'stage': stage, 'observed_at': START + timedelta(seconds=seconds), **fields}

    events = [
        event(
            'legacy_candidate',
            1,
            finish='legacy-a',
            recording='recording-a',
            cut_at=(START + timedelta(seconds=1)).isoformat(),
            source='unknown',
            basis='server_cut',
        ),
        event(
            'legacy_candidate',
            2,
            finish='legacy-b',
            recording='recording-b',
            cut_at=(START + timedelta(seconds=2)).isoformat(),
            source='unknown',
            basis='server_cut',
        ),
        event('legacy_manual_end', 3, recording='recording-a'),
        event('window', 4, recording='recording-a', card='card-a'),
        event('summary', 20, card='card-a'),
    ]
    result = readback.readback(events, START, THROUGH)
    assert result['totals']['finishes'] == 1
    assert result['totals']['timing_unknown'] == 1
    assert result['by_route_source'][0]['source'] == 'unknown'


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


@pytest.mark.parametrize(
    'outcome,deliberate',
    [
        ('cut', True),
        ('requested', True),
        ('already_cut', True),
        ('consumed', True),
        ('recording_cut', True),
        ('named_recording_cut', True),
        ('named_recording_requested', True),
        # Outcomes of a Finish that moved to a newer capture (``newer_*``, ``newer_dual_*``).
        ('newer_recording_cut', True),
        ('newer_recording_requested', True),
        ('newer_already_requested', True),
        ('newer_consumed', True),
        ('newer_dual_cut', True),
        ('newer_dual_already_requested', True),
        ('already_visible', False),
        ('already_empty', False),
        ('resolved_empty', False),
        ('named_not_finishable', False),
        ('named_superseded', False),
        ('newer_recording_ineligible', False),
        ('newer_dual_resolved_empty', False),
        ('no_live_window', False),
    ],
)
def test_deliberate_finish_counts_named_and_newer_paths(outcome, deliberate):
    assert deliberate_finish(outcome) is deliberate


def test_owner_end_cut_carries_the_finish_it_answered():
    now = START + timedelta(minutes=10)
    finished = {
        'id': 'a',
        'started_at': START,
        'source': 'omi',
        'recording': True,
        'finished_at': START + timedelta(seconds=8),
        'v3_manual_end': True,
        'transcript_segments': [{'text': 'first part', 'start': 0, 'end': 8, 'is_user': True}],
    }
    later = {
        'id': 'b',
        'started_at': START + timedelta(seconds=10),
        'source': 'omi',
        'recording': True,
        'transcript_segments': [{'text': 'second part', 'start': 0, 'end': 15, 'is_user': True}],
    }
    end = START + timedelta(seconds=30)
    (group,) = outline.stretches([finished, later], now, manual_cuts=[end], finish_routes=set())
    assert group['manual_end'] is True
    assert group['_finish_sli_sources'] == ('a',)
    (unmeasured,) = outline.stretches([finished, later], now, manual_cuts=[end])
    assert unmeasured['manual_end'] is True and '_finish_sli_sources' not in unmeasured


@pytest.mark.parametrize(
    'updates,visible',
    [
        ({}, True),
        ({'is_locked': True}, False),
        ({'sync_merged_into': 'survivor'}, False),
        ({'backfilled': True}, False),
        ({'manual_end': False}, False),
        ({'tile_state': 'writing'}, False),
        ({'structured': {'title': 'Plan'}}, False),
    ],
)
def test_home_summary_requires_a_finished_readable_card(monkeypatch, updates, visible):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    observed = []
    monkeypatch.setattr(sli, 'observe_summary', lambda uid, cid: observed.append(cid))
    row = {
        'id': 'c',
        'v3_derived': True,
        'manual_end': True,
        'v3_notes_written': True,
        'tile_state': 'done',
        'status': 'completed',
        'structured': {'title': 'Plan', 'overview': 'We set a date.'},
    }
    sli.observe_home_summaries('owner', [row | updates])
    assert observed == (['c'] if visible else [])
