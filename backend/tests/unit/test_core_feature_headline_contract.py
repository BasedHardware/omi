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


def test_capture_coverage_is_visible_without_redefining_settled_success():
    panels = _panels()
    headline = panels[2]
    assert 'outcome=~"success|failure"' in headline['targets'][0]['expr']
    assert 'stale' not in headline['targets'][0]['expr']
    coverage = panels[78]
    assert coverage['type'] == 'stat'
    assert coverage['gridPos']['y'] == headline['gridPos']['y']
    assert coverage['gridPos']['x'] == headline['gridPos']['x'] + headline['gridPos']['w']
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
