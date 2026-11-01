"""Contract (j) parity gate: row thresholds, surfaces, verdict combination, CLI."""

import json

import pytest

from scripts.parity import fleet_sample, parity_gate, rows
from scripts.parity.report_schema import ParityReason as R, Status, Surface, combine
from scripts.parity.scorers import normalize_text, owner_agreement, percentile, pooled_wer, word_errors
from scripts.rollout import ramp_controller as rc

S, P = Surface.STAGING, Surface.PROD_SHADOW


def corpus(
    batch_err=780,
    legacy_err=760,
    words=10000,
    minutes=61.0,
    b_correct=9000,
    l_correct=9050,
    pinned=True,
    baseline=0.905,
    missing=0,
):
    out = {
        'pinned': pinned,
        'corpus_minutes': minutes,
        'pipelines': {
            'batch': {
                'wer': {'errors': batch_err, 'reference_words': words},
                'speaker': {'words': 10000, 'correct_1to1': b_correct},
                'missing_units': missing,
                'scored_wer_minutes': minutes,
            },
            'legacy': {
                'wer': {'errors': legacy_err, 'reference_words': words},
                'speaker': {'words': 10000, 'correct_1to1': l_correct},
                'missing_units': 0,
                'scored_wer_minutes': minutes,
            },
        },
    }
    if baseline is not None:
        out['baseline'] = {'speaker_accuracy': baseline}
    return out


def replay(n=200, median=0.05, unreviewed=0, owner_conv=200, scored=10000, agree=9800):
    return {
        'conversations': n,
        'agreement_wer_median': median,
        'outliers_unreviewed': unreviewed,
        'owner_conversations': owner_conv,
        'owner_scored_words': scored,
        'owner_agree_words': agree,
    }


def gate_sample(**changes):
    sample = {
        'admissions': 40,
        'since_t0_stuck_jobs_over_30m': 0,
        'since_t0_oldest_unprojected_seconds': 30,
        'since_t0_recovery_obligations_over_15m': 0,
        'since_t0_projection_obligations_over_15m': 0,
        'quarantine_projection_over_900_count': 0,
        'terminal_unrecovered_speech_status': 'MEASURED',
        'terminal_unrecovered_speech_fraction': 0.001,
        'first_summary_dispatch_measured_count': 25,
        'first_summary_dispatch_breaches': 0,
        'first_summary_dispatch_max_seconds': 90.0,
        'first_summary_completion_latency_p95_seconds': 200.0,
        'first_summary_close_to_summary_p95_seconds': 210.0,
    }
    sample.update(changes)
    return sample


def census(**changes):
    out = {
        'conversation_count_batch': 1000,
        'conversation_count_legacy': 1005,
        'duration_seconds_batch': 3.6e6,
        'duration_seconds_legacy': 3.61e6,
        'accepted_content_ids': 1200,
        'receipted_or_terminal_content_ids': 1200,
        'lost_content_ids': 0,
        'privacy_violations': 0,
        'privacy_units_considered': 1200,
        'ordering_violations': 0,
        'ordering_units_considered': 1200,
    }
    out.update(changes)
    return out


COST = {
    'steady_hours': 2.5,
    'leases_per_min_per_node': 47.0,
    'batch': {
        'gpu_node_hours': 10,
        'gpu_usd_per_hour': 0.9,
        'vendor_stt_usd': 0,
        'cpu_worker_usd': 2,
        'audio_hours': 500,
    },
    'legacy': {
        'gpu_node_hours': 20,
        'gpu_usd_per_hour': 0.9,
        'vendor_stt_usd': 10,
        'cpu_worker_usd': 20,
        'audio_hours': 500,
    },
}
LEGACY = {'accept_to_summary_p95_seconds': 180.0}


# --- scorers ----------------------------------------------------------------------------------


def test_normalize_text_drops_case_punctuation_and_fillers():
    assert normalize_text('Hello, um, WORLD!  It’s fine.') == "hello world it's fine"


def test_word_errors_counts_edits_on_normalized_text():
    assert word_errors('the cat sat', 'The cat, sat.') == (0, 3)
    assert word_errors('the cat sat', 'the bat sat down') == (2, 3)
    assert word_errors('the cat', '') == (2, 2)


def test_pooled_wer_sums_before_dividing():
    result = pooled_wer([('a b c d', 'a b c d'), ('x', 'y')])
    assert result['errors'] == 1 and result['reference_words'] == 5 and result['wer'] == pytest.approx(0.2)


def test_percentile_nearest_rank():
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert percentile([], 95) is None


def test_owner_agreement_maps_labels_before_comparing():
    legacy = [{'start': i, 'end': i + 0.5, 'speaker': 'A' if i < 5 else 'B', 'is_user': i < 5} for i in range(10)]
    # Batch uses different label names and swaps one owner word to the other speaker.
    batch = [{'start': i, 'end': i + 0.5, 'speaker': 'S1' if i < 5 else 'S0'} for i in range(10)]
    batch[2]['speaker'] = 'S0'
    out = owner_agreement(legacy, batch)
    assert out['owner_known'] and out['paired_words'] == 10
    assert out['owner_agree_words'] == 9 and out['owner_scored_words'] == 10


# --- rows -------------------------------------------------------------------------------------


def test_row1_wer_delta_threshold_is_half_a_point():
    assert rows.row_1(corpus(batch_err=810, legacy_err=760), S).status is Status.PASS  # +0.5pp exactly
    failed = rows.row_1(corpus(batch_err=811, legacy_err=760), S)
    assert (failed.status, failed.reason) == (Status.FAIL, R.WER_DELTA_OVER_LIMIT)


def test_row1_pending_below_sixty_minutes_or_unpinned():
    assert rows.row_1(corpus(minutes=59.9), S).reason is R.SAMPLE_BELOW_MINIMUM
    assert rows.row_1(corpus(pinned=False), S).status is Status.PENDING
    assert rows.row_1(None, S).reason is R.INPUT_MISSING


def test_row1_corpus_without_pinned_true_or_with_missing_units_is_not_evidence():
    unpinned = corpus()
    del unpinned['pinned']
    assert (rows.row_1(unpinned, S).status, rows.row_1(unpinned, S).reason) == (Status.PENDING, R.INPUT_INVALID)
    partial = rows.row_1(corpus(missing=3), S)
    assert (partial.status, partial.reason) == (Status.PENDING, R.INPUT_INVALID)
    assert partial.measured['missing_units'] == {'batch': 3, 'legacy': 0}
    absent = corpus()
    del absent['pipelines']['legacy']['missing_units']
    assert rows.row_1(absent, S).status is Status.PENDING
    assert rows.row_2(corpus(missing=1), replay(), S).reason is R.INPUT_INVALID


def test_row1_sixty_minute_floor_is_on_scored_audio_not_the_index():
    c = corpus(minutes=72.0)
    c['pipelines']['batch']['scored_wer_minutes'] = 40.0  # index says 72 min; only 40 were scored
    assert rows.row_1(c, S).reason is R.SAMPLE_BELOW_MINIMUM
    del c['pipelines']['legacy']['scored_wer_minutes']
    assert rows.row_1(c, S).reason is R.INPUT_INVALID


def test_rows_1_7_8_are_not_applicable_on_prod_shadow():
    for row in (rows.row_1(corpus(), P), rows.row_7(census(), P), rows.row_8(census(), P)):
        assert row.status is Status.NOT_APPLICABLE


def test_rows_1b_and_2_are_evaluated_on_prod_shadow_from_the_replay_half():
    assert rows.row_1b(replay(), P).status is Status.PASS
    assert rows.row_1b(replay(median=0.2), P).reason is R.AGREEMENT_MEDIAN_OVER_LIMIT
    # Row 2 on prod shadow is owner agreement only; a corpus is ignored there.
    assert rows.row_2(None, replay(), P).status is Status.PASS
    assert rows.row_2(corpus(b_correct=5000), replay(), P).status is Status.PASS
    assert rows.row_2(None, replay(agree=9000), P).reason is R.OWNER_AGREEMENT_BELOW_LIMIT
    assert rows.row_2(None, replay(owner_conv=20), P).reason is R.SAMPLE_BELOW_MINIMUM
    assert rows.row_2(None, None, P).reason is R.INPUT_MISSING


def test_row1b_median_and_unreviewed_outliers():
    assert rows.row_1b(replay(), S).status is Status.PASS
    assert rows.row_1b(replay(median=0.081), S).reason is R.AGREEMENT_MEDIAN_OVER_LIMIT
    assert rows.row_1b(replay(n=10, unreviewed=1), S).reason is R.AGREEMENT_OUTLIER_UNREVIEWED
    assert rows.row_1b(replay(n=199), S).status is Status.PENDING


def test_row2_speaker_drop_and_owner_agreement():
    assert rows.row_2(corpus(), replay(), S).status is Status.PASS
    regressed = rows.row_2(corpus(b_correct=8940, l_correct=9050), replay(), S)  # 1.1pp drop
    assert regressed.reason is R.SPEAKER_ACCURACY_REGRESSED
    low_owner = rows.row_2(corpus(), replay(agree=9690), S)
    assert low_owner.reason is R.OWNER_AGREEMENT_BELOW_LIMIT
    assert rows.row_2(corpus(), replay(owner_conv=150), S).status is Status.PENDING


def test_row2_uses_explicit_main_baseline_over_legacy():
    c = corpus(b_correct=9000, l_correct=9500)
    c['baseline'] = {'speaker_accuracy': 0.905}
    assert rows.row_2(c, replay(), S).status is Status.PASS


def test_row2_missing_frozen_baseline_pends_instead_of_comparing_to_legacy():
    # Batch and legacy both dropped 10pp against the frozen bench: the legacy score is no baseline.
    shared_drop = corpus(b_correct=8000, l_correct=8000, baseline=None)
    result = rows.row_2(shared_drop, replay(), S)
    assert (result.status, result.reason) == (Status.PENDING, R.INPUT_MISSING)
    assert rows.row_2(corpus(b_correct=8000, l_correct=8000), replay(), S).reason is R.SPEAKER_ACCURACY_REGRESSED


def test_row3_dispatch_breach_uses_contract_121s_not_gate_tolerance():
    agg = fleet_sample.row3_aggregates(gate_sample(first_summary_dispatch_max_seconds=123.0), LEGACY)
    assert agg['first_summary_dispatch_breaches_over_121s'] == 1
    assert rows.row_3(agg, S).reason is R.FIRST_SUMMARY_DISPATCH_BREACH


def test_row3_completion_and_accept_to_summary():
    assert rows.row_3(fleet_sample.row3_aggregates(gate_sample(), LEGACY), P).status is Status.PASS
    slow = fleet_sample.row3_aggregates(gate_sample(first_summary_completion_latency_p95_seconds=301), LEGACY)
    assert rows.row_3(slow, P).reason is R.FIRST_SUMMARY_COMPLETION_P95
    late = fleet_sample.row3_aggregates(gate_sample(first_summary_close_to_summary_p95_seconds=241), LEGACY)
    assert rows.row_3(late, P).reason is R.ACCEPT_TO_SUMMARY_P95
    assert rows.row_3(fleet_sample.row3_aggregates(gate_sample(), None), P).reason is R.INPUT_MISSING
    few = fleet_sample.row3_aggregates(gate_sample(first_summary_dispatch_measured_count=19), LEGACY)
    assert rows.row_3(few, P).reason is R.SAMPLE_BELOW_MINIMUM
    no_max = gate_sample()
    del no_max['first_summary_dispatch_max_seconds']  # breaches=0 alone cannot prove the 121s limit
    assert rows.row_3(fleet_sample.row3_aggregates(no_max, LEGACY), P).reason is R.INPUT_INVALID


def test_row4_completeness_tokens_and_drift():
    ok = fleet_sample.row4_aggregates(gate_sample(), census())
    assert rows.row_4(ok, S).status is Status.PASS
    stuck = fleet_sample.row4_aggregates(gate_sample(since_t0_oldest_unprojected_seconds=1801), census())
    assert rows.row_4(stuck, S).reason is R.STUCK_JOB_OVER_30M
    speech = fleet_sample.row4_aggregates(gate_sample(terminal_unrecovered_speech_fraction=0.0021), census())
    assert rows.row_4(speech, S).reason is R.TERMINAL_UNRECOVERED_SPEECH
    drift = fleet_sample.row4_aggregates(gate_sample(), census(conversation_count_batch=1020))
    assert rows.row_4(drift, S).reason is R.COUNT_DRIFT


def test_row4_documented_systematic_difference_is_subtracted_only_with_a_reference():
    merged = census(
        conversation_count_batch=980,
        conversation_count_legacy=1005,
        systematic_difference={'count': -25, 'duration_seconds': 0},
    )
    assert rows.row_4(fleet_sample.row4_aggregates(gate_sample(), merged), S).reason is R.INPUT_INVALID
    merged['systematic_difference']['explanation_ref'] = 'parity_report#smart-merge'
    assert rows.row_4(fleet_sample.row4_aggregates(gate_sample(), merged), S).status is Status.PASS


def test_row5_lost_recordings_exactly_zero_and_consistent():
    assert rows.row_5(census(), S).status is Status.PASS
    lost = rows.row_5(census(receipted_or_terminal_content_ids=1199, lost_content_ids=1), P)
    assert (lost.status, lost.reason) == (Status.FAIL, R.LOST_RECORDINGS)
    inconsistent = rows.row_5(census(receipted_or_terminal_content_ids=1199, lost_content_ids=0), S)
    assert inconsistent.status is Status.PENDING  # never read an inconsistent census as zero


def test_row6_throughput_on_staging_and_cost_on_prod_shadow():
    assert rows.row_6(COST, S).status is Status.PASS
    # Contract (j): below 45/min/node staging still PASSes, capped at the percent the rate carries.
    slow = rows.row_6({**COST, 'leases_per_min_per_node': 30.0}, S)
    assert (slow.status, slow.measured['capped']) == (Status.PASS, True)
    assert slow.measured['max_supported_percent'] == pytest.approx(100 * 4 * 30 / 174)
    assert rows.row_6(COST, S).measured['capped'] is False
    assert rows.row_6({**COST, 'leases_per_min_per_node': None}, S).reason is R.INPUT_MISSING
    for bad_rate in (0.0, -3.0, 'nan'):
        # A rate that carries no ramp percent is never an uncapped PASS.
        result = rows.row_6({**COST, 'leases_per_min_per_node': bad_rate}, S)
        assert (result.status, result.reason) == (
            Status.PENDING,
            R.INPUT_INVALID if bad_rate != 'nan' else R.INPUT_MISSING,
        )
    assert rows.row_6(COST, P).status is Status.PASS
    pricey = {**COST, 'batch': {**COST['batch'], 'vendor_stt_usd': 100}}
    assert rows.row_6(pricey, P).reason is R.COST_ABOVE_LEGACY
    assert rows.row_6({**COST, 'steady_hours': 1.5}, P).reason is R.SAMPLE_BELOW_MINIMUM


def test_rows_7_and_8_zero_violations():
    assert rows.row_7(census(), S).status is Status.PASS
    assert rows.row_7(census(privacy_violations=1), S).reason is R.PRIVACY_VIOLATION
    assert rows.row_8(census(ordering_violations=2), S).reason is R.ORDERING_VIOLATION


# --- combination ------------------------------------------------------------------------------


def test_data_loss_fail_takes_precedence_for_rollback_zero():
    results = [
        rows.row_3(fleet_sample.row3_aggregates(gate_sample(first_summary_dispatch_breaches=1), LEGACY), P),
        rows.row_5(census(receipted_or_terminal_content_ids=1190, lost_content_ids=10), P),
    ]
    status, reason, data_loss, row = combine(results, P)
    assert (status, reason, data_loss, row) == (Status.FAIL, R.LOST_RECORDINGS, True, '5')


def test_fail_names_lowest_data_loss_row_then_lowest_row():
    lost = rows.row_5(census(receipted_or_terminal_content_ids=1190, lost_content_ids=10), S)
    privacy = rows.row_7(census(privacy_violations=1), S)
    wer = rows.row_1(corpus(batch_err=900), S)
    ordering = rows.row_8(census(ordering_violations=1), S)
    assert combine([wer, lost, privacy, ordering], S)[3] == '5'
    assert combine([wer, privacy, ordering], S)[3] == '7'
    assert combine([wer, ordering], S)[2:] == (False, '1')


def test_prod_shadow_verdict_gates_on_rows_3_to_6_only():
    report = parity_gate.evaluate(P, gate_sample=gate_sample(), legacy_baseline=LEGACY, census=census(), cost=COST)
    assert report.status is Status.PASS
    assert {r.row for r in report.rows if r.status is Status.NOT_APPLICABLE} == {'1', '7', '8'}
    # Rows 1b and 2 on David's recordings are reported but cannot change ADVANCE.
    bad = parity_gate.evaluate(
        P,
        replay=replay(median=0.2, agree=9000),
        gate_sample=gate_sample(),
        legacy_baseline=LEGACY,
        census=census(),
        cost=COST,
    )
    by_row = {r.row: r for r in bad.rows}
    assert by_row['1b'].status is Status.FAIL and by_row['2'].status is Status.FAIL
    assert bad.status is Status.PASS


def test_staging_full_pass_and_missing_inputs_pend():
    full = parity_gate.evaluate(
        S,
        corpus=corpus(),
        replay=replay(),
        gate_sample=gate_sample(),
        legacy_baseline=LEGACY,
        census=census(),
        cost=COST,
    )
    assert full.status is Status.PASS, [(r.row, r.status, r.reason) for r in full.rows]
    partial = parity_gate.evaluate(S, gate_sample=gate_sample(), legacy_baseline=LEGACY, census=census(), cost=COST)
    assert partial.status is Status.PENDING and partial.reason is R.INPUT_MISSING
    assert parity_gate.evaluate(S).status is Status.PENDING


def test_parse_gate_output_reads_last_sample_and_verdict():
    lines = ['{"admissions": 1}', 'PRE_EXISTING_DEBT 0', '{"admissions": 2}', 'GATE_FAIL stuck_job_over_30m']
    sample, status, reason = fleet_sample.parse_gate_output(lines)
    assert sample == {'admissions': 2} and (status, reason) == ('FAIL', 'stuck_job_over_30m')
    assert fleet_sample.is_data_loss_token('terminal_unrecovered_speech_over_0_2pct')
    assert not fleet_sample.is_data_loss_token('http_5xx_regression')


# --- CLI --------------------------------------------------------------------------------------


def test_cli_writes_content_free_report(tmp_path, capsys):
    replay_dir = tmp_path / 'replay'
    replay_dir.mkdir()
    words = [{'text': 'secret words here', 'start': 0, 'end': 1, 'speaker': 'A', 'is_user': True}]
    (replay_dir / 'conv-raw-key.legacy.json').write_text(json.dumps({'words': words}))
    (replay_dir / 'conv-raw-key.batch.json').write_text(json.dumps({'words': [{**words[0], 'text': 'other'}]}))
    fleet = tmp_path / 'fleet.txt'
    fleet.write_text(json.dumps(gate_sample()) + '\nGATE_PASS\n')
    (tmp_path / 'legacy.json').write_text(json.dumps(LEGACY))
    (tmp_path / 'census.json').write_text(json.dumps(census()))
    (tmp_path / 'cost.json').write_text(json.dumps(COST))
    out = tmp_path / 'parity_report.json'
    code = parity_gate.main(
        [
            '--surface',
            'prod-shadow',
            '--output',
            str(out),
            '--replay-dir',
            str(replay_dir),
            '--fleet-sample',
            str(fleet),
            '--legacy-baseline',
            str(tmp_path / 'legacy.json'),
            '--census',
            str(tmp_path / 'census.json'),
            '--cost',
            str(tmp_path / 'cost.json'),
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == 'PARITY_PASS'
    text = out.read_text()
    assert 'secret' not in text and 'conv-raw-key' not in text
    body = json.loads(text)
    assert body['schema_version'] == 1 and body['inputs']['fleet_gate_status'] == 'PASS'
    assert body['replay_outlier_keys'] == [parity_gate.opaque_key('conv-raw-key')]


@pytest.mark.parametrize(
    ('census_changes', 'terminal'),
    [
        ({'receipted_or_terminal_content_ids': 1199, 'lost_content_ids': 1}, 'PARITY_FAIL row_5'),
        ({'privacy_violations': 1}, 'PARITY_FAIL row_7'),
        ({'ordering_violations': 1}, 'PARITY_FAIL row_8'),
    ],
)
def test_cli_fail_terminal_line_names_the_row(tmp_path, capsys, census_changes, terminal):
    """Contract (j): the controller keys ROLLBACK_ZERO on `PARITY_FAIL row_5` / `row_7`."""
    fleet = tmp_path / 'fleet.txt'
    fleet.write_text(json.dumps(gate_sample()) + '\nGATE_PASS\n')
    (tmp_path / 'legacy.json').write_text(json.dumps(LEGACY))
    (tmp_path / 'census.json').write_text(json.dumps(census(**census_changes)))
    (tmp_path / 'cost.json').write_text(json.dumps(COST))
    out = tmp_path / 'parity_report.json'
    code = parity_gate.main(
        [
            '--surface',
            'staging',
            '--output',
            str(out),
            '--fleet-sample',
            str(fleet),
            '--legacy-baseline',
            str(tmp_path / 'legacy.json'),
            '--census',
            str(tmp_path / 'census.json'),
            '--cost',
            str(tmp_path / 'cost.json'),
        ]
    )
    assert code == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == terminal
    body = json.loads(out.read_text())
    assert body['failing_row'] == terminal.rsplit('_', 1)[-1]
    assert body['data_loss'] is (terminal != 'PARITY_FAIL row_8')


@pytest.mark.parametrize(
    ('census_changes', 'action'),
    [
        ({'receipted_or_terminal_content_ids': 1199, 'lost_content_ids': 1}, 'ROLLBACK_ZERO'),
        ({'ordering_violations': 1}, 'ROLLBACK_ONE'),
    ],
)
def test_prod_shadow_fail_line_maps_through_the_ramp_controller(tmp_path, capsys, census_changes, action):
    """End to end with lane 6's parser: a row-5 parity FAIL must roll back to zero, not one step."""
    fleet = tmp_path / 'fleet.txt'
    fleet.write_text(json.dumps(gate_sample()) + '\nGATE_PASS\n')
    (tmp_path / 'legacy.json').write_text(json.dumps(LEGACY))
    (tmp_path / 'census.json').write_text(json.dumps(census(**census_changes)))
    (tmp_path / 'cost.json').write_text(json.dumps(COST))
    argv = ['--surface', 'staging', '--output', str(tmp_path / 'r.json'), '--fleet-sample', str(fleet)]
    argv += ['--legacy-baseline', str(tmp_path / 'legacy.json'), '--census', str(tmp_path / 'census.json')]
    argv += ['--cost', str(tmp_path / 'cost.json')]
    code = parity_gate.main(argv)
    stdout = capsys.readouterr().out
    status, reason = rc.run_parity(['parity'], runner=lambda cmd, timeout: (code, stdout))
    verdict = rc.compose_with_parity(rc.GateVerdict('PASS', '', 0.0, 0.0, 50.0), (status, reason))
    assert rc.classify_fail(verdict.reason)[0].name == action


def test_cli_runs_with_no_extra_arguments_and_prints_throughput_cap(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert parity_gate.main(['--surface', 'prod-shadow']) == 3
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith('PARITY_PENDING ')
    assert (tmp_path / 'parity_report.json').exists()
    (tmp_path / 'cost.json').write_text(json.dumps({**COST, 'leases_per_min_per_node': 30.0}))
    parity_gate.main(['--surface', 'staging', '--cost', str(tmp_path / 'cost.json')])
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-2] == f'max_supported_percent {round(100 * 4 * 30 / 174, 1)}'
    assert lines[-1].startswith('PARITY_PENDING ')


def test_cli_missing_inputs_exit_pending(tmp_path, capsys):
    code = parity_gate.main(['--surface', 'staging', '--output', str(tmp_path / 'r.json')])
    assert code == 3
    assert capsys.readouterr().out.strip().splitlines()[-1].startswith('PARITY_PENDING ')
