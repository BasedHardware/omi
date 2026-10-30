"""Keep coverage, failure detail and durable finalization counts honest."""

import json
from pathlib import Path

MONITORING = Path(__file__).resolve().parents[2] / 'charts/monitoring'


def _panels():
    dashboard = json.loads((MONITORING / 'dashboards/general/omi-core-features.json').read_text())

    def walk(panels):
        for panel in panels:
            yield panel
            yield from walk(panel.get('panels', []))

    return {panel['id']: panel for panel in walk(dashboard['panels'])}


def _row(top, panel_id):
    return next(p for p in top if p['id'] == panel_id)


def test_capture_coverage_is_visible_without_redefining_settled_success():
    panels = _panels()
    headline = panels[2]
    assert 'outcome=~"success|failure"' in headline['targets'][0]['expr']
    assert 'stale' not in headline['targets'][0]['expr']
    coverage = panels[78]
    assert coverage['type'] == 'stat'
    # Coverage stays on the first screen, never inside a collapsed row.
    dashboard = json.loads((MONITORING / 'dashboards/general/omi-core-features.json').read_text())
    top = dashboard['panels']
    assert top.index(_row(top, 27)) < top.index(coverage) < top.index(_row(top, 89))
    assert all(target['instant'] for target in coverage['targets'])
    count, share = [target['expr'] for target in coverage['targets']]
    assert 'outcome="stale"}[3h]' in count
    assert share.startswith('100 * ' + count + ' / ')
    assert 'omi_journey_terminal_total{journey="capture_finalization"}[3h]' in share
    assert 'accepted_total' not in count + share  # Independent event windows are not a cohort/backlog.
    assert 'fenc' in coverage['description'].lower()
    assert coverage['fieldConfig']['defaults']['noValue'] == 'not reporting'
    overrides = coverage['fieldConfig']['overrides']
    assert overrides[0]['matcher']['options'] == coverage['targets'][1]['legendFormat']
    assert {'id': 'unit', 'value': 'percent'} in overrides[0]['properties']


def test_dead_letter_tile_uses_one_durable_global_history_across_pod_churn():
    panel = _panels()[31]
    expr = panel['targets'][0]['expr']
    # Collapse replica identity BEFORE computing the change. Per-process counters
    # cannot recover events before first scrape or after a worker disappears.
    assert 'delta((max(listen_finalization_jobs{status="dead_letter"}))[$__range:1m])' in expr
    assert 'listen_finalization_dead_letter_total' not in expr
    assert 'sum(' not in expr and 'increase(' not in expr
    assert 'or vector(0)' not in expr
    assert 'and on() (time() - max(listen_finalization_summary_last_success_timestamp_seconds) < 900)' in expr
    assert 'BYOK' in panel['description']


def test_client_breakdown_keeps_legacy_unlabeled_failures_visible():
    panels = _panels()
    assert 79 in {p['id'] for p in panels[50]['panels']}
    expr = panels[79]['targets'][0]['expr']
    assert 'sum by (journey, outcome, reason)' in expr
    assert 'outcome=~"failure|degraded|unknown"' in expr
    assert 'reason!=""' in expr and 'reason=""' in expr
    assert '"reason", "legacy_unlabeled"' in expr


def test_system_owned_age_stays_separate_from_byok_waits():
    assert _panels()[30]['targets'][0]['expr'] == 'max(listen_finalization_oldest_nonterminal_age_seconds)'
    # The producer's split and its distinct BYOK age are exercised by
    # test_conversation_finalization_jobs.test_oldest_nonterminal_age_sees_jobs_that_carry_no_reconcile_after_at.
    assert 'blocked_byok is excluded' in _panels()[30]['description']


def _top_level_outcome_tiles():
    dashboard = json.loads((MONITORING / 'dashboards/general/omi-core-features.json').read_text())
    start = next(i for i, p in enumerate(dashboard['panels']) if p['id'] == 1)
    end = next(i for i, p in enumerate(dashboard['panels']) if p['id'] == 27)
    return dashboard['panels'][start + 1 : end]


def test_first_screen_keeps_outcome_thresholds_and_a_trend_under_each_tile():
    panels = _top_level_outcome_tiles()
    stats = {p['id']: p for p in panels if p['type'] == 'stat'}
    bands = {'default': [None, 95, 99], 73: [None, 90, 98]}
    for stat_id, spark_id in zip((63, 3, 2, 73, 4, 20, 36, 70), range(80, 88)):
        stat = stats[stat_id]
        steps = [s['value'] for s in stat['fieldConfig']['defaults']['thresholds']['steps']]
        assert steps == bands.get(stat_id, bands['default']), stat['title']
        spark = next(p for p in panels if p['id'] == spark_id)
        assert spark['fieldConfig']['defaults']['thresholds'] == stat['fieldConfig']['defaults']['thresholds']
        assert spark['gridPos']['x'] == stat['gridPos']['x']
        assert spark['gridPos']['y'] == stat['gridPos']['y'] + stat['gridPos']['h']
        assert spark['interval'] == '1h'
        assert 'noValue' not in spark['fieldConfig']['defaults'], 'noValue turns gaps into a drawn value'
        expr = spark['targets'][0].get('expr')
        if expr is None:
            promql = spark['targets'][0]['promQLQuery']
            assert '[1h]' in promql['expr'] and '[3h]' not in promql['expr']
            assert promql['step'] == '1h'
        else:
            # The window equals the step, so each sample is read once and a wider range cannot overlap.
            assert '[$__interval]' in expr and '[$__range]' not in expr
            assert expr.endswith(' >= 0'), 'hours with no settled traffic must gap, not draw NaN'


def test_verdict_counts_the_same_expressions_as_the_tiles():
    panels = _panels()
    (target,) = panels[88]['targets']
    assert target['instant'] is True
    assert target['expr'].startswith('count_values("state", clamp(floor((((')
    assert target['expr'].endswith(') >= 0) - 95) / 4), -1, 1))')
    for tile in (63, 3, 2, 4, 20, 36, 70):
        assert panels[tile]['targets'][0]['expr'] in target['expr']
    assert panels[73]['targets'][0].get('expr') is None  # Recaps live in another datasource and bands.


def test_first_screen_is_exactly_the_agreed_panels():
    panels = _top_level_outcome_tiles()
    # Panel 5 is the deliberate exception: it is the only no-signal check, because a stopped
    # reporter and no traffic look the same on an outcome tile.
    assert {p['id'] for p in panels} == {88, 5, 63, 3, 2, 73, 4, 20, 36, 70, *range(80, 88)}


def test_no_panels_overlap_on_the_first_screen_or_inside_any_row():
    dashboard = json.loads((MONITORING / 'dashboards/general/omi-core-features.json').read_text())
    groups = [[p for p in dashboard['panels']]] + [p['panels'] for p in dashboard['panels'] if p.get('panels')]
    for group in groups:
        occupied = set()
        for panel in group:
            g = panel['gridPos']
            cells = {(x, y) for x in range(g['x'], g['x'] + g['w']) for y in range(g['y'], g['y'] + g['h'])}
            assert not cells & occupied, panel['title']
            assert g['x'] + g['w'] <= 24, panel['title']
            occupied |= cells
