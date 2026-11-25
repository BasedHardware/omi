"""Pipeline-lab ``scenario compare``: conversation diffs, compare.json and exit codes (no stack)."""

from __future__ import annotations

from contextlib import contextmanager
import json

import pytest

from testing.pipeline_lab import cli
from testing.pipeline_lab.scenario import compare, stack

CONV = {
    'handle': 'aaaa1111',
    'recordings': ['A', 'F'],
    'words': 120,
    'visible': True,
    'hidden_reason': None,
    'manual_end': True,
    'deleted': False,
    'started_at': '2026-03-14T09:00:00Z',
}


def test_same_conversations_with_different_handles_do_not_differ():
    assert compare.diff_conversations([CONV], [{**CONV, 'handle': 'bbbb2222'}]) == []


def test_a_changed_field_and_a_missing_conversation_are_listed():
    other = {**CONV, 'recordings': ['B'], 'words': 10}
    rows = compare.diff_conversations([CONV, other], [{**CONV, 'visible': False, 'hidden_reason': 'too_short'}])
    assert rows == [
        {
            'key': 'A+F',
            'base': {k: CONV[k] for k in compare.COMPARED},
            'head': {**{k: CONV[k] for k in compare.COMPARED}, 'visible': False, 'hidden_reason': 'too_short'},
            'fields': ['hidden_reason', 'visible'],
        },
        {'key': 'B', 'base': {k: other[k] for k in compare.COMPARED}, 'head': None, 'fields': ['present']},
    ]


def test_deleted_conversations_are_ignored_and_repeated_keys_are_numbered():
    deleted = {**CONV, 'deleted': True, 'words': 1}
    assert compare.diff_conversations([CONV, deleted], [CONV]) == []
    assert list(compare._keyed([CONV, {**CONV, 'started_at': '2026-03-14T10:00:00Z'}])) == ['A+F', 'A+F#2']


def test_compare_results_flags_outcome_changes():
    rows = compare.compare_results(
        {'s': {'conversations': [CONV]}}, {'s': {'conversations': [CONV]}}, {'s': ('passed', 'failed')}
    )
    assert rows == [{'name': 's', 'base': 'passed', 'head': 'failed', 'differs': True, 'conversations': []}]


@pytest.fixture
def fake_sides(monkeypatch, tmp_path):
    """Two sides whose run_one returns per-side canned results; no worktree, no stack."""
    heads: dict[str, list] = {'base': [], 'head': []}
    seen_arms = []

    def run_one(path, out, peers, *, timeout, clock='frozen', isolation=None, arm=None):
        side = out.relative_to(out.parents[1]).parts[0]
        seen_arms.append((side, arm))
        conv = heads[side].pop(0) if heads[side] else CONV
        row = {'scenario': path.stem, 'outcome': 'passed', 'checks': [], 'conversations': [conv], 'seconds': 1.0}
        (out / 'result.json').write_text(json.dumps(row))
        return row

    @contextmanager
    def local_stack(work):
        yield stack.Peers('127.0.0.1:1', '127.0.0.1:2', 'given')

    class Slots:
        databases = 16

        def __init__(self, *_):
            self.n = 0

        def claim(self, run_id, ttl):
            self.n += 1
            return self.n

        def release(self, db, run_id):
            return True

    def side(repo, ref, vendor_root):
        if ref is None:
            return None, {'ref': 'worktree', 'sha': 'h' * 40, 'backend_tree': 't2', 'dirty': True}
        return stack.Arm(backend=tmp_path, vendor=vendor_root), {
            'ref': ref,
            'sha': 'b' * 40,
            'backend_tree': 't1',
            'dirty': False,
        }

    monkeypatch.setattr(stack, 'run_one', run_one)
    monkeypatch.setattr(stack, 'RedisSlots', Slots)
    monkeypatch.setattr(stack, 'delete_project', lambda host, project: None)
    monkeypatch.setattr(stack, 'local_stack', local_stack)
    monkeypatch.setattr(compare, '_side', side)
    return heads, seen_arms


def test_compare_writes_both_layouts_and_exits_zero_when_equal(tmp_path, fake_sides, capsys):
    _, arms = fake_sides
    out = tmp_path / 'cmp'
    code = cli.main(['scenario', 'compare', 'main', '--scenario', 'finish_single_recording_fast', '--keep', str(out)])
    assert code == 0
    report = json.loads((out / 'compare.json').read_text())
    assert report['differs'] is False and report['base']['ref'] == 'main' and report['head']['ref'] == 'worktree'
    for side in ('base', 'head'):
        assert (out / side / 'run.json').exists() and (out / side / 'verdict.json').exists()
        assert (out / side / 'finish_single_recording_fast' / 'scenario.json').exists()
    assert [a is None for _, a in arms] == [False, True]  # base ran in an arm, head in this tree


def test_compare_exits_one_when_a_conversation_differs(tmp_path, fake_sides, capsys):
    heads, _ = fake_sides
    heads['head'].append({**CONV, 'words': 3, 'visible': False, 'hidden_reason': 'too_short'})
    out = tmp_path / 'cmp'
    code = cli.main(
        [
            'scenario',
            'compare',
            'main',
            '--worktree',
            '--scenario',
            'finish_single_recording_fast',
            '--keep',
            str(out),
            '--json',
        ]
    )
    assert code == 1
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    (row,) = printed['scenarios']
    assert row['differs'] and row['conversations'][0]['fields'] == ['hidden_reason', 'visible', 'words']


def test_compare_refuses_head_and_worktree_together(tmp_path, fake_sides, capsys):
    assert cli.main(['scenario', 'compare', 'main', 'other', '--worktree', '--keep', str(tmp_path / 'c')]) == 2
