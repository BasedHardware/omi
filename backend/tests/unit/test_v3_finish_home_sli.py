import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from database import conversations_v3
from scripts import finish_home_readback as readback

# Imported at module load: record admission is a heavy import.
from utils.batch_pipeline import live
from utils.conversations.v3 import finish_home_sli as sli, outline
from utils.conversations.v3.finish import deliberate_finish
from utils.conversations.v3.policy import NATIVE_MANUAL_STOP

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


@pytest.mark.parametrize('header', [None, f'app,{uuid4()},{int(datetime.now(timezone.utc).timestamp() * 1000)}'])
def test_held_out_owner_finish_emits_no_cut(monkeypatch, caplog, header):
    # Home sends a held-out owner (SCA-2918) to legacy Home: the cut must not enter the v3 cohort.
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(sli, 'v3_intake_held_out', lambda uid: uid == 'held')
    headers = {sli.APP_CHANNEL_HEADER: 'beta', **({sli.HEADER: header} if header else {})}
    request = SimpleNamespace(headers=headers)
    with caplog.at_level('INFO'):
        assert sli.from_request('held', request) is None
        assert sli.from_request('owner', request) is not None
    stages = [json.loads(r.message.split(readback.MARKER)[1])['stage'] for r in caplog.records]
    assert stages == (['cut'] if header else [])


def test_holdout_is_asked_only_after_stage_admission(monkeypatch):
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: False)
    monkeypatch.setattr(sli, 'v3_intake_held_out', lambda uid: pytest.fail('holdout read before admission'))
    assert sli.home_cohort('owner') is False


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
        event('eligible', 20, card='card-a'),
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
        event('eligible', 42, card='a-card'),  # Previous notes on a reused card.
        event('window', 45, recording='a-rec', card='a-card'),
        event('eligible', 60, card='a-card'),
        event('eligible', 100, card='a-card'),
        event('binding', 25, finish='b', recording='b-rec'),
        event('route', 30, recording='b-rec', route='batch'),
        event('route', 35, recording='b-rec', route='held'),
        event('window', 85, recording='b-rec', card='b-card'),
        event('eligible', 120, card='b-card'),
        event('binding', 565, finish='d', recording='d-rec'),
        event('window', 575, recording='d-rec', card='d-card'),
        event('eligible', 580, card='d-card'),
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


def _linked_finish(*extra):
    def event(stage, elapsed, **fields):
        return {'stage': stage, 'observed_at': START + timedelta(seconds=elapsed), **fields}

    return [
        event('cut', 1, cut_at=START.isoformat(), finish='f', source='app', basis='client_cut'),
        event('binding', 2, finish='f', recording='rec'),
        event('window', 5, recording='rec', card='card'),
        *(event(stage, elapsed, card='card') for stage, elapsed in extra),
    ]


def test_finish_is_scored_when_the_summary_became_eligible_not_when_home_fetched_it():
    result = readback.readback(_linked_finish(('eligible', 20), ('summary', 90)), START, THROUGH)
    assert result['totals']['within_60s'] == 1
    assert result['totals']['late'] == 0
    assert result['totals']['matched_client_cut_p95_seconds'] == 20
    assert result['home_fetch_validation'] == {
        'eligible': 1,
        'fetched': 1,
        'eligible_card_not_fetched': 0,
        'other_linked_card_fetched': 0,
        'fetched_without_eligible': 0,
        'fetch_after_eligible_p95_seconds': 70,
    }


def test_an_eligible_summary_that_home_never_fetched_is_still_scored():
    result = readback.readback(_linked_finish(('eligible', 20)), START, THROUGH)
    assert result['totals']['within_60s'] == 1
    assert result['totals']['unmatched'] == 0
    assert result['home_fetch_validation']['eligible_card_not_fetched'] == 1
    assert result['home_fetch_validation']['other_linked_card_fetched'] == 0


@pytest.mark.parametrize('fetched', [False, True])
def test_a_summary_that_never_became_eligible_is_a_miss(fetched):
    # Hidden, below the word floor or discarded: the write path never emits ``eligible``.
    result = readback.readback(_linked_finish(*([('summary', 30)] if fetched else [])), START, THROUGH)
    assert result['totals']['finishes'] == 1
    assert result['totals']['within_60s'] == 0
    assert result['totals']['unmatched'] == 1
    assert result['totals']['p95_at_or_below_60s'] is False
    assert result['home_fetch_validation']['fetched_without_eligible'] == int(fetched)


def test_fetch_validation_follows_the_card_that_won_eligibility():
    def event(stage, elapsed, **fields):
        return {'stage': stage, 'observed_at': START + timedelta(seconds=elapsed), **fields}

    # Card A wins eligibility at 20 s but Home never returns it; Home returns linked card B at 30 s.
    events = [
        event('cut', 1, cut_at=START.isoformat(), finish='f', source='app', basis='client_cut'),
        event('binding', 2, finish='f', recording='rec'),
        event('window', 5, recording='rec', card='card-a'),
        event('window', 6, recording='rec', card='card-b'),
        event('eligible', 20, card='card-a'),
        event('eligible', 25, card='card-b'),
        event('summary', 30, card='card-b'),
    ]
    result = readback.readback(events, START, THROUGH)
    assert result['totals']['within_60s'] == 1
    assert result['totals']['matched_client_cut_p95_seconds'] == 20
    assert result['home_fetch_validation'] == {
        'eligible': 1,
        'fetched': 0,
        'eligible_card_not_fetched': 1,
        'other_linked_card_fetched': 1,
        'fetched_without_eligible': 0,
        'fetch_after_eligible_p95_seconds': None,
    }
    # The score never depends on what Home fetched: without the fetch it is the same.
    unfetched = readback.readback(events[:-1], START, THROUGH)
    assert unfetched['totals'] == result['totals']


class _AdmissionStore:
    client = object()


def _admit_record(uid, recording_id, current):
    asyncio.run(live._manual_finish_admitted(_AdmissionStore(), uid, recording_id, current, [UNIT], object(), b'k'))


UNIT = (0.0, 1.0, [{'bucket': 'b', 'path': 'p', 'generation': 1}])
NATIVE_STOP = {'job_id': 'bp_job', 'revision': 1, 'finished_at': START}


def _sli_events(caplog):
    return [
        json.loads(record.getMessage().split(readback.MARKER)[1])
        for record in caplog.records
        if readback.MARKER in record.getMessage()
    ]


def test_native_batch_finish_reads_back_as_the_batch_route(monkeypatch, caplog):
    # End to end through the real emitters: the Finish header's cut, its binding, the confirmed
    # native batch admission, the window and the eligible card, exported and read back.
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(sli, 'v3_intake_held_out', lambda uid: False)
    now = datetime.now(timezone.utc)
    request = SimpleNamespace(
        headers={
            sli.HEADER: f'app,{uuid4()},{int(now.timestamp() * 1000)}',
            sli.APP_CHANNEL_HEADER: 'beta',
        },
    )
    native = {'recording': True, 'v3_manual_end_requested': True, NATIVE_MANUAL_STOP: NATIVE_STOP}
    with caplog.at_level('INFO'):
        finish = sli.from_request('owner', request)
        assert finish is not None
        finish.bind('recording')
        _admit_record('owner', 'recording', native)
        sli.observe_window('owner', 'recording', 'card')
        sli.observe_eligible('owner', 'card')
    entries = [
        {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            'textPayload': record.getMessage(),
        }
        for record in caplog.records
    ]
    start = now.replace(microsecond=0) - timedelta(minutes=1)
    through = start + timedelta(days=1, minutes=1)

    result = readback.readback(readback.observations(entries, through), start, through)

    assert [(row['route'], row['source'], row['finishes']) for row in result['by_route_source']] == [
        ('batch', 'app', 1)
    ]
    assert result['totals']['within_60s'] == 1


def _in_cohort(monkeypatch, member=True):
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: member)
    monkeypatch.setattr(sli, 'v3_intake_held_out', lambda uid: False)


def test_native_batch_admission_names_the_route_once_and_nothing_else(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    _in_cohort(monkeypatch)
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', lambda *a, **k: pytest.fail('native cut promoted'))
    # The app's Finish also asks for the legacy manual end; the native stop must not take that path too.
    native = {'recording': True, 'v3_manual_end_requested': True, NATIVE_MANUAL_STOP: NATIVE_STOP}
    with caplog.at_level('INFO'):
        _admit_record('owner', 'recording', native)
    # The native completion records its own manual-end proof; admission adds only the route.
    assert _sli_events(caplog) == [
        {'stage': 'route', 'recording': sli._key('recording', 'owner', 'recording'), 'route': 'batch'}
    ]


def test_legacy_manual_end_admission_names_the_batch_route_once(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    _in_cohort(monkeypatch)
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'off')
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', lambda *a, **k: False)
    with caplog.at_level('INFO'):
        _admit_record('owner', 'recording', {'recording': True, 'v3_manual_end_requested': True})
        # Neither a natural end nor a non-recording capture names a route.
        _admit_record('owner', 'natural', {'recording': True})
        _admit_record('owner', 'capture', {'v3_manual_end_requested': True, NATIVE_MANUAL_STOP: NATIVE_STOP})
    assert [(event['stage'], event.get('route')) for event in _sli_events(caplog)] == [('route', 'batch')]


# --- SCA-4489 review fixes --------------------------------------------------------------------------------


def _event(stage, elapsed, **fields):
    return {'stage': stage, 'observed_at': START + timedelta(seconds=elapsed), **fields}


def test_already_visible_finish_is_ready_at_its_cut_not_a_miss():
    # The Finish found its card on Home with notes: no eligibility write follows, and none is needed.
    events = [
        _event('cut', 1, cut_at=START.isoformat(), finish='f', source='app', basis='client_cut'),
        _event('binding', 2, finish='f', recording='rec'),
        _event('already_visible', 2, finish='f', card='card'),
        _event('summary', 9, card='card'),
    ]
    result = readback.readback(events, START, THROUGH)
    assert result['totals']['finishes'] == 1
    assert result['totals']['unmatched'] == 0
    assert result['totals']['within_60s'] == 1
    assert result['totals']['matched_client_cut_p95_seconds'] == 0
    assert [(row['route'], row['finishes']) for row in result['by_route_source']] == [('already_visible', 1)]
    assert result['home_fetch_validation']['eligible'] == 1
    assert result['home_fetch_validation']['fetched'] == 1


def test_already_visible_bind_emits_a_scoreable_event(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    _in_cohort(monkeypatch)
    now = datetime.now(timezone.utc)
    request = SimpleNamespace(
        headers={sli.HEADER: f'pendant,{uuid4()},{int(now.timestamp() * 1000)}', sli.APP_CHANNEL_HEADER: 'beta'}
    )
    with caplog.at_level('INFO'):
        finish = sli.from_request('owner', request)
        finish.bind('recording', prove_legacy_manual_end=True, visible_card='card')
    events = _sli_events(caplog)
    assert [e['stage'] for e in events] == ['cut', 'binding', 'already_visible']
    assert events[2] == {
        'stage': 'already_visible',
        'finish': events[0]['finish'],
        'card': sli._key('card', 'owner', 'card'),
    }
    entries = [
        {'timestamp': datetime.fromtimestamp(r.created, tz=timezone.utc).isoformat(), 'textPayload': r.getMessage()}
        for r in caplog.records
    ]
    start = now.replace(microsecond=0) - timedelta(minutes=1)
    through = start + timedelta(days=1, minutes=1)
    result = readback.readback(readback.observations(entries, through), start, through)
    assert result['totals']['within_60s'] == 1 and result['totals']['unmatched'] == 0


def test_legacy_already_visible_finish_is_scored_once_proven(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    _in_cohort(monkeypatch)
    with caplog.at_level('INFO'):
        finish = sli.from_request('owner', SimpleNamespace(headers={sli.APP_CHANNEL_HEADER: 'beta'}))
        finish.bind('recording', prove_legacy_manual_end=True, visible_card='card')
    assert [e['stage'] for e in _sli_events(caplog)] == ['legacy_candidate', 'legacy_manual_end', 'already_visible']


def test_acknowledge_binds_already_visible_with_its_card(monkeypatch):
    from utils.conversations.v3 import finish as v3_finish

    monkeypatch.setattr(v3_finish, 'deserialize_conversation', lambda window: SimpleNamespace())
    monkeypatch.setattr(v3_finish, 'CreateConversationResponse', lambda **kwargs: kwargs)
    monkeypatch.setattr(v3_finish.live, 'has_finish_content', lambda *a: True)
    monkeypatch.setattr(
        v3_finish.metrics, 'FINISH_NO_POINTER', SimpleNamespace(labels=lambda o: SimpleNamespace(inc=lambda: None))
    )
    observed = []

    def observe(recording_id, **kwargs):
        observed.append((recording_id, kwargs))

    v3_finish._acknowledge('owner', {'id': 'card'}, 'already_visible', 'rec', observe)
    v3_finish._acknowledge('owner', {'id': 'card'}, 'already_empty', 'rec', observe)
    assert observed == [('rec', {'visible_card': 'card'})]


def test_route_observations_are_limited_to_the_home_cohort(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    monkeypatch.setenv('CONVERSATIONS_V3_FAST_FINISH', 'off')
    monkeypatch.setattr(conversations_v3, 'promote_manual_end', lambda *a, **k: False)
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: uid != 'stage-outsider')
    monkeypatch.setattr(sli, 'v3_intake_held_out', lambda uid: uid == 'held-out')
    native = {'recording': True, 'v3_manual_end_requested': True, NATIVE_MANUAL_STOP: NATIVE_STOP}
    with caplog.at_level('INFO'):
        for uid in ('stage-outsider', 'held-out'):
            _admit_record(uid, 'recording', native)
            _admit_record(uid, 'recording', {'recording': True, 'v3_manual_end_requested': True})
    assert _sli_events(caplog) == []
    assert sli.measured('held-out') is False and sli.measured('owner') is True
    assert asyncio.run(sli.measured_async('stage-outsider')) is False
    monkeypatch.delenv('CONVERSATIONS_V3_FINISH_HOME_SLI')
    assert sli.measured('owner') is False and asyncio.run(sli.measured_async('owner')) is False


def _reconcile_groups(monkeypatch, uid, *, derive=False, on_open=False):
    from utils.conversations.v3 import service

    held = {'held-recording'}

    def stretches(eligible, now, **kwargs):
        if 'finish_routes' in kwargs:
            kwargs['finish_routes'].update(held)
        return []

    monkeypatch.setattr(service.outline, 'stretches', stretches)
    monkeypatch.setattr(service.manual_cuts, 'enabled', lambda uid: False)
    return asyncio.run(
        service._reconcile_groups(
            uid,
            [],
            START,
            since=None,
            until=None,
            internal_end=None,
            historical_timing=None,
            silence_gap=timedelta(seconds=120),
            lock_delay=timedelta(seconds=120),
            custom_timing=False,
            cohesion=False,
            derive=derive,
            on_open=on_open,
        )
    )


def test_reconcile_measures_only_home_cohort_owners_and_holds_once(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    monkeypatch.setattr(sli, '_held_seen', {})
    monkeypatch.setattr(sli, 'conversations_v3_enabled', lambda uid: True)
    monkeypatch.setattr(sli, 'v3_intake_held_out', lambda uid: uid == 'held-out')
    with caplog.at_level('INFO'):
        assert _reconcile_groups(monkeypatch, 'held-out')[2] is False
        assert _reconcile_groups(monkeypatch, 'owner', derive=True)[2] is False
        assert _sli_events(caplog) == []
        # Three reconcile passes over the same held Finish (one on open) name the held route once.
        assert _reconcile_groups(monkeypatch, 'owner')[2] is True
        assert _reconcile_groups(monkeypatch, 'owner')[2] is True
        assert _reconcile_groups(monkeypatch, 'owner', on_open=True)[2] is True
    assert _sli_events(caplog) == [
        {'stage': 'route', 'recording': sli._key('recording', 'owner', 'held-recording'), 'route': 'held'}
    ]


def test_held_route_repeats_only_after_its_window(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    monkeypatch.setattr(sli, '_held_seen', {})
    clock = iter([0.0, 10.0, sli.HELD_SEEN_SECONDS + 1])
    with caplog.at_level('INFO'):
        for _ in range(3):
            sli.observe_held('owner', ['r'], clock=lambda: next(clock))
    assert [e['route'] for e in _sli_events(caplog)] == ['held', 'held']


def _ended_window(*sources):
    return {'manual_end': True, '_finish_sli_sources': sources}


@pytest.mark.parametrize(
    'prior,was_ended,expected',
    [
        (None, False, {'card': ('a', 'b')}),
        # The stored card was not yet ended: this commit ends it, so it binds.
        ({'id': 'card', 'manual_end': True, 'v3_recording_ids': ['a', 'b']}, False, {'card': ('a', 'b')}),
        # The stored card ended without a Finish cut (silence): the cut is new in this commit.
        ({'id': 'card', 'manual_end': False, 'v3_recording_ids': ['a', 'b']}, True, {'card': ('a', 'b')}),
        # A later pass rewrites the same ended Finish card: nothing new to bind.
        ({'id': 'card', 'manual_end': True, 'v3_recording_ids': ['a', 'b']}, True, {}),
        # Only a recording newly joining the ended card binds.
        ({'id': 'card', 'manual_end': True, 'v3_recording_ids': ['a']}, True, {'card': ('b',)}),
    ],
)
def test_window_binding_is_remembered_only_when_new_in_the_commit(prior, was_ended, expected):
    windows = {}
    sli.remember_window(
        windows,
        enabled=True,
        ended=True,
        window=_ended_window('a', 'b'),
        row={'id': 'card'},
        prior=prior,
        was_ended=was_ended,
    )
    assert windows == expected


def test_repeated_reconcile_commits_emit_one_window_event(monkeypatch, caplog):
    monkeypatch.setenv('CONVERSATIONS_V3_FINISH_HOME_SLI', 'on')
    stored = None
    with caplog.at_level('INFO'):
        for _ in range(3):
            windows = {}
            row = {'id': 'card', 'manual_end': True, 'v3_recording_ids': ['rec']}
            sli.remember_window(
                windows,
                enabled=True,
                ended=True,
                window=_ended_window('rec'),
                row=row,
                prior=stored,
                was_ended=stored is not None,
            )
            sli.observe_windows('owner', [row], windows)
            stored = row
    assert [e['stage'] for e in _sli_events(caplog)] == ['window']
