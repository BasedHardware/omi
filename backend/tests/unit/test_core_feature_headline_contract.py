"""Keep coverage, failure detail and durable finalization counts honest."""

import json
import re
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
    assert 'omi_journey_terminal_total{job="pusher-metrics",journey="capture_finalization"}[3h]' in share
    assert share.endswith(' > 0)')
    assert 'accepted_total' not in count + share  # Independent event windows are not a cohort/backlog.
    assert 'fenc' in coverage['description'].lower()
    assert coverage['fieldConfig']['defaults']['noValue'] == 'not measured'
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
    # 99/95 only where the denominator is a user result. Other tiles stay
    # uncolored so a non-outcome rate cannot read as a failed 99% bar.
    # Recaps keep their own 98/90 generation scale.
    bands = {
        'default': [None, 0, 95, 99],
        73: [None, 0, 90, 98],
        63: [None],
        2: [None],
        20: [None],
        36: [None],
    }
    for stat_id, spark_id in zip((63, 3, 2, 73, 4, 20, 36, 70), range(80, 88)):
        stat = stats[stat_id]
        steps = [s['value'] for s in stat['fieldConfig']['defaults']['thresholds']['steps']]
        assert steps == bands.get(stat_id, bands['default']), stat['title']
        assert stat['fieldConfig']['defaults']['thresholds']['steps'][0]['color'] == 'text', stat['title']
        spark = next(p for p in panels if p['id'] == spark_id)
        assert spark['fieldConfig']['defaults']['thresholds'] == stat['fieldConfig']['defaults']['thresholds']
        assert spark['gridPos']['x'] == stat['gridPos']['x']
        assert spark['gridPos']['y'] == stat['gridPos']['y'] + stat['gridPos']['h']
        assert 'noValue' not in spark['fieldConfig']['defaults'], 'noValue turns gaps into a drawn value'
        expr = spark['targets'][0].get('expr')
        assert spark['fieldConfig']['defaults']['custom']['gradientMode'] == 'scheme'
        if stat_id == 36:
            # Production has no realtime_voice denominator. Do not manufacture
            # numerator data for an unmeasured journey.
            assert ' or 0 * sum(' not in stat['targets'][0]['expr']
            assert ' or 0 * sum(' not in spark['targets'][0]['expr']
            assert stat['fieldConfig']['defaults']['noValue'] == 'not measured'
        elif stat_id != 73:
            # A numerator series that was never created must read 0% under traffic, not "no traffic".
            assert ' or 0 * sum(' in stat['targets'][0]['expr'], stat['title']
            assert ' or 0 * sum(' in spark['targets'][0]['expr'], stat['title']
        if expr is None:
            assert spark['interval'] == '1h'
            promql = spark['targets'][0]['promQLQuery']
            assert '[1h]' in promql['expr'] and '[3h]' not in promql['expr']
            assert promql['step'] == '1h'
        else:
            # Roughly 24 points at any range, so a short range doesn't end a whole step early.
            assert spark['interval'] == '5m' and spark['maxDataPoints'] == 24
            # The window equals the step, so each sample is read once and a wider range cannot overlap.
            assert '[$__interval]' in expr and '[$__range]' not in expr
            assert expr.endswith(' >= 0'), 'hours with no settled traffic must gap, not draw NaN'


def test_oldest_job_shows_the_queue_that_separates_stuck_from_backlog():
    panel = _panels()[30]
    assert [t['legendFormat'] for t in panel['targets']] == ['Oldest', 'Queued']
    assert panel['targets'][1]['expr'] == 'max(listen_finalization_jobs{status="queued"})'
    assert panel['fieldConfig']['overrides'][0]['matcher']['options'] == 'Queued'


def test_capture_failures_can_be_read_by_reason():
    panels = _panels()
    assert 90 in {p['id'] for p in panels[44]['panels']}
    expr = panels[90]['targets'][0]['expr']
    assert 'sum by (service_name, reason)' in expr
    assert 'omi_capture_finalization_failures_total[$__interval]' in expr


def test_first_screen_is_exactly_the_agreed_panels():
    panels = _top_level_outcome_tiles()
    assert {p['id'] for p in panels} == {63, 3, 2, 73, 4, 20, 36, 70, *range(80, 88)}


def test_home_rows_tile_is_an_average_not_a_success_rate():
    dashboard = json.loads((MONITORING / 'dashboards/general/omi-core-features.json').read_text())
    panel = next(p for p in dashboard['panels'] if p.get('title') == 'Home rows / user / day')
    expr = panel['targets'][0]['expr']
    assert 'omi_home_rows_user_day_sum_total' in expr
    assert 'omi_home_rows_user_day_count_total' in expr
    assert panel['fieldConfig']['defaults']['noValue'] == 'not measured'
    assert panel['fieldConfig']['defaults']['thresholds']['steps'] == [{'color': 'text', 'value': None}]
    # Stays off the locked first screen (panels between the feature-health row and "Is anything stuck?").
    stuck = next(i for i, p in enumerate(dashboard['panels']) if p['id'] == 27)
    assert dashboard['panels'].index(panel) > stuck


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


def test_headline_tiles_name_the_user_result_they_actually_count():
    panels = _panels()
    assert 'not a user outcome' in panels[63]['description'].lower()
    live = panels[3]['targets'][0]['expr']
    assert 'frames_seen="audio"' in live
    assert 'queue_wait_timeout' in live
    assert 'application_error' in live
    assert 'replay' in panels[3]['description'].lower()
    assert 'visible' in panels[2]['description'].lower()
    assert 'dead-letter' in panels[2]['description'].lower()
    assert 'chat_response' in panels[4]['targets'][0]['expr']
    assert '4xx' in panels[4]['description'].lower() or 'upstream_rejected' in panels[4]['description'].lower()
    gateway = panels[20]['targets'][0]['expr']
    assert 'job="llm-gateway-metrics"' in gateway
    assert panels[20]['fieldConfig']['defaults']['noValue'] == 'not measured'
    assert 'on-device' in panels[36]['description'].lower()
    assert 'last 3 hours' in panels[73]['description'].lower() or 'last 3h' in panels[73]['title'].lower()
    assert 'not what the user received' in panels[73]['description'].lower()


def test_server_journeys_use_only_their_emitting_jobs():
    # November 7 dashboard incident: every process pre-initializes all three
    # journeys. A journey-only selector silently counts unrelated scrape jobs.
    owners = {
        'chat_response': 'cloud-run-application-metrics',
        'pusher_session': 'pusher-metrics',
        'capture_finalization': 'pusher-metrics',  # Live finalization; sync is separate.
    }
    seen = set()
    for panel in _panels().values():
        for target in panel.get('targets', []):
            expr = target.get('expr', '')
            selectors = re.findall(r'\bomi_journey_\w+(\{[^}]*\})?', expr)
            for selector in selectors:
                journey = re.search(r'journey="([^"]+)"', selector)
                assert journey is not None, (panel['id'], expr)
                journey = journey[1]
                assert journey in owners, (panel['id'], journey)
                owner = owners[journey]
                # Live capture is accepted by backend-listen and settled by pusher
                # (prod 2026-11-12: 49,870 accepted on backend-listen, 0 on pusher, 2d).
                if journey == 'capture_finalization' and f'omi_journey_accepted_total{selector}' in expr:
                    owner = 'backend-listen-metrics'
                # Exactly one job matcher: repeated matchers must all match, so a second
                # job would select nothing while a substring check still passed.
                assert re.findall(r'\bjob\s*(=~|!~|!=|=)\s*"([^"]*)"', selector) == [('=', owner)], (
                    panel['id'],
                    selector,
                )
                seen.add(journey)
            # Client and server journey names are disjoint, not join keys.
            for selector in re.findall(r'\bomi_client_journey_\w+\{([^}]*)\}', expr):
                assert not any(f'journey="{journey}"' in selector for journey in owners), panel['id']
    assert seen == set(owners)
    for panel_id in (5, 6, 7, 8, 9):
        for target in _panels()[panel_id]['targets']:
            assert all(f'journey="{journey}"' in target['expr'] for journey in owners), panel_id


def test_non_journey_metrics_match_the_observed_production_labels():
    # Label-values evidence (c), 2026-11-07. No guessed spellings such as
    # frames_seen=true or event=cancelled may silently empty these queries.
    allowed = {
        'pusher_socket_closed_total': {
            'job': {'pusher-metrics'},
            'frames_seen': {'audio', 'control_only', 'none'},
            'reason': {
                'application_error',
                'cancelled',
                'peer',
                'protocol_error',
                'queue_wait_timeout',
                'receive_timeout',
                'rejected',
            },
        },
        'llm_gateway_requests_total': {
            'job': {'llm-gateway-metrics'},
            'outcome': {'error', 'success'},
        },
        'omi_listen_accepted_total': {
            'job': {'backend-listen-metrics'},
            'transcription_source': {
                'apple_watch',
                'bee',
                'desktop',
                'fieldy',
                'limitless',
                'omi',
                'openglass',
                'phone',
                'plaud',
                'rayban_meta',
                'unknown',
            },
        },
        'omi_subscription_events_total': {
            'job': {'cloud-run-application-metrics'},
            'event': {'cancellation_requested', 'cancellation_reverted', 'created', 'ended', 'payment_failed'},
        },
    }
    seen = set()
    for panel in _panels().values():
        for target in panel.get('targets', []):
            for metric, labels in allowed.items():
                for selector in re.findall(r'\b' + metric + r'\{([^}]*)\}', target.get('expr', '')):
                    assert 'journey' not in selector, (panel['id'], metric)
                    for label, _, value in re.findall(r'(\w+)(=~|!~|!=|=)"([^"]*)"', selector):
                        assert label in labels, (panel['id'], metric, label)
                        assert set(value.split('|')) <= labels[label], (panel['id'], metric, label, value)
                    seen.add(metric)
    assert seen == set(allowed)


def test_scoped_stats_preserve_missing_telemetry_instead_of_fabricating_zero():
    panels = _panels()
    for panel_id in (2, 3, 4, 5, 12, 13, 14, 15, 20, 36, 37, 38, 39, 51, 52, 53, 54, 55, 56, 57, 58, 59, 78, 94):
        panel = panels[panel_id]
        assert panel['fieldConfig']['defaults']['noValue'] == 'not measured', panel['title']
        for target in panel['targets']:
            assert 'or vector(0)' not in target['expr'], panel['title']
    for panel_id in (2, 3, 4, 20, 36, 51, 52, 53, 54, 55, 56, 59):
        # A present but idle denominator must also leave the stat empty.
        assert panels[panel_id]['targets'][0]['expr'].endswith(' > 0)'), panels[panel_id]['title']
    for panel_id in (12, 13, 14, 15):
        expr = panels[panel_id]['targets'][0]['expr']
        assert '0 * sum(increase(omi_subscription_events_total{job="cloud-run-application-metrics"}[$__range]))' in expr
        # Unscoped, the query also scans the always-zero listen series and times out (2026-11-12).
        assert 'omi_subscription_events_total[' not in expr and 'omi_subscription_events_total{event' not in expr
