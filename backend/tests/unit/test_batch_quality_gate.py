import copy
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import importlib.util

POLICY_PATH = pathlib.Path(__file__).resolve().parents[2] / 'scripts/rollout/batch_quality_gate.py'
spec = importlib.util.spec_from_file_location('batch_quality_gate_under_test', POLICY_PATH)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

NOW = guard.epoch('2026-10-29T04:00:00Z')
SOFT = [
    'T3_batch_wedge',
    'T3_admitted_nonterminal_over2h',
    'T5_failed_held_over2pct',
    'T2_unknown_held_capture_over5pct_1h',
    'serving_revision_changed_requalify',
    'serving_percent_drift',
    'manifest_hash_drift',
    'observer_pin_drift',
    't2-window_missing',
]


def packet():
    common = dict(at='2026-10-29T04:00:00Z', serving_sha='a' * 40, complete=True, evidence_ref='doc:test-receipt')
    return dict(
        serving_sha='a' * 40,
        errclass=dict(common, baseline_hours=24, includes_zero_percent_traffic=True, untriaged_new_classes=0),
        replay=dict(common, verdict='PASS'),
        observer=dict(
            at=common['at'],
            observed_through=common['at'],
            verdict='CLEAN',
            reasons=[],
            observation_since='2026-10-29T03:30:00Z',
            observation_started_at='2026-10-29T03:30:00Z',
            observed_samples=16,
            max_sample_gap_seconds=120,
            hard3=dict(T1='CLEAN', T2='CLEAN', T4='CLEAN'),
        ),
    )


class HardThreeTest(unittest.TestCase):
    def test_thin_speech_denominator_is_unknown_even_when_complete(self):
        sample = self.sample()
        sample.update(
            terminal_unrecovered_vad_speech_seconds=10,
            terminal_unrecovered_speech_max_unit_seconds=10,
            terminal_unrecovered_speech_denominator_seconds=1000,
        )
        self.assertEqual(guard.observer_record(sample, '2026-10-29T04:00:00Z')['hard3']['T2'], 'UNKNOWN')

    def test_backdated_query_scope_does_not_create_measured_soak(self):
        record = packet()['observer']
        fresh = {
            key: value
            for key, value in record.items()
            if key not in ('observation_started_at', 'observed_samples', 'max_sample_gap_seconds')
        }
        first = guard.observed_clock(fresh)
        self.assertEqual(first['observation_started_at'], first['observed_through'])
        p = packet()
        p['observer'] = first
        self.assertEqual(guard.entry_check(p, NOW)['verdict'], 'WAIT')
        prior = first
        for minutes in range(2, 32, 2):
            stamp = guard.dt.datetime.fromtimestamp(NOW + minutes * 60, guard.dt.timezone.utc).isoformat()
            prior = guard.observed_clock(dict(fresh, at=stamp, observed_through=stamp), prior)
        p['observer'] = prior
        p['errclass']['at'] = p['replay']['at'] = prior['at']
        self.assertEqual(guard.entry_check(p, NOW + 1800)['verdict'], 'READY_FOR_LEAD_ENTRY')
        gap = guard.observed_clock(
            dict(prior, at='2026-10-29T05:00:00Z', observed_through='2026-10-29T05:00:00Z'), prior
        )
        self.assertEqual(gap['observed_samples'], 1)

    def sample(self):
        return dict(
            rows_read_at='2026-10-29T04:00:00Z',
            custody=dict(missing=0, unknown=0),
            terminal_unrecovered_vad_speech_seconds=0,
            terminal_unrecovered_speech_denominator_seconds=7200,
            terminal_unrecovered_speech_max_unit_seconds=0,
            measured_held_vad_speech_seconds=0,
            measured_held_vad_max_unit_seconds=0,
            terminal_unrecovered_speech_unknown_units=0,
            held_vad_unknown_units=0,
            terminal_unrecovered_speech_vad_fallback_units=0,
            since_t0_failed_held_unknown_duration=0,
            since_t0_failed_held_vad_fallback_units=0,
            language_route_unsafe_parakeet_units=0,
            language_route_missing_completed_units=0,
        )

    def test_raw_observer_hard_harm_survives_soft_noise_and_missing_fields(self):
        sample = self.sample()
        self.assertEqual(
            guard.observation(guard.observer_record(sample, '2026-10-29T04:00:00Z'), NOW)['verdict'], 'CLEAN'
        )
        for field, value, reason in (
            ('terminal_unrecovered_speech_max_unit_seconds', 120, 'T2_lost_unit_over120s'),
            ('terminal_unrecovered_vad_speech_seconds', 15, 'T2_lost_speech_over0_2pct'),
            ('language_route_unsafe_parakeet_units', 1, 'T4_unsafe_parakeet_route'),
            ('language_route_missing_completed_units', 1, 'T4_completed_without_route_proof'),
        ):
            with self.subTest(field=field):
                s = self.sample()
                s[field] = value
                result = guard.observer_record(s, '2026-10-29T04:00:00Z', SOFT)
                self.assertIn(reason, result['reasons'])
                self.assertEqual(guard.observation(result, NOW)['verdict'], 'TRIP')
        sample = self.sample()
        sample['custody']['missing'] = 1
        del sample['measured_held_vad_speech_seconds']
        result = guard.observer_record(sample, '2026-10-29T04:00:00Z')
        self.assertIn('T1_custody_missing_or_mismatch', result['reasons'])
        self.assertEqual(result['hard3']['T2'], 'UNKNOWN')

    def test_unknown_sample_never_claims_hard_three_clean(self):
        result = guard.observer_record({}, '2026-10-29T04:00:00Z')
        self.assertEqual(set(result['hard3'].values()), {'UNKNOWN'})
        self.assertEqual(guard.observation(result, NOW)['verdict'], 'BLIND')

    def test_overflow_unknown_instead_of_false_clean(self):
        sample = self.sample()
        sample.update(
            terminal_unrecovered_vad_speech_seconds=1e308,
            measured_held_vad_speech_seconds=1e308,
            terminal_unrecovered_speech_denominator_seconds=1.7e308,
        )
        record = guard.observer_record(sample, '2026-10-29T04:00:00Z')
        self.assertEqual(record['hard3']['T2'], 'UNKNOWN')

    def test_malformed_alerts_cannot_crash_or_trip(self):
        for alerts in (None, 1, ['ok', None], {}):
            latest = packet()['observer']
            latest['alerts'] = alerts
            result = guard.observation(latest, NOW)
            self.assertEqual(result['verdict'], 'CLEAN')
            self.assertIn('malformed_soft_alerts', result['alerts'])

    def test_fallback_is_not_a_clean_speech_measurement(self):
        sample = self.sample()
        sample['terminal_unrecovered_speech_vad_fallback_units'] = 1
        result = guard.observer_record(sample, '2026-10-29T04:00:00Z')
        self.assertEqual(result['hard3']['T2'], 'UNKNOWN')
        sample.update(terminal_unrecovered_vad_speech_seconds=500, terminal_unrecovered_speech_max_unit_seconds=500)
        result = guard.observer_record(sample, '2026-10-29T04:00:00Z')
        self.assertEqual(result['hard3']['T2'], 'UNKNOWN')
        self.assertEqual(result['reasons'], [])

    def test_actual_collector_adapter_ignores_old_manual_marker(self):
        path = POLICY_PATH.with_name('batch_quality_observer.py')
        spec = importlib.util.spec_from_file_location('batch_quality_observer_under_test', path)
        observer = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {'batch_quality_gate': guard}), mock.patch.object(
            sys, 'path', list(sys.path)
        ):
            spec.loader.exec_module(observer)
            with tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                sampler = root / 'sampler.py'
                (root / 'sibling.py').write_text('VALUE=3\n')
                sampler.write_text(
                    "from pathlib import Path\nimport sibling\nROOT=Path(__file__).parent\n"
                    "def sample(since, percent):\n"
                    "    return dict(marker=(ROOT/'t2-window.json').exists(), since=since, percent=percent)\n"
                )
                (root / 't2-window.json').write_text('old marker must not be read')
                empty = root / 'empty'
                empty.mkdir()
                result = observer.collect(sampler, '2026-10-29T03:30:00Z', 0, empty)
                self.assertFalse(result['marker'])
                self.assertEqual(result['percent'], 0)
                (empty / 't2-window.json').write_text('new manual marker')
                with self.assertRaisesRegex(ValueError, 'manual_marker_not_supported'):
                    observer.collect(sampler, '2026-10-29T03:30:00Z', 0, empty)

    def test_stale_census_retains_known_harm_but_cannot_prove_clean(self):
        sample = self.sample()
        sample['rows_read_at'] = '2026-10-29T03:00:00Z'
        self.assertEqual(set(guard.observer_record(sample, '2026-10-29T04:00:00Z')['hard3'].values()), {'UNKNOWN'})
        sample['custody']['missing'] = 1
        result = guard.observer_record(sample, '2026-10-29T04:00:00Z')
        self.assertIn('T1_custody_missing_or_mismatch', result['reasons'])
        result['at'] = '2026-10-29T03:00:00Z'
        self.assertEqual(guard.observation(result, NOW)['verdict'], 'BLIND')

    def test_all_soft_signals_alert_only_even_old_observer_calls_them_trip(self):
        for reason in SOFT:
            with self.subTest(reason=reason):
                result = guard.classify('TRIP', [reason])
                self.assertEqual(result, dict(verdict='CLEAN', reasons=[], alerts=[reason]))

    def test_raw_soft_metrics_are_reported_and_do_not_trip(self):
        sample = self.sample()
        sample.update(t3_pending_over7200=3, t3_projection_over900=10, terminal_batch_units=100, failed_held=20)
        result = guard.observer_record(sample, '2026-10-29T04:00:00Z')
        self.assertEqual(result['verdict'], 'CLEAN')
        self.assertIn('T3_admitted_nonterminal_over2h', result['alerts'])
        self.assertIn('T5_failed_held_over2pct', result['alerts'])

    def test_mixed_trip_retains_each_hard_signal(self):
        for reason in guard.HARD:
            with self.subTest(reason=reason):
                result = guard.classify('TRIP', SOFT + [reason])
                self.assertEqual(result['verdict'], 'TRIP')
                self.assertEqual(result['reasons'], [reason])

    def test_single_entry_gate_soft_noise_does_not_require_seals_or_markers(self):
        p = packet()
        p['observer'].update(verdict='TRIP', reasons=SOFT)
        result = guard.entry_check(p, NOW)
        self.assertEqual(result['verdict'], 'READY_FOR_LEAD_ENTRY', result)
        self.assertEqual(result['alerts'], sorted(SOFT))

    def test_each_gate_dependency_is_required(self):
        mutations = [
            lambda p: p['errclass'].update(untriaged_new_classes=1),
            lambda p: p['errclass'].update(untriaged_new_classes=False),
            lambda p: p['errclass'].update(baseline_hours=23),
            lambda p: p['errclass'].update(includes_zero_percent_traffic=False),
            lambda p: p['replay'].update(serving_sha='b' * 40),
            lambda p: p['replay'].update(verdict='FAIL'),
            lambda p: p['replay'].update(at='2026-10-29T03:00:00Z'),
            lambda p: p['observer'].update(hard3=dict(T1='CLEAN', T2='UNKNOWN', T4='CLEAN')),
            lambda p: p['observer'].update(verdict='TRIP', reasons=['T4_unsafe_parakeet_route']),
            lambda p: p['observer'].update(at='2026-10-29T03:00:00Z'),
            lambda p: p['observer'].update(observation_since='2026-10-29T03:59:00Z'),
            lambda p: p['observer'].update(observed_through='2026-10-29T03:59:59Z'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                p = packet()
                mutate(p)
                self.assertEqual(guard.entry_check(p, NOW)['verdict'], 'WAIT')

    def test_missing_evidence_is_unknown_never_synthetic_clean(self):
        for latest in (None, {}, dict(at='2026-10-29T04:00:00Z', verdict='TRIP', reasons=[])):
            self.assertEqual(guard.observation(latest, NOW)['verdict'], 'BLIND')


if __name__ == '__main__':
    unittest.main()
