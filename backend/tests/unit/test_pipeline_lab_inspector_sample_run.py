"""Pipeline-lab inspector: the synthetic sample run follows the DESIGN store contract. Synthetic only."""

import hashlib
import json
import stat
import struct

import pytest

from testing.pipeline_lab.inspector import sample_run, views
from testing.pipeline_lab.inspector.reader import ID_PATTERN, Reader, content_key, seconds_between

CONVERSATION_KEYS = {
    'id',
    'baseline_id',
    'lane',
    'started_at',
    'finished_at',
    'discarded',
    'discard_reason',
    'language',
    'segments',
    'structured',
    'action_items',
    'memories',
    'notifications',
    'llm_call_ids',
    'evaluable',
}
RUN_KEYS = {
    'run_id',
    'day_id',
    'ref',
    'backend_tree',
    'overlay',
    'start_state',
    'status',
    'started_at',
    'finished_at',
    'spend_usd',
    'budget_usd',
    'timings',
    'stages',
    'warnings',
}
CALL_KEYS = {
    'id',
    'at',
    'stage',
    'conversation_id',
    'feature',
    'model',
    'prompt',
    'output',
    'tokens_in',
    'tokens_out',
    'usd',
    'cache_hit',
    'ms',
}


@pytest.fixture(scope='module')
def sample(tmp_path_factory):
    base = tmp_path_factory.mktemp('plab-sample')
    result = sample_run.write_sample(base / 'store', base / 'verdicts', audio_rate=1000)
    return base, result


def _jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_corpus_day_and_baseline_layout(sample):
    base, result = sample
    day_dir = base / 'store' / 'corpus' / sample_run.DAY_ID
    day = json.loads((day_dir / 'day.json').read_text())
    assert set(day) >= {'day_id', 'date', 'timezone', 'source_snapshot', 'start_state_snapshot', 'coverage'}
    assert set(day['coverage']) >= {'audio_seconds', 'conversations', 'with_audio', 'lanes', 'gaps'}
    assert len(day['coverage']['gaps']) == 2 and all(g['kind'] == 'unknown' for g in day['coverage']['gaps'])
    for name in ('conversations.jsonl', 'memories.jsonl', 'action_items.jsonl', 'notifications.jsonl'):
        assert (day_dir / 'baseline' / name).is_file()
    assert json.loads((day_dir / 'baseline' / 'daily_summary.json').read_text())['title']
    baseline = _jsonl(day_dir / 'baseline' / 'conversations.jsonl')
    assert len(baseline) == result['baseline_conversations'] == day['coverage']['conversations']
    for row in baseline:
        assert set(row) >= CONVERSATION_KEYS
        assert row['baseline_id'] is None


def test_audio_index_points_at_valid_wavs_covering_each_clip(sample):
    base, result = sample
    audio_dir = base / 'store' / 'corpus' / sample_run.DAY_ID / 'audio'
    index = json.loads((audio_dir / 'index.json').read_text())
    assert isinstance(index, list) and len(index) == result['audio_clips']
    for entry in index:
        assert set(entry) >= {'conversation_id', 'path', 'start', 'end', 'codec', 'sample_rate'}
        body = (audio_dir / entry['path']).read_bytes()
        assert body[:4] == b'RIFF' and body[8:12] == b'WAVE'
        rate = struct.unpack('<I', body[24:28])[0]
        data_len = struct.unpack('<I', body[40:44])[0]
        assert rate == entry['sample_rate'] == 1000
        assert abs(data_len / rate - seconds_between(entry['start'], entry['end'])) < 0.01
        assert set(body[44:]) - {0x80}, 'clip has tones, not only silence'


def test_runs_follow_the_contract_and_cross_reference(sample):
    base, _ = sample
    for run_id in (sample_run.RUN_ID, sample_run.MAIN_RUN_ID):
        run_dir = base / 'store' / 'runs' / run_id
        run = json.loads((run_dir / 'run.json').read_text())
        assert set(run) >= RUN_KEYS
        assert run['start_state'] == 'approximate' and run['status'] == 'complete'
        calls = _jsonl(run_dir / 'llm_calls.jsonl')
        assert calls and all(set(c) >= CALL_KEYS for c in calls)
        call_ids = {c['id'] for c in calls}
        assert len(call_ids) == len(calls)
        assert run['spend_usd'] == pytest.approx(sum(c['usd'] for c in calls), abs=1e-3)
        convs = [json.loads(p.read_text()) for p in (run_dir / 'conversations').glob('*.json')]
        for conv in convs:
            assert set(conv) >= CONVERSATION_KEYS
            assert ID_PATTERN.fullmatch(conv['id'])
            assert set(conv['llm_call_ids']) <= call_ids
            for seg in conv['segments']:
                assert set(seg) >= {'start', 'end', 'speaker', 'speaker_name', 'is_user', 'text'}
                assert 0 <= seg['start'] < seg['end']
            for item in conv['action_items']:
                assert item['key'] == content_key('task', item['description'])
            for item in conv['memories']:
                assert item['key'] == content_key('memory', item['content'])
        day = json.loads((run_dir / 'day.json').read_text())
        assert set(day) >= {'daily_summary', 'goals', 'memory_delta', 'notifications'}
        for name in ('vendor_log.jsonl', 'decisions.jsonl'):
            assert _jsonl(run_dir / name)


def test_variant_run_exercises_every_inspector_state(sample):
    base, _ = sample
    reader = Reader(base / 'store', base / 'verdicts')
    view = reader.comparison(reader.run(sample_run.RUN_ID))
    kinds = {kind for kind, n in view['digest']['kinds'].items() if n}
    assert kinds == {'same', 'content', 'merge', 'split', 'new', 'missing'}
    tags = {tag for tag, n in view['digest']['tags'].items() if n}
    assert tags >= {
        'boundary',
        'summary',
        'transcript',
        'tasks',
        'memories',
        'pushes',
        'discard',
        'home_dropped',
        'home_added',
    }
    by_id = {c['id']: c for c in reader.conversations(sample_run.RUN_ID)}
    rows = [{'replay': by_id[i]} for g in view['groups'] for i in g['replay']]
    assert any(len(row['replay'].get('baseline_ids') or []) == 2 for row in rows), 'a merge'
    claimed = [row['replay']['baseline_id'] for row in rows if row['replay']['baseline_id']]
    assert len(claimed) != len(set(claimed)), 'a split'
    assert any(row['replay']['discarded'] for row in rows) and any(not row['replay']['discarded'] for row in rows)
    assert any(row['replay']['evaluable']['boundaries'] is False for row in rows)
    assert sum(len(row['replay']['notifications']) for row in rows) >= 3


def test_files_are_private_and_free_of_private_paths(sample):
    base, _ = sample
    store = base / 'store'
    for path in [store, *store.rglob('*')]:
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == (0o700 if path.is_dir() else 0o600), path
        if path.suffix in ('.json', '.jsonl'):
            text = path.read_text()
            assert '/Users/' not in text and '/Volumes/' not in text


def test_sample_verdicts_name_real_items(sample):
    base, result = sample
    rows = _jsonl(base / 'verdicts' / 'verdicts.jsonl')
    assert len(rows) == result['verdicts'] >= 3
    reader = Reader(base / 'store', base / 'verdicts')

    run = reader.run(sample_run.RUN_ID)
    for row in rows:
        assert row['mark'] in ('good', 'bad')
        views.locate_item(reader, run, row['conversation_id'], row['item_kind'], row['item_key'])


def test_content_key_matches_the_contract_recipe():
    expected = hashlib.sha256('task\x00"buy a 12 mm washer"'.encode('utf-8')).hexdigest()[:16]
    assert content_key('task', '  Buy a 12 mm washer. ') == expected


def test_sample_is_deterministic(tmp_path):
    a = sample_run.write_sample(tmp_path / 'a', audio_rate=500)
    b = sample_run.write_sample(tmp_path / 'b', audio_rate=500)
    assert a['runs'] == b['runs']
    left = (tmp_path / 'a' / 'runs' / sample_run.RUN_ID / 'llm_calls.jsonl').read_text()
    right = (tmp_path / 'b' / 'runs' / sample_run.RUN_ID / 'llm_calls.jsonl').read_text()
    assert left == right


def test_refuses_to_write_inside_a_git_tree(tmp_path):
    (tmp_path / '.git').mkdir()
    with pytest.raises(SystemExit):
        sample_run.write_sample(tmp_path / 'store')


def test_core_contract_round_trip_when_available(sample):
    contracts = pytest.importorskip('testing.pipeline_lab.contracts')
    base, _ = sample
    run_dir = base / 'store' / 'runs' / sample_run.RUN_ID
    contracts.RunRecord.from_json(json.loads((run_dir / 'run.json').read_text()))
    for path in (run_dir / 'conversations').glob('*.json'):
        record = contracts.ConversationRecord.from_json(json.loads(path.read_text()))
        for item in record.action_items:
            assert item.key == contracts.task_key(item.description)
