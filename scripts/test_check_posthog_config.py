#!/usr/bin/env python3
"""Fixture tests for scripts/check_posthog_config.py (stdlib unittest)."""
import contextlib
import datetime as dt
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_posthog_config as check  # noqa: E402

TODAY = dt.date(2026, 11, 23)
WAIVER = {'by': 'David Zhang', 'date': '2026-11-23', 'reason': 'until collector alerts replace PostHog', 'expires': '2026-12-07'}


def passing():
    return {
        'project_id': 1,
        'budget': {
            'monthly_usd': 500,
            'days_per_month': 30,
            'tiers': {
                'events': [[1000000, 0], [2000000, 0.00005], [None, 0.0000343]],
                'identified_events': [[1000000, 0], [2000000, 0.000198], [None, 0.0000697]],
                'feature_flag_requests': [[1000000, 0], [2000000, 0.0001], [None, 0.000045]],
            },
            'warehouse_usd_per_row': 0.0000059,
        },
        'feature_flags': {'measured_requests_per_day': 0},
        'functions': [
            {'id': 'keep', 'name': 'Keep-list', 'execution_order': 5, 'enabled': True, 'kind': 'keep_list', 'pct': 2,
             'events': ['Memory Created', 'Capture Wedge Detected']},
            {'id': 'wedge', 'name': 'Wedge 10%', 'execution_order': 9, 'enabled': True, 'kind': 'sample', 'pct': 10,
             'events': ['Capture Wedge Detected']},
            {'id': 'drop', 'name': 'Drop', 'execution_order': 7, 'enabled': True, 'kind': 'drop', 'pct': 0,
             'events': ['wal_transcript_coverage']},
            {'id': 'geo', 'name': 'GeoIP', 'execution_order': 1, 'enabled': True, 'kind': 'unmanaged'},
        ],
        'warehouse': {'schemas': [
            {'source_id': 's', 'schema_id': 'raw', 'name': 'raw', 'should_sync': False, 'sync_type': 'full_refresh',
             'est_rows_per_run': 31000000, 'runs_per_month': 4.3, 'reader': ['x']},
        ]},
        'events': {
            'Memory Created': {'est_events_per_day': 1000, 'identified': True, 'purpose': 'product', 'reader': ['ins1']},
            'Capture Wedge Detected': {'est_events_per_day': 20000, 'identified': True, 'purpose': 'debug',
                                       'reader': ['grafana:device-signals'], 'waiver': dict(WAIVER)},
            'Device Connected': {'est_events_per_day': 40000, 'identified': True},
        },
    }


def errors(doc, today=TODAY):
    return check.validate(doc, today)


class CheckPostHogConfig(unittest.TestCase):
    def assertOneError(self, doc, fragment, today=TODAY):
        found = errors(doc, today)
        self.assertEqual(len(found), 1, found)
        self.assertIn(fragment, found[0])

    def test_passing_fixture(self):
        self.assertEqual(errors(passing()), [])

    def test_repository_config_fails_only_on_budget(self):
        # The honest 2026-11-23 config is over $500 with no ceiling (David: no interim ceiling).
        # Every other rule passes; when cuts land, this flips to passing.
        doc = json.loads((check.ROOT / check.SOURCE).read_text())
        self.assertNotIn('ceiling', doc['budget'])
        found = errors(doc)
        self.assertTrue(all(e.startswith('budget: estimated') for e in found), found)

    def test_negative_estimate(self):
        doc = passing()
        doc['events']['Device Connected']['est_events_per_day'] = -40000
        self.assertOneError(doc, 'Device Connected: est_events_per_day must be a non-negative integer')

    def test_kept_event_without_estimate(self):
        doc = passing()
        del doc['events']['Memory Created']['est_events_per_day']
        self.assertOneError(doc, 'without a measured est_events_per_day')

    def test_new_keep_list_event_without_entry(self):
        doc = passing()
        doc['functions'][0]['events'].append('Brand New Event')
        self.assertOneError(doc, 'Brand New Event: kept at 100% without a measured est_events_per_day')

    def test_kept_event_without_reader(self):
        doc = passing()
        del doc['events']['Memory Created']['reader']
        self.assertOneError(doc, 'kept at 100% with no reader')

    def test_debug_purpose_above_ceiling_without_waiver(self):
        doc = passing()
        del doc['events']['Capture Wedge Detected']['waiver']
        self.assertOneError(doc, 'debug event kept at 10%')

    def test_expired_waiver(self):
        doc = passing()
        self.assertOneError(doc, 'needs an unexpired waiver', today=dt.date(2026, 12, 8))

    def test_waiver_not_signed_by_david(self):
        doc = passing()
        doc['events']['Capture Wedge Detected']['waiver']['by'] = 'An Agent'
        self.assertOneError(doc, 'signed by David Zhang')

    def test_debug_named_product_event(self):
        doc = passing()
        doc['functions'][0]['events'].append('Phone Battery Sample')
        doc['events']['Phone Battery Sample'] = {'est_events_per_day': 9000, 'identified': True, 'purpose': 'product', 'reader': ['route.ts']}
        self.assertOneError(doc, 'Phone Battery Sample: debug-named event kept at 100%')

    def test_debug_event_at_two_percent_is_allowed(self):
        doc = passing()
        doc['functions'][1]['pct'] = 2
        del doc['events']['Capture Wedge Detected']['waiver']
        self.assertEqual(errors(doc), [])

    def test_debug_name_tokens(self):
        for name in ('Recording Upload Failed', 'authenticated_request_401', 'fallback_triggered',
                     'Mobile Device Health Daily', 'Phone Battery Sample', 'wal_transcript_coverage'):
            self.assertTrue(check.debug_name(name), name)
        for name in ('Daily Summary Detail Viewed', 'Memory Created', 'Diagnostics Opened', 'Sample Rate Changed'):
            self.assertFalse(check.debug_name(name), name)

    def test_budget_exceeded(self):
        doc = passing()
        doc['events']['Memory Created']['est_events_per_day'] = 2_000_000
        self.assertOneError(doc, 'exceeds budget.monthly_usd $500')

    def test_unsigned_ceiling_never_counts(self):
        doc = passing()
        doc['events']['Memory Created']['est_events_per_day'] = 400_000
        doc['budget']['ceiling'] = {'usd': 1500, 'until': '2026-12-07', 'reason': 'glide path'}
        found = errors(doc)
        self.assertEqual(len(found), 2, found)
        self.assertIn('a ceiling needs an unexpired waiver signed by David Zhang', found[0])
        self.assertIn('exceeds budget.monthly_usd $500', found[1])

    def test_signed_ceiling_covers_until_it_expires(self):
        doc = passing()
        doc['events']['Memory Created']['est_events_per_day'] = 400_000
        doc['budget']['ceiling'] = {'usd': 1500, 'until': '2026-12-07', 'reason': 'glide path', 'waiver': dict(WAIVER)}
        self.assertEqual(errors(doc), [])
        doc['events']['Capture Wedge Detected']['waiver']['expires'] = '2026-12-31'
        found = errors(doc, today=dt.date(2026, 12, 8))
        self.assertEqual(len(found), 2, found)

    def test_planned_savings_are_priced_separately(self):
        doc = passing()
        doc['events']['Memory Created']['est_events_per_day'] = 400_000
        doc['feature_flags']['measured_requests_per_day'] = 100_000
        doc['budget']['planned'] = [{'id': 'p', 'saving': {'events_per_day': {'Memory Created': 300_000},
                                                            'feature_flag_requests': 'all'}}]
        now, later = check.estimate(doc), check.estimate(doc, with_planned=True)
        self.assertAlmostEqual(later['events_per_month'], now['events_per_month'] - 9_000_000)
        self.assertEqual(later['flags'], 0)
        self.assertGreater(now['flags'], 0)
        self.assertIn('exceeds budget.monthly_usd', errors(doc)[0])

    def test_flags_are_priced_from_the_measured_daily_rate(self):
        doc = passing()
        doc['feature_flags']['measured_requests_per_day'] = 100_000  # 3M/month: 1M free, 1M at $0.0001, 1M at $0.000045
        cost = check.estimate(doc)
        self.assertAlmostEqual(cost['flags'], 145.0)
        self.assertEqual(cost['flag_requests_per_month'], 3_000_000)
        self.assertEqual(check.estimate(doc, flags_per_day=0)['flags'], 0)

    def test_flag_measurement_is_required(self):
        for bad in (None, -1, 1.5, True):
            doc = passing()
            doc['feature_flags']['measured_requests_per_day'] = bad
            self.assertTrue(any('feature_flags.measured_requests_per_day' in e for e in errors(doc)), bad)

    def test_warehouse_full_refresh_over_one_million_rows(self):
        doc = passing()
        doc['warehouse']['schemas'][0]['should_sync'] = True
        doc['budget']['monthly_usd'] = 100000
        self.assertOneError(doc, 'full_refresh re-bills 31,000,000 rows')

    def test_later_stage_must_not_loosen_tag(self):
        doc = passing()
        doc['functions'].append({'id': 'uploads', 'name': 'Uploads 0.5%', 'execution_order': 3, 'enabled': True,
                                 'kind': 'sample', 'pct': 0.5, 'events': ['Recording Upload Started']})
        doc['events']['Recording Upload Started'] = {'est_events_per_day': 1000, 'identified': True}
        self.assertOneError(doc, 'omi_sample_pct would read 2 but the event is kept at 0.5%')

    def test_tiered_estimate(self):
        tiers = passing()['budget']['tiers']['events']
        self.assertEqual(check.tiered(900_000, tiers), 0)
        self.assertAlmostEqual(check.tiered(3_000_000, tiers), 50 + 34.3)
        doc = passing()
        cost = check.estimate(doc)
        # 1000 + 20000 * 10% + 40000 * 2% = 3800/day = 114k/month, inside the free tier.
        self.assertAlmostEqual(cost['events_per_month'], 114000)
        self.assertEqual(cost['total'], 0)

    def test_unrelated_diff_only_warns(self):
        doc = passing()
        del doc['events']['Memory Created']['reader']
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'posthog.json'
            path.write_text(json.dumps(doc))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(check.run(path, None, TODAY, enforce=False), [])
                self.assertEqual(len(check.run(path, None, TODAY, enforce=True)), 1)
            text = out.getvalue()
        self.assertIn('PostHog estimate: $0/mo (base $0/mo, delta $+0)', text)
        self.assertIn('warning (PostHog config unchanged in this diff)', text)


if __name__ == '__main__':
    unittest.main()
