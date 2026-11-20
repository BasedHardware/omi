"""v3 corpus ingest, contract export, pairing by recording and pipeline selection (synthetic only)."""

import json

import pytest

from testing.pipeline_lab.baseline.compare import baseline_view
from testing.pipeline_lab.contracts import ConversationRecord
from testing.pipeline_lab.seed.corpus import add_day
from testing.pipeline_lab.seed.synthetic import SYNTHETIC_SOURCE_UID, write_synthetic_snapshot
from testing.pipeline_lab.store import Store
from testing.pipeline_lab.v3.corpus import day_has_v3, read_day_recordings
from testing.pipeline_lab.v3.export import home_visible, normalize_v3_conversation, pair_by_recordings
from testing.pipeline_lab.v3.select import PipelineRefused, entry_module, select_pipeline

DAY = '2026-03-14'


@pytest.fixture()
def store(tmp_path):
    return Store(root=tmp_path / 'store', verdicts_root=tmp_path / 'verdicts')


def test_add_day_ingests_the_v3_export(tmp_path, store):
    snap = write_synthetic_snapshot(tmp_path / 'snap', day=DAY, v3=True)
    result = add_day(store, snap, DAY, 'UTC')
    meta = result['v3']
    assert meta['recordings'] == 5 and meta['recordings_live'] == 5 and meta['recordings_backfill_donors'] == 0
    assert meta['v3_conversations'] == 3 and meta['v3_visible'] == 1 and meta['prior_recordings'] == 1
    assert meta['memories'] == 1 and meta['live_since'].startswith(DAY)
    day_dir = store.day_dir(DAY)
    assert day_has_v3(store, DAY)
    assert [r['id'] for r in read_day_recordings(store, DAY)] == ['rec-a', 'rec-b', 'rec-c', 'rec-live', 'rec-gone']
    baseline = [json.loads(line) for line in (day_dir / 'baseline' / 'v3_conversations.jsonl').read_text().splitlines()]
    assert [b['id'] for b in baseline] == ['v3-seeds', 'v3-water', 'v3-festival']
    festival = baseline[-1]
    assert festival['recordings'] == ['rec-c'] and festival['v3']['visible'] is True
    assert festival['memories'] and festival['structured']['sections']
    assert baseline[0]['v3']['home_hidden_reason'] == 'below_word_minimum'
    ConversationRecord.from_json(festival)  # the contract shape round-trips
    start_ids = [
        json.loads(line)['id'] for line in (day_dir / 'start_state' / 'conversations.jsonl').read_text().splitlines()
    ]
    assert 'rec-prev' in start_ids and 'rec-a' not in start_ids
    prior = next(
        json.loads(line)
        for line in (day_dir / 'start_state' / 'conversations.jsonl').read_text().splitlines()
        if json.loads(line)['id'] == 'rec-prev'
    )
    assert prior['v3_pending'] is False
    for path in store.root.rglob('*'):
        if path.is_file():
            assert SYNTHETIC_SOURCE_UID not in path.read_text(errors='ignore'), path


def test_add_day_without_export_has_no_v3(tmp_path, store):
    snap = write_synthetic_snapshot(tmp_path / 'snap', day=DAY)
    assert add_day(store, snap, DAY, 'UTC')['v3'] is None
    assert not day_has_v3(store, DAY)
    with pytest.raises(FileNotFoundError):
        read_day_recordings(store, DAY)


def row(cid, start, end, recordings, **extra):
    out = {
        'id': cid,
        'v3_derived': True,
        'started_at': start,
        'finished_at': end,
        'v3_recording_ids': recordings,
        'status': 'completed',
        'structured': {'title': cid, 'sections': [{'heading': 'h', 'body_markdown': 'b'}], 'participants': []},
        'transcript_segments': [{'text': 'hi', 'start': 0, 'end': 1, 'is_user': True}],
    }
    out.update(extra)
    return out


def test_normalize_v3_conversation_carries_recordings_and_home_state():
    out = normalize_v3_conversation(
        row(
            'x',
            '2026-03-14T09:00:00+00:00',
            '2026-03-14T09:10:00+00:00',
            ['r1', 'r2'],
            home_hidden=True,
            home_hidden_reason='media',
            kind='media',
            v3_process_failed=True,
            v3_process_failure_reason='outline',
        ),
        baseline_id='p1',
        baseline_ids=['p1', 'p2'],
    )
    assert out['lane'] == 'v3' and out['recordings'] == ['r1', 'r2'] and out['baseline_ids'] == ['p1', 'p2']
    assert out['v3']['visible'] is False and out['v3']['kind'] == 'media' and out['v3']['process_failed']
    assert out['structured']['sections'] == [{'heading': 'h', 'body_markdown': 'b'}]
    assert 'participants' not in out['structured']  # empty lists stay out
    assert home_visible({'status': 'completed'}) and not home_visible({'status': 'failed'})
    assert not home_visible({'discarded': True}) and not home_visible({'deleted': True})


def test_pair_by_recordings_handles_split_and_merge():
    production = [
        row('p1', '2026-03-14T09:00:00+00:00', '2026-03-14T09:05:00+00:00', ['r1']),
        row('p2', '2026-03-14T09:05:00+00:00', '2026-03-14T09:12:00+00:00', ['r1', 'r2']),
        row('p3', '2026-03-14T11:00:00+00:00', '2026-03-14T11:30:00+00:00', ['r3']),
    ]
    replay = [
        # merged what production split
        row('m', '2026-03-14T09:00:00+00:00', '2026-03-14T09:12:00+00:00', ['r1', 'r2']),
        # shares r3 but does not overlap in time -> no pair
        row('n', '2026-03-14T12:00:00+00:00', '2026-03-14T12:10:00+00:00', ['r3']),
        row('o', '2026-03-14T13:00:00+00:00', '2026-03-14T13:10:00+00:00', ['r9']),
    ]
    pairs = pair_by_recordings(replay, production)
    assert pairs['m'] == ('p2', ['p1', 'p2'])
    assert pairs['n'] == (None, []) and pairs['o'] == (None, [])
    # contract rows (``recordings``) pair the same way
    contract = [normalize_v3_conversation(r) for r in replay]
    assert pair_by_recordings(contract, production)['m'][0] == 'p2'


def test_baseline_view_compares_home_visibility_and_kind():
    prod = normalize_v3_conversation(
        row('p', '2026-03-14T09:00:00+00:00', '2026-03-14T09:10:00+00:00', ['r1'], home_hidden=True, kind='background')
    )
    rep = normalize_v3_conversation(
        row('x', '2026-03-14T09:00:00+00:00', '2026-03-14T09:10:00+00:00', ['r1'], kind='conversation'),
        baseline_id='p',
    )
    view = baseline_view([rep], [prod])
    entry = view['conversations'][0]
    # v3 visibility is the ``home`` field (the outline kind shows up as the hidden reason when both are hidden)
    assert entry['match'] == 'id' and 'home' in entry['substantive_fields']
    assert 'home_added' in view['groups'][0]['tags']
    classic = {'id': 'c', 'started_at': '2026-03-14T09:00:00+00:00', 'finished_at': '2026-03-14T09:10:00+00:00'}
    assert baseline_view([dict(classic)], [dict(classic)])['conversations'][0]['status'] == 'same'


def test_select_pipeline_rules():
    on = {'env': {'CONVERSATIONS_V3': 'on'}}
    assert select_pipeline(on, day_has_v3=True)[0] == 'v3'
    assert select_pipeline(on, day_has_v3=False)[0] == 'classic'
    assert select_pipeline({'env': {'CONVERSATIONS_V3': 'off'}}, day_has_v3=True)[0] == 'classic'
    assert select_pipeline({}, day_has_v3=True)[0] == 'classic'
    assert select_pipeline({**on, 'model_config': {'pipeline': 'classic'}}, day_has_v3=True)[0] == 'classic'
    assert select_pipeline({'model_config': {'pipeline': 'v3'}}, day_has_v3=True)[0] == 'v3'
    with pytest.raises(PipelineRefused):
        select_pipeline({'model_config': {'pipeline': 'v3'}}, day_has_v3=False)
    with pytest.raises(PipelineRefused):
        select_pipeline({'model_config': {'pipeline': 'v2'}}, day_has_v3=True)
    assert entry_module('v3').endswith('v3.entry') and entry_module('classic').endswith('chain.entry')
