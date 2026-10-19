"""Contract (h) 12h legacy-dark soak checks."""

import io
import json

from scripts.parity import soak_check as sc

DRAINING = sc.parse_iso('2026-10-21T14:00:00Z')
DARK = sc.parse_iso('2026-10-21T15:10:00Z')
QUEUES = sc.ENVS['prod']['queues']


def gate(status='PASS', reason=None, percent=100.0, breaches=0):
    return {
        'status': status,
        'reason': reason,
        'percent': percent,
        'sample': {
            'percent': percent,
            'first_summary_dispatch_breaches': breaches,
            'first_summary_dispatch_measured_count': 30,
            'first_summary_status': 'PASS',
        },
    }


def evidence(**changes):
    ev = {
        'legacy_admissions_since_draining': 0.0,
        'legacy_queue_depths': {q: 0 for q in QUEUES},
        'task_target_errors': {'5xx': 0, '429': 0, '503': 0},
        'lost_recordings': {
            'since': '2026-10-21T14:00:00Z',
            'accepted_content_ids': 900,
            'receipted_or_terminal_content_ids': 900,
            'lost_content_ids': 0,
            'legacy_and_batch_content_ids': 0,
        },
        'provider_stt': {'byok_uploads': 3, 'unsupported_language_uploads': 2, 'served_by_provider_stt': 5},
        'cap_hold': {'redrives_total': 0, 'redrives_served_by_batch': 0},
        'upload_2xx_by_build': {
            'b1': {'rate': 0.995, 'baseline_rate': 0.996, 'requests': 4000},
            'b2': {'rate': 0.90, 'baseline_rate': 0.99, 'requests': 10},
        },
        'reason_unknown_ratio': {'live_stt': 0.001, 'parity': 0.0},
    }
    ev.update(changes)
    return ev


def run(ev, g=None):
    return sc.evaluate('prod', ev, gate() if g is None else g, draining_since=DRAINING, dark_since=DARK)


def by_check(report):
    return {c['check']: c for c in report['checks']}


def test_all_ten_checks_pass():
    report = run(evidence())
    assert report['status'] == 'PASS', [(c['check'], c['status'], c['reason']) for c in report['checks']]
    assert [c['check'] for c in report['checks']] == list(sc.CHECKS)
    assert sc.verdict_line(report) == 'SOAK_PASS'


def test_fleet_gate_must_pass_at_100_percent():
    assert by_check(run(evidence(), gate(percent=75.0)))['fleet_gate']['reason'] == 'gate_not_at_100'
    failed = run(evidence(), gate('FAIL', 'stuck_job_over_30m'))
    assert failed['status'] == 'FAIL' and failed['data_loss'] is True
    assert by_check(run(evidence(), gate('PENDING', 'first_summary_sample')))['fleet_gate']['status'] == 'PENDING'


def test_legacy_admission_in_dark_is_data_loss():
    report = run(evidence(legacy_admissions_since_draining=1.0))
    assert report['status'] == 'FAIL' and report['data_loss'] is True
    assert report['failing_check'] == 'legacy_admissions'


def test_all_four_legacy_queues_including_backfill_fresh():
    assert 'sync-backfill-fresh' in QUEUES and len(QUEUES) == 4
    depths = {q: 0 for q in QUEUES}
    depths['sync-backfill-fresh'] = 3
    assert by_check(run(evidence(legacy_queue_depths=depths)))['legacy_queues']['status'] == 'FAIL'
    del depths['sync-backfill-fresh']
    depths['sync-jobs'] = 0
    assert by_check(run(evidence(legacy_queue_depths=depths)))['legacy_queues']['status'] == 'PENDING'


def test_task_target_retryable_statuses_fail():
    report = run(evidence(task_target_errors={'5xx': 0, '429': 2, '503': 0}))
    assert by_check(report)['task_target_errors']['status'] == 'FAIL'


def test_lost_recording_census_must_start_at_draining_not_dark():
    late = evidence()
    late['lost_recordings'] = {**late['lost_recordings'], 'since': '2026-10-21T15:10:00Z'}
    assert by_check(run(late))['lost_recordings']['reason'] == 'census_starts_after_draining'


def test_lost_or_double_processed_content_ids_fail_as_data_loss():
    lost = evidence()
    lost['lost_recordings'] = {
        **lost['lost_recordings'],
        'receipted_or_terminal_content_ids': 899,
        'lost_content_ids': 1,
    }
    report = run(lost)
    assert report['failing_check'] == 'lost_recordings' and report['data_loss'] is True
    double = evidence()
    double['lost_recordings'] = {**double['lost_recordings'], 'legacy_and_batch_content_ids': 1}
    assert by_check(run(double))['lost_recordings']['reason'] == 'double_processed_content_id'


def test_data_loss_check_is_reported_first_when_several_fail():
    ev = evidence(task_target_errors={'5xx': 1, '429': 0, '503': 0}, legacy_admissions_since_draining=2)
    assert run(ev)['failing_check'] == 'legacy_admissions'


def test_provider_stt_and_cap_hold():
    assert (
        by_check(run(evidence(provider_stt={'byok_uploads': 0, 'unsupported_language_uploads': 0})))['provider_stt'][
            'reason'
        ]
        == 'zero_traffic'
    )
    short = {'byok_uploads': 3, 'unsupported_language_uploads': 2, 'served_by_provider_stt': 4}
    assert by_check(run(evidence(provider_stt=short)))['provider_stt']['status'] == 'FAIL'
    held = {'redrives_total': 5, 'redrives_served_by_batch': 4}
    assert by_check(run(evidence(cap_hold=held)))['cap_hold']['status'] == 'FAIL'


def test_first_summary_breach_fails():
    assert by_check(run(evidence(), gate(breaches=1)))['first_summary']['status'] == 'FAIL'


def test_upload_2xx_drop_over_one_point_for_a_judged_build():
    builds = {'b1': {'rate': 0.984, 'baseline_rate': 0.995, 'requests': 500}}
    assert by_check(run(evidence(upload_2xx_by_build=builds)))['upload_2xx']['status'] == 'FAIL'
    tiny = {'b1': {'rate': 0.5, 'baseline_rate': 0.995, 'requests': 49}}
    assert by_check(run(evidence(upload_2xx_by_build=tiny)))['upload_2xx']['status'] == 'PENDING'


def test_reason_unknown_ratio_limit():
    assert by_check(run(evidence(reason_unknown_ratio={'live_stt': 0.02})))['reason_unknown']['status'] == 'FAIL'


def test_unmeasured_is_pending_never_pass():
    report = sc.evaluate('prod', {}, None, draining_since=DRAINING, dark_since=DARK)
    assert report['status'] == 'PENDING'
    assert all(c['status'] == 'PENDING' for c in report['checks'])


def test_staging_uses_staging_queue_names():
    report = sc.evaluate('staging', evidence(), gate(), draining_since=DRAINING, dark_since=DARK)
    assert set(by_check(report)['legacy_queues']['measured']) == set(sc.ENVS['staging']['queues'])
    assert by_check(report)['legacy_queues']['status'] == 'PENDING'  # prod names do not satisfy staging


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_queue_depth_collector_reads_tasks_count_and_marks_unreadable_none():
    def opener(request, timeout):
        if 'sync-jobs-fresh' in request.full_url:
            raise OSError('boom')
        return _Response(json.dumps({'stats': {'tasksCount': '7'}}).encode())

    depths = sc.queue_depths('p', QUEUES, 'token', opener)
    assert depths['sync-jobs'] == 7 and depths['sync-jobs-fresh'] is None


def test_legacy_admission_series_absent_is_unmeasured():
    def opener(request, timeout):
        return _Response(json.dumps({'status': 'success', 'data': {'result': []}}).encode())

    assert sc.legacy_admissions_since('p', 600, 't', opener) is None


def test_cli_end_to_end(tmp_path, capsys):
    fleet = tmp_path / 'fleet.txt'
    fleet.write_text(json.dumps(gate()['sample']) + '\nGATE_PASS\n')
    ev = tmp_path / 'ev.json'
    ev.write_text(json.dumps(evidence()))
    out = tmp_path / 'soak.json'
    code = sc.main(
        [
            '--draining-since',
            '2026-10-21T14:00:00Z',
            '--dark-since',
            '2026-10-21T15:10:00Z',
            '--fleet-output',
            str(fleet),
            '--evidence',
            str(ev),
            '--output',
            str(out),
        ]
    )
    assert code == 0 and capsys.readouterr().out.strip().endswith('SOAK_PASS')
    assert json.loads(out.read_text())['status'] == 'PASS'
