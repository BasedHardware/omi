"""Pipeline-lab run store: private dirs, atomic writes, runs, cache, verdict root. Synthetic only."""

import os
import stat
import threading

import pytest

from testing.pipeline_lab import contracts as c
from testing.pipeline_lab import store as s


def _mode(path):
    return stat.S_IMODE(os.lstat(path).st_mode)


@pytest.fixture
def lab(tmp_path):
    return s.Store.open(tmp_path / 'lab' / 'root', tmp_path / 'verdicts')


def test_open_creates_private_roots(lab, tmp_path):
    assert _mode(lab.root) == 0o700
    assert _mode(tmp_path / 'lab') == 0o700  # created parents are private too
    assert _mode(lab.verdicts_root) == 0o700
    for name in ('corpus', 'cache', 'runs'):
        assert (lab.root / name).is_dir()


def test_refuses_root_inside_a_git_tree(tmp_path):
    (tmp_path / 'repo' / '.git').mkdir(parents=True)
    with pytest.raises(s.StoreRefused):
        s.Store.open(tmp_path / 'repo' / 'lab', tmp_path / 'verdicts')


def test_refuses_group_readable_existing_root(tmp_path):
    root = tmp_path / 'open'
    root.mkdir(mode=0o755)
    os.chmod(root, 0o755)
    with pytest.raises(s.StoreRefused):
        s.Store.open(root, tmp_path / 'verdicts')


def test_refuses_symlinked_root(tmp_path):
    real = tmp_path / 'real'
    real.mkdir(mode=0o700)
    (tmp_path / 'link').symlink_to(real)
    with pytest.raises(s.StoreRefused):
        s.ensure_private_dir(tmp_path / 'link')


def test_env_roots(monkeypatch, tmp_path):
    monkeypatch.setenv(s.ROOT_ENV, str(tmp_path / 'r'))
    monkeypatch.setenv(s.VERDICTS_ENV, str(tmp_path / 'v'))
    lab = s.Store.open()
    assert lab.root == tmp_path / 'r' and lab.verdicts_root == tmp_path / 'v'


def test_atomic_write_is_private_and_leaves_no_temp(tmp_path):
    target = tmp_path / 'd' / 'x.json'
    s.atomic_write_json(target, {'a': 1})
    s.atomic_write_json(target, {'a': 2})
    assert s.read_json(target) == {'a': 2}
    assert _mode(target) == 0o600
    assert [p.name for p in target.parent.iterdir()] == ['x.json']


@pytest.mark.parametrize('bad', ['', '..', '../x', 'a/b', '.hidden', 'a..b', 'x' * 200])
def test_unsafe_ids_are_refused(lab, bad):
    with pytest.raises(s.StoreRefused):
        lab.run_dir(bad)


def test_audio_path_stays_inside_the_day(lab):
    assert lab.audio_path('d1', 'sub/a.m4a') == lab.audio_dir('d1') / 'sub' / 'a.m4a'
    for bad in ('../x.m4a', '/etc/passwd', 'a/../../b'):
        with pytest.raises(s.StoreRefused):
            lab.audio_path('d1', bad)


def test_corpus_round_trip(lab):
    day = c.CorpusDay(day_id='d1', date='2026-01-15', timezone='UTC')
    lab.write_day(day)
    lab.write_day(c.CorpusDay(day_id='d0', date='2026-01-14', timezone='UTC'))
    assert lab.read_day('d1') == day
    assert [d.day_id for d in lab.list_days()] == ['d0', 'd1']
    lab.write_baseline('d1', 'conversations.jsonl', [c.ConversationRecord(id='b1', started_at='t')])
    assert lab.baseline_conversations('d1')[0].id == 'b1'
    with pytest.raises(s.StoreRefused):
        lab.write_baseline('d1', 'other.jsonl', [])
    entry = c.AudioIndexEntry(conversation_id='b1', path='b1.m4a', start='a', end='b', codec='aac', sample_rate=16000)
    lab.write_audio_index('d1', [entry])
    assert lab.read_audio_index('d1') == [entry]
    with pytest.raises(FileNotFoundError):
        lab.read_day('missing')


def test_runs_create_update_list(lab):
    lab.create_run(c.RunRecord(run_id='r-old', day_id='d1', ref='a', started_at='2026-01-01T00:00:00Z'))
    lab.create_run(c.RunRecord(run_id='r-new', day_id='d1', ref='b', started_at='2026-01-02T00:00:00Z'))
    lab.create_run(c.RunRecord(run_id='r-other', day_id='d2', ref='b', started_at='2026-01-03T00:00:00Z'))
    with pytest.raises(s.StoreRefused):
        lab.create_run(c.RunRecord(run_id='r-old', day_id='d1', ref='a'))
    assert [r.run_id for r in lab.list_runs('d1')] == ['r-new', 'r-old']
    updated = lab.update_run('r-old', lambda run: setattr(run, 'status', 'complete'))
    assert updated.status == 'complete' and lab.read_run('r-old').status == 'complete'
    assert _mode(lab.run_dir('r-old')) == 0o700


def test_concurrent_run_updates_do_not_lose_writes(lab):
    lab.create_run(c.RunRecord(run_id='r1', day_id='d1', ref='a'))

    def bump(i):
        lab.update_run('r1', lambda run: run.warnings.append(f'w{i}'))

    threads = [threading.Thread(target=bump, args=(i,)) for i in range(16)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(lab.read_run('r1').warnings) == sorted(f'w{i}' for i in range(16))


def test_conversations_day_and_logs(lab):
    lab.create_run(c.RunRecord(run_id='r1', day_id='d1', ref='a'))
    lab.write_conversation('r1', c.ConversationRecord(id='c2', started_at='2026-01-15T10:00:00Z'))
    lab.write_conversation('r1', c.ConversationRecord(id='c1', started_at='2026-01-15T09:00:00Z'))
    assert [x.id for x in lab.list_conversations('r1')] == ['c1', 'c2']
    assert lab.read_conversation('r1', 'c1').id == 'c1'
    lab.write_run_day('r1', c.RunDay(daily_summary=c.DailySummary(title='h')))
    assert lab.read_run_day('r1').daily_summary.title == 'h'
    lab.append_llm_calls('r1', [c.LlmCall(id='l1', at='t'), c.LlmCall(id='l2', at='t')])
    lab.append_vendor_log('r1', [c.VendorLogEntry(at='t', vendor='fake', purpose='stt')])
    lab.append_decisions('r1', [c.Decision(at='t', name='N', mode='m', source='overlay')])
    assert [x.id for x in lab.read_llm_calls('r1')] == ['l1', 'l2']
    assert lab.read_vendor_log('r1')[0].vendor == 'fake'
    assert lab.read_decisions('r1')[0].name == 'N'
    assert _mode(lab.llm_calls_path('r1')) == 0o600


def test_concurrent_jsonl_appends_keep_every_line(lab):
    lab.create_run(c.RunRecord(run_id='r1', day_id='d1', ref='a'))
    threads = [
        threading.Thread(target=lab.append_llm_calls, args=('r1', [c.LlmCall(id=f'l{i}', at='t', prompt='x' * 5000)]))
        for i in range(24)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(x.id for x in lab.read_llm_calls('r1')) == sorted(f'l{i}' for i in range(24))


def test_torn_final_jsonl_line_is_skipped(tmp_path):
    path = tmp_path / 'x.jsonl'
    path.write_text('{"a": 1}\n{"a": 2')
    assert s.read_jsonl(path) == [{'a': 1}]
    path.write_text('{"a": 1\n{"a": 2}\n')
    with pytest.raises(ValueError):
        s.read_jsonl(path)


def test_cache_get_put(lab):
    key = 'ab' + '0' * 62
    assert lab.cache_get('notes', key) is None
    lab.cache_put('notes', key, {'output': {'n': 1}})
    assert lab.cache_get('notes', key)['output'] == {'n': 1}
    lab.cache_put('notes', key, {'output': {'n': 2}, 'key': 'other', 'stage': 'other'})
    assert lab.cache_get('notes', key)['output'] == {'n': 2}  # a value never overrides the entry's identity
    assert lab.cache_path('notes', key).parent.name == 'ab'
    with pytest.raises(s.StoreRefused):
        lab.cache_path('notes', '../../etc')


def _verdict(**kw):
    base = dict(
        id=s.new_verdict_id(),
        at='t',
        run_id='r1',
        day_id='d1',
        ref='main',
        conversation_id='c1',
        item_kind='task',
        item_key='k1',
        mark='good',
    )
    base.update(kw)
    return c.Verdict(**base)


def test_verdicts_live_in_the_separate_root(lab):
    lab.append_verdict(_verdict())
    assert lab.verdicts_path.parent == lab.verdicts_root
    assert not any(lab.root.rglob('verdicts.jsonl'))
    assert _mode(lab.verdicts_path) == 0o600


def test_verdict_filters_and_latest(lab):
    lab.append_verdict(_verdict(mark='good', at='1'))
    lab.append_verdict(_verdict(mark='bad', at='2', note='wrong due date'))
    lab.append_verdict(_verdict(item_kind='memory', item_key='m1', run_id='r2'))
    assert len(lab.read_verdicts()) == 3
    latest = lab.read_verdicts(latest=True)
    assert [(v.item_key, v.mark) for v in latest] == [('k1', 'bad'), ('m1', 'good')]
    assert [v.item_key for v in lab.read_verdicts(item_kind='memory')] == ['m1']
    assert [v.at for v in lab.read_verdicts(mark='good', item_kind='task')] == ['1']
    assert [v.run_id for v in lab.read_verdicts(run_id='r2')] == ['r2']
    with pytest.raises(ValueError):
        lab.append_verdict(_verdict(mark='meh'))


def test_new_run_id_is_safe():
    run_id = s.new_run_id('day-1', 'feature/branch name')
    assert s.safe_segment(run_id) == run_id and 'featurebranc' in run_id
