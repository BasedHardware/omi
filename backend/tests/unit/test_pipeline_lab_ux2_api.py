"""Pipeline lab, inspector round 2: digest and group API, conversation field comparison, verdict links, day panel,
and the nav routing helper. Synthetic sample only."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from testing.pipeline_lab.baseline.compare import TAGS
from testing.pipeline_lab.inspector import sample_run, views
from testing.pipeline_lab.inspector.reader import Reader

RUN = sample_run.RUN_ID
STATIC = Path(__file__).resolve().parents[2] / 'testing' / 'pipeline_lab' / 'inspector' / 'static'


@pytest.fixture(scope='module')
def reader(tmp_path_factory):
    base = tmp_path_factory.mktemp('plab-ux2')
    sample_run.write_sample(base / 'store', audio_rate=1000)
    return Reader(base / 'store', base / 'verdicts')


def test_every_digest_number_is_the_number_of_groups_its_chip_shows(reader):
    ov = views.run_overview(reader, RUN)
    digest, groups = ov['digest'], ov['groups']
    for tag in TAGS:
        assert digest['tags'][tag] == len([g for g in groups if tag in g['tags']]), tag
    assert digest['groups'] == len(groups) == sum(digest['kinds'].values())
    # the status words agree with the digest: one status per group kind
    for kind, n in digest['kinds'].items():
        status = 'changed' if kind == 'content' else kind
        assert ov['statuses'].get(status, 0) == n
    assert digest['home']['production'] == sum(c['home'] for g in groups for c in g['production'])
    assert digest['home']['replay'] == sum(c['home'] for g in groups for c in g['replay'])


def test_groups_carry_cells_with_home_state_and_a_change_line(reader):
    ov = views.run_overview(reader, RUN)
    merge = next(g for g in ov['groups'] if g['kind'] == 'merge')
    assert len(merge['production']) == 2 and len(merge['replay']) == 1 and merge['marker'] == '⇉'
    assert merge['open'] == {'kind': 'replay', 'id': merge['replay'][0]['id']}
    missing = next(g for g in ov['groups'] if g['kind'] == 'missing')
    assert missing['replay'] == [] and missing['open']['kind'] == 'production'
    for group in ov['groups']:
        assert group['change']
        for cell in group['production'] + group['replay']:
            assert isinstance(cell['home'], bool) and (cell['home'] or cell['home_reason'])
    # the flat list (agents, j/k) follows the groups
    assert {r['group'] for r in ov['conversations']} == {g['id'] for g in ov['groups']}


def test_stale_baseline_json_is_recomputed_not_trusted(reader):
    run_dir = reader.root / 'runs' / RUN
    (run_dir / 'baseline.json').write_text(json.dumps({'conversations': [], 'counts': {'changed': 999}}))
    try:
        ov = views.run_overview(reader, RUN)
        assert ov['digest']['groups'] == len(ov['groups']) > 0
    finally:
        (run_dir / 'baseline.json').unlink()


def test_conversation_page_lists_every_compared_field_including_emoji(reader):
    ov = views.run_overview(reader, RUN)
    pair = next(g for g in ov['groups'] if g['kind'] in ('content', 'same') and g['replay'])
    detail = views.conversation_detail(reader, RUN, pair['replay'][0]['id'])
    names = [f['field'] for f in detail['compare']['fields']]
    assert {'home', 'title', 'overview', 'emoji', 'category', 'events', 'tasks', 'memories', 'pushes'} <= set(names)
    assert all(f['class'] in ('same', 'cosmetic', 'substantive') for f in detail['compare']['fields'])
    assert detail['home']['replay']['home'] in (True, False) and detail['home']['production']
    assert detail['group']['id'] == pair['id']


def test_verdict_links_open_the_replay_conversation(reader):
    ov = views.run_overview(reader, RUN)
    merge = next(g for g in ov['groups'] if g['kind'] == 'merge')
    replay_id, second_prod = merge['replay'][0]['id'], merge['production'][1]['id']
    detail = views.conversation_detail(reader, RUN, replay_id)
    row = views.build_verdict(
        reader,
        {
            'run_id': RUN,
            'conversation_id': replay_id,
            'item_kind': 'summary',
            'item_key': detail['keys']['replay']['summary'],
            'mark': 'bad',
        },
    )
    assert row['conversation_id'] != replay_id  # stored under the production id (RULINGS 4)
    assert views.verdict_open(reader, row) == {'kind': 'replay', 'run_id': RUN, 'id': replay_id}
    # a mark that only names a production id resolves through its group
    bare = {'run_id': RUN, 'conversation_id': second_prod, 'item_kind': 'summary'}
    assert views.verdict_open(reader, bare) == {'kind': 'replay', 'run_id': RUN, 'id': replay_id}
    missing = next(g for g in ov['groups'] if g['kind'] == 'missing')['production'][0]['id']
    assert (
        views.verdict_open(reader, {'run_id': RUN, 'conversation_id': missing, 'item_kind': 'task'})['kind']
        == 'production'
    )
    assert views.verdict_open(reader, {'run_id': RUN, 'item_kind': 'daily_summary'})['kind'] == 'day'


def test_day_panel_reports_a_failed_daily_summary_and_real_highlights(reader, tmp_path):
    store = tmp_path / 'store'
    shutil.copytree(reader.root, store)
    run_dir = store / 'runs' / RUN
    day = json.loads((run_dir / 'day.json').read_text())
    day['daily_summary'] = None
    day['goals'] = [
        {'title': 'Revenue', 'progress_before': 8e7, 'progress_after': 8e7, 'target': 1e9, 'unit': 'dollars'},
        {'title': 'Ship', 'progress_before': 0.2, 'progress_after': 0.5, 'target': 1.0},
    ]
    (run_dir / 'day.json').write_text(json.dumps(day))
    run = json.loads((run_dir / 'run.json').read_text())
    run['warnings'] = ['daily_summary: daily summary failed: InternalServerError']
    (run_dir / 'run.json').write_text(json.dumps(run))
    baseline = store / 'corpus' / sample_run.DAY_ID / 'baseline' / 'daily_summary.json'
    summary = json.loads(baseline.read_text())
    summary['highlights'] = [{'emoji': '🌱', 'topic': 'Seeds', 'summary': 'Traded seeds.', 'conversation_ids': ['x']}]
    baseline.write_text(json.dumps(summary))
    panel = views.day_panel(Reader(store, tmp_path / 'verdicts'), RUN)
    assert panel['daily_summary']['replay'] is None
    assert panel['daily_summary']['replay_failure'].endswith('InternalServerError')
    assert panel['daily_summary']['baseline']['highlights'] == [
        {'emoji': '🌱', 'topic': 'Seeds', 'summary': 'Traded seeds.'}
    ]
    assert [g['changed'] for g in panel['goals']] == [False, True] and panel['goals_changed'] == 1


def _function_source(text: str, name: str) -> str:
    match = re.search(r'\n  (?:async )?function ' + name + r'\(.*?\n  }\n', text, re.S)
    assert match, name
    return match.group(0)


@pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')
def test_day_link_always_leads_back_to_the_day():
    """``dayHref`` (app.js) is what the Day nav link points at on every page, set before anything loads."""
    script = _function_source((STATIC / 'app.js').read_text(), 'dayHref') + """
const runs = [{run_id: 'run-b'}, {run_id: 'run-a'}];
const out = [
  dayHref({view: 'verdicts'}, 'run-a', runs),
  dayHref({view: 'verdicts'}, null, runs),
  dayHref({view: 'verdicts'}, 'gone', runs),
  dayHref({view: 'conv', runId: 'run-a'}, 'run-b', runs),
  dayHref({view: 'verdicts'}, 'run-a', null),
  dayHref({view: 'verdicts'}, null, []),
];
console.log(JSON.stringify(out));
"""
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=30, check=True)
    assert json.loads(result.stdout) == [
        '#/run/run-a',
        '#/run/run-b',
        '#/run/run-b',
        '#/run/run-a',
        '#/run/run-a',
        '#/',
    ]


def test_render_sets_the_nav_before_it_awaits_anything():
    """The stuck-on-Verdicts fix: nav highlight, aria-current and the Day href change on the hashchange itself."""
    text = (STATIC / 'app.js').read_text()
    render = _function_source(text, 'render').replace('async function', 'function')
    assert render.index('setNav(route)') < render.index('await ')
    verdicts = _function_source(text, 'verdictHref')
    assert 'conversation_id' not in verdicts  # links come from the server-resolved ``open``
