"""Contract (h) legacy-dark soak checks and the evidence-based window (6h floor, David 2026-10-20)."""

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
            'first_summary_dispatch_max_seconds': 90.0,
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


def test_first_summary_uses_the_strict_121s_limit_and_a_dispatch_floor():
    late = gate()
    late['sample']['first_summary_dispatch_max_seconds'] = 123.0  # inside the gate's 125s tolerance
    assert by_check(run(evidence(), late))['first_summary']['status'] == 'FAIL'
    thin = gate()
    thin['sample']['first_summary_dispatch_measured_count'] = 0
    check = by_check(run(evidence(), thin))['first_summary']
    assert (check['status'], check['reason']) == ('PENDING', 'sample_below_minimum')
    unmeasured = gate()
    del unmeasured['sample']['first_summary_dispatch_measured_count']
    assert by_check(run(evidence(), unmeasured))['first_summary']['status'] == 'PENDING'
    no_max = gate()
    del no_max['sample']['first_summary_dispatch_max_seconds']  # a dropped field is not a zero breach
    check = by_check(run(evidence(), no_max))['first_summary']
    assert (check['status'], check['reason']) == ('PENDING', 'input_invalid')


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


# --- the window: evidence-based soak with a 6h floor (David, 2026-10-20) --------------------------

H = 3600


def read_at(offset, *, accepted=None, completed=3000, census_age=H, **changes):
    """One SOAK read ``offset`` seconds after dark, as main() would keep it."""
    at = DARK + offset
    ev = evidence(**changes)
    if 'lost_recordings' not in changes:
        ev['lost_recordings'] = dict(
            ev['lost_recordings'],
            until=sc.iso(at - census_age),
            accepted_content_ids=accepted if accepted is not None else 900 + int(offset // 6),
        )
        ev['lost_recordings']['receipted_or_terminal_content_ids'] = ev['lost_recordings']['accepted_content_ids']
    g = gate()
    g['sample']['completed'] = completed
    report = run(ev, g)
    report['observed_at'] = sc.iso(at)
    return report


def series(hours=6, step=30 * 60, **kw):
    return [read_at(t, **kw) for t in range(step, int(hours * H) + 1, step)]


def window(reads, now=None):
    last = max((sc.parse_iso(r['observed_at']) for r in reads if 'observed_at' in r), default=DARK)
    return sc.evaluate_window('prod', reads, dark_since=DARK, now=last if now is None else now)


def test_window_passes_at_six_hours_with_every_read_green_and_volume():
    w = window(series())
    assert (w['status'], w['reason']) == ('PASS', 'pass'), w
    assert w['elapsed_seconds'] == 6 * H and w['batch_completions'] == 3000
    assert w['uploads_accepted'] == 3300 and w['floors'] == sc.WINDOW_FLOORS['prod']
    assert sc.window_line(w) == 'SOAK_WINDOW_PASS pass'


def test_window_floor_is_six_hours_not_twelve():
    assert sc.MIN_SOAK_SECONDS == 6 * H
    assert window(series(hours=5.5))['reason'] == 'soak_under_6h'


def test_window_fails_on_any_red_read_and_carries_data_loss():
    reads = series()
    reads[3] = read_at(
        4 * 30 * 60,
        lost_recordings=dict(evidence()['lost_recordings'], lost_content_ids=2, receipted_or_terminal_content_ids=898),
    )
    w = window(reads)
    assert w['status'] == 'FAIL' and w['data_loss'] and w['reason'].startswith('read_failed:lost_recordings')


def test_window_pending_when_any_read_was_not_green():
    reads = series()
    reads[2] = read_at(3 * 30 * 60, reason_unknown_ratio={})
    w = window(reads)
    assert (w['status'], w['reason']) == ('PENDING', 'read_not_green:reason_unknown:input_missing')


def test_window_pending_on_an_unobserved_stretch():
    reads = series()
    del reads[4:6]  # a 90-minute hole
    assert window(reads)['reason'] == 'read_gap'
    # The first read must also follow dark closely, and the window must still be current.
    assert window(series()[2:])['reason'] == 'read_gap'
    assert window(series(), now=DARK + 6 * H + 46 * 60)['reason'] == 'read_gap'


def test_window_needs_a_fresh_final_census():
    reads = series()
    reads[-1] = read_at(6 * H, census_age=2 * H)
    assert window(reads)['reason'] == 'final_census_stale'
    reads[-1] = read_at(6 * H)
    del reads[-1]['checks'][4]['measured']['until']
    assert window(reads)['reason'] == 'final_census_window_missing'


def test_window_volume_floors():
    reads = series(completed=1999)
    assert window(reads)['reason'] == 'batch_completions_below_floor'
    reads = series(accepted=900)
    assert (window(reads)['reason'], window(reads)['uploads_accepted']) == ('uploads_accepted_below_floor', 0)
    reads = series()
    reads[-1]['checks'][0]['measured']['completed'] = None
    assert window(reads)['reason'] == 'window_volume_unmeasured'


def test_window_rejects_reads_from_another_window_and_empty_history():
    assert window([])['reason'] == 'no_reads'
    reads = series()
    reads[0] = dict(reads[0], dark_since='2026-10-20T00:00:00Z')
    assert window(reads)['reason'] == 'read_from_other_window'
    reads = series()
    reads[0] = {k: v for k, v in reads[0].items() if k != 'observed_at'}
    assert window(reads)['reason'] == 'read_from_other_window'


def test_cli_history_dir_judges_the_window(tmp_path, capsys, monkeypatch):
    history = tmp_path / 'soak-reads'
    for read in series()[:-1]:
        history.mkdir(exist_ok=True)
        stamp = read['observed_at'].replace('-', '').replace(':', '')
        (history / f'read-{stamp}.json').write_text(json.dumps(read))
    fleet = tmp_path / 'fleet.txt'
    sample = dict(gate()['sample'], completed=3000)
    fleet.write_text(json.dumps(sample) + '\nGATE_PASS\n')
    ev = tmp_path / 'ev.json'
    ev.write_text(
        json.dumps(
            evidence(
                lost_recordings={
                    'since': '2026-10-21T14:00:00Z',
                    'until': sc.iso(DARK + 5 * H),
                    'accepted_content_ids': 4500,
                    'receipted_or_terminal_content_ids': 4500,
                    'lost_content_ids': 0,
                    'legacy_and_batch_content_ids': 0,
                }
            )
        )
    )
    out = tmp_path / 'soak.json'
    monkeypatch.setattr(sc.time, 'time', lambda: DARK + 6 * H)
    argv = [
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
        '--history-dir',
        str(history),
    ]
    assert sc.main(argv) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-2:] == ['SOAK_PASS', 'SOAK_WINDOW_PASS pass']
    report = json.loads(out.read_text())
    assert report['window']['reads'] == 12 and report['observed_at'] == sc.iso(DARK + 6 * H)
    assert len(list(history.glob('read-*.json'))) == 12

    # An unreadable kept read leaves the window PENDING, never PASS.
    (history / 'read-zzz.json').write_text('{')
    assert sc.main(argv) == 3
    assert capsys.readouterr().out.strip().endswith('SOAK_WINDOW_PENDING history_unreadable')
