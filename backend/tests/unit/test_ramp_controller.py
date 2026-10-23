"""Contract (g): ramp-controller decisions, authority limits, and a hermetic full-ladder rehearsal."""

from dataclasses import replace
import json
import math
from pathlib import Path
import re

import pytest

from database import rollout_cohorts as store
from scripts.rollout import inject_gate, ramp_controller as rc, ramp_set
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.rollout import runtime_percent as rp
from utils.rollout.runtime_percent import RampSnapshot, write_ramp

H = 3600


def snap(percent=10.0, **kw):
    fields = dict(
        revision=4,
        percents={'batch-pipeline': percent, 'first-summary': percent},
        legacy_sync='on',
        locked_by=None,
        source='firestore',
        env='prod',
    )
    fields.update(kw)
    return RampSnapshot(**fields)


def verdict(status='PASS', reason='', percent=10.0, hold=2 * H):
    return rc.GateVerdict(status, reason, 0.0, hold, percent, {})


def decide(s, v, **ctx):
    return rc.decide(s, v, name='batch-pipeline', now=0.0, context=rc.ControllerContext(**ctx))


def test_advance_one_step_after_hold():
    d = decide(snap(10.0), verdict(percent=10.0, hold=H))
    assert (d.action, d.from_percent, d.to_percent, d.reason) == (
        rc.Action.ADVANCE,
        10.0,
        25.0,
        rc.RampReason.GATE_PASS,
    )


DAY = 86400
NOON_UTC = 20 * DAY + 18 * H  # 18:00Z
NIGHT_UTC = 20 * DAY + 8 * H  # 08:00Z


def five(hold=H, observed_at=NOON_UTC, completed=rc.FIVE_PERCENT_MIN_COMPLETED, **kw):
    raw = {} if completed is None else {'completed': completed}
    return rc.GateVerdict(kw.pop('status', 'PASS'), '', observed_at, hold, 5.0, raw)


def test_five_percent_holds_one_hour_ruling_10_20():
    assert rc.HOLD_SECONDS[5.0] == H
    assert decide(snap(5.0), five(hold=H - 1)).detail == 'hold_incomplete'
    assert decide(snap(5.0), five(hold=H)).to_percent == 10.0


def test_five_percent_has_no_time_of_day_requirement():
    # Lead ruling on #22886: "5% hold 1h" means 1h; a night hold with enough completions advances.
    assert not hasattr(rc, 'daytime_seconds')
    assert decide(snap(5.0), five(hold=H, observed_at=NIGHT_UTC)).to_percent == 10.0


@pytest.mark.parametrize(
    ('completed', 'detail'),
    [
        (None, 'sample_unmeasured'),
        ('150', 'sample_unmeasured'),
        (True, 'sample_unmeasured'),
        (149, 'sample_below_floor'),
    ],
)
def test_five_percent_needs_the_completion_floor(completed, detail):
    d = decide(snap(5.0), five(completed=completed))
    assert (d.action, d.reason, d.detail) == (rc.Action.HOLD, rc.RampReason.HOLD_INCOMPLETE, detail)


def test_five_percent_sample_floor_scales_only_for_a_staging_rehearsal():
    v = five(hold=H / 60, observed_at=NOON_UTC, completed=3)
    assert decide(snap(5.0), v, hold_scale=1 / 60).to_percent == 10.0
    assert decide(snap(5.0), v).action is rc.Action.HOLD


def test_other_steps_need_no_sample_floor():
    v = rc.GateVerdict('PASS', '', NIGHT_UTC, H, 10.0, {})
    assert decide(snap(10.0), v).to_percent == 25.0


@pytest.mark.parametrize('status', ['PENDING', 'NO_WORK'])
def test_pending_and_no_work_hold(status):
    d = decide(snap(), verdict(status))
    assert d.action is rc.Action.HOLD and d.reason is rc.RampReason.GATE_PENDING


def test_never_past_one_hundred():
    d = decide(snap(100.0), verdict(percent=100.0))
    assert d.action is rc.Action.HOLD and d.reason is rc.RampReason.AT_CEILING


def test_off_ladder_value_moves_to_next_step_without_skipping():
    # 7% sits on the 5% step, so the 5% sample floor applies.
    assert decide(snap(7.0), replace(five(hold=4 * H), percent=7.0)).to_percent == 10.0
    assert decide(snap(7.0), verdict(percent=7.0, hold=4 * H)).detail == 'sample_unmeasured'
    assert decide(snap(7.0), verdict('FAIL', 'http_5xx_regression', percent=7.0)).to_percent == 5.0


@pytest.mark.parametrize(
    'reason',
    [
        'http_5xx_regression',
        'unrecovered_quarantine',
        'first_summary_dispatch_contract',
        'recovery_spend_unknown',
        'quarantine_projection_p95_over_5m',
        'pre_existing_debt_growing',
        'projection_transient_rate',
        'first_summary_completion_outlier',
        'quarantine_projection_p95_unknown',
        'recovery_spend_over_0_005_per_worn_hour',
        'unsafe_parakeet_language_route',
        'language_route_unknown',
        'parity_fail',
        'parity_row_3',
    ],
)
def test_ordinary_fail_rolls_back_one(reason):
    d = decide(snap(25.0), verdict('FAIL', reason, percent=25.0))
    assert (d.action, d.to_percent) == (rc.Action.ROLLBACK_ONE, 10.0)


@pytest.mark.parametrize(
    'reason, expected',
    [
        ('terminal_unrecovered_speech_over_0_2pct', rc.RampReason.DATA_LOSS),
        ('terminal_unrecovered_speech_unknown', rc.RampReason.DATA_LOSS),
        ('terminal_unrecovered_speech_unit_over_120s', rc.RampReason.DATA_LOSS),
        ('stuck_job_over_30m', rc.RampReason.DATA_LOSS),
        ('obligation_over_15m', rc.RampReason.DATA_LOSS),
        ('projection_error', rc.RampReason.DATA_LOSS),
        ('projection_stalled', rc.RampReason.DATA_LOSS),
        ('parity_row_5', rc.RampReason.DATA_LOSS),
        ('parity_row_7', rc.RampReason.PRIVACY),
    ],
)
def test_data_loss_and_privacy_roll_back_to_zero(reason, expected):
    d = decide(snap(50.0), verdict('FAIL', reason, percent=50.0, hold=0))
    assert (d.action, d.to_percent, d.reason) == (rc.Action.ROLLBACK_ZERO, 0.0, expected)


@pytest.mark.parametrize(
    'reason',
    [
        'ro_prod_unavailable',
        'unexpected_read_or_parse_failure',
        'gate_output_unparsed',
        'timeout_incomplete',
        'usage_fleet_gate.sh',
        # fleet_gate.sh GateError tokens: the gate could not judge the cohort (C1), never a rollback.
        'ro_dev_unavailable',
        'http_route_logs_truncated_or_invalid',
        'http_route_logs_read_failed',
        'projection_logs_truncated_or_invalid',
        'job_read_limit_exceeded',
        'http_metric_invalid_response',
        'canary_allowlists_not_matching_singleton',
        'projection_completion_precedes_quarantine',
        'parity_not_run',
        'some_future_gate_error',
    ],
)
def test_gate_execution_failures_hold(reason):
    d = decide(snap(25.0), verdict('FAIL', reason, percent=25.0))
    assert d.action is rc.Action.HOLD
    assert rc.gate_unavailable(verdict('FAIL', reason, percent=25.0))


@pytest.mark.parametrize(
    'kw, ctx',
    [
        ({'legacy_sync': 'draining'}, {}),
        ({'legacy_sync': 'dark'}, {}),
        ({'locked_by': 'lead'}, {}),
        ({}, {'train_lock_held': True}),
        ({}, {'rollbacks_in_window': 2}),
    ],
)
def test_refusals_hold_and_page_on_fail(kw, ctx):
    d = decide(snap(25.0, **kw), verdict('FAIL', 'projection_error', percent=25.0), **ctx)
    assert d.action is rc.Action.HOLD and d.reason is rc.RampReason.LOCKED_BY_OPERATOR and d.page
    assert decide(snap(25.0, **kw), verdict(percent=25.0), **ctx).action is rc.Action.HOLD


def test_write_rate_limit_and_gate_percent_match():
    d = decide(snap(), verdict(), seconds_since_last_controller_write=599)
    assert (d.action, d.detail) == (rc.Action.HOLD, 'write_rate_limited')
    assert decide(snap(10.0), verdict(percent=5.0)).action is rc.Action.HOLD


def test_rollback_is_not_write_rate_limited():
    # Time-inflation audit item 9: a FAIL minutes after an advance must roll back on this tick, not wait out
    # the 10-minute write interval. The rate limit is for advances; ROLLBACK_STOP_COUNT bounds rollbacks.
    d = decide(
        snap(25.0), verdict('FAIL', 'pre_existing_debt_growing', percent=25.0), seconds_since_last_controller_write=10
    )
    assert (d.action, d.from_percent, d.to_percent) == (rc.Action.ROLLBACK_ONE, 25.0, 10.0)
    d = decide(snap(), verdict('FAIL', 'projection_error'), seconds_since_last_controller_write=10)
    assert (d.action, d.to_percent) == (rc.Action.ROLLBACK_ZERO, 0.0)
    # The two-rollback stop still holds even right after a write.
    d = decide(
        snap(),
        verdict('FAIL', 'projection_error'),
        seconds_since_last_controller_write=10,
        rollbacks_in_window=rc.ROLLBACK_STOP_COUNT,
    )
    assert d.action is rc.Action.HOLD and d.detail == 'stopped_after_two_rollbacks'


def test_resume_after_gap_never_advances_but_still_rolls_back():
    assert decide(snap(), verdict(), resumed_after_gap=True).action is rc.Action.HOLD
    assert decide(snap(), verdict('FAIL', 'projection_error'), resumed_after_gap=True).action is rc.Action.ROLLBACK_ZERO


def test_zero_needs_operator_and_retire_is_never_decided():
    assert decide(snap(0.0), verdict(percent=0.0)).action is rc.Action.HOLD
    with pytest.raises(ValueError):
        rc.decide(snap(), verdict(), name='batch-live-stt-retire', now=0.0)


def test_unseeded_snapshot_holds():
    d = decide(snap(source='env_default', percents={}), verdict(percent=0.0))
    assert d.action is rc.Action.HOLD


def test_follower_divergence_holds():
    s = snap(percents={'batch-pipeline': 10.0, 'first-summary': 5.0})
    out = rc.decide_all(s, verdict(percent=10.0, hold=H), now=0.0)
    assert [d.action for d in out] == [rc.Action.ADVANCE, rc.Action.HOLD]


def test_gate_output_parsing():
    out = '{"admissions": 12, "completed": 11, "owner": "x y"}\nPRE_EXISTING_DEBT 0\nGATE_FAIL projection_stalled\n'
    status, reason, raw = rc.parse_gate_output(out, 1)
    assert (status, reason) == ('FAIL', 'projection_stalled')
    assert rc.compact_raw(raw) == {'admissions': 12, 'completed': 11}
    assert rc.parse_gate_output('GATE_PASS\n', 1)[:2] == ('FAIL', 'gate_output_unparsed')
    assert rc.parse_gate_output('nothing', 0)[:2] == ('FAIL', 'gate_output_unparsed')


def test_parity_composition():
    v = verdict(percent=25.0)
    assert rc.compose_with_parity(v, ('PASS', '')).status == 'PASS'
    assert rc.compose_with_parity(v, ('PENDING', 'sample')).status == 'PENDING'
    assert rc.compose_with_parity(v, ('FAIL', 'row_5')).reason == 'parity_row_5'
    assert rc.compose_with_parity(v, ('FAIL', 'row_3')).reason == 'parity_row_3'
    assert rc.compose_with_parity(v, ('FAIL', 'other')).reason == 'parity_fail'
    assert rc.classify_fail('parity_row_3')[0] is rc.Action.ROLLBACK_ONE


@pytest.mark.parametrize(
    ('token', 'action'),
    [
        ('first_summary_deadline', rc.Action.ROLLBACK_ONE),
        ('failed_held_over_budget', rc.Action.ROLLBACK_ZERO),
    ],
)
def test_gate_verdict_tokens_roll_back(token, action):
    # M1 review L06-2: a verdict token missing from the closed lists HOLDs as "gate unavailable".
    assert rc.classify_fail(token)[0] is action


@pytest.mark.parametrize(
    'token',
    ['unsafe_parakeet_language_route', 'language_route_unknown'],
)
def test_language_route_verdicts_roll_back_one_not_hold(token):
    # P26 fleet-gate tokens: wrong-language Parakeet routing is a cohort verdict, and missing route evidence
    # fails closed like recovery_spend_unknown — neither may strand a failing cohort as "gate unavailable".
    assert rc.classify_fail(token) == (rc.Action.ROLLBACK_ONE, rc.RampReason.GATE_FAIL)
    assert not rc.gate_unavailable(verdict('FAIL', token, percent=25.0))
    d = decide(snap(25.0), verdict('FAIL', token, percent=25.0))
    assert (d.action, d.to_percent) == (rc.Action.ROLLBACK_ONE, 10.0)


def test_every_scorer_fail_token_is_a_classified_verdict():
    # testing/pipeline_sim/scorer.py is the in-repo fleet_gate stand-in; each verdict it emits must act.
    source = (Path(__file__).resolve().parents[2] / 'testing' / 'pipeline_sim' / 'scorer.py').read_text()
    tokens = set(re.findall(r'GATE_FAIL ([a-z0-9_]+)', source))
    assert tokens
    unclassified = {t for t in tokens - rc.INCOMPLETE_SAMPLE_TOKENS if rc.classify_fail(t)[0] is None}
    assert unclassified == set()


def test_prod_arguments_are_guarded(monkeypatch):
    parse = rc.build_parser().parse_args
    base = ['--env', 'prod', '--gate-cmd', 'fleet_gate.sh']
    assert rc.validate_args(parse(base + ['--hold-scale', '0.1'])) == 'hold_scale_is_staging_only'
    assert (
        rc.validate_args(parse(['--env', 'prod', '--gate-cmd', 'inject_gate.py --plan p --']))
        == 'injected_gate_is_staging_only'
    )
    assert rc.validate_args(parse(base + ['--apply'])) == 'prod_apply_requires_train_lock_cmd'
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    no_preflight = base + ['--apply', '--train-lock-cmd', 'x', '--parity-cmd', 'y']
    assert rc.validate_args(parse(no_preflight)) == 'prod_apply_requires_preflight_cmd'
    full = no_preflight + ['--preflight-cmd', 'z']
    assert rc.validate_args(parse(full)) == 'operator_tier_mismatch'
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    assert rc.validate_args(parse(full)) is None


# ---------------------------------------------------------------------------
# Hermetic rehearsal: real CAS writes (StrictFirestore), scripted gate, fake clock.
# ---------------------------------------------------------------------------


_ACTIVE = []


@pytest.fixture(autouse=True)
def rig_clock(monkeypatch):
    # History `at` stamps follow the rig's clock so the 10-minute and 24h windows are deterministic.
    _ACTIVE.clear()
    real = rp._utc_now_iso
    monkeypatch.setattr(rp, '_utc_now_iso', lambda: rc.iso(_ACTIVE[-1].now) if _ACTIVE else real())


class Rig:
    def __init__(self, env='staging', script=None):
        _ACTIVE.append(self)
        self.env = env
        self.db = StrictFirestore()
        self.now = 1_800_000_000.0
        self.script = dict(script or {})  # percent -> list of gate lines (consumed once each)
        self.state = []
        self.notes = []
        self.gate_calls = []
        self.train_lock = False

    def lead(self, change, reason):
        rev = self.document()['revision'] if self.document() else 0
        return write_ramp(
            self.env, change, expected_revision=rev, actor='lead', reason=reason, firestore_client=self.db
        )

    def document(self):
        raw = self.db.rows.get(('rollout_cohorts', '_ramp'))
        return store.normalize_ramp_document(raw) if raw else None

    def history(self, revisions):
        return [
            self.db.rows[k]
            for r in revisions
            if (k := ('rollout_cohorts', '_ramp', 'history', f'{r:010d}')) in self.db.rows
        ]

    def gate(self, since, percent):
        self.gate_calls.append(percent)
        queue = self.script.get(percent) or []
        line = queue.pop(0) if queue else 'GATE_PASS'
        status, reason, _ = rc.parse_gate_output(
            line, {'PASS': 0, 'FAIL': 1, 'NO_WORK': 2, 'PENDING': 3}[line.split()[0][5:]]
        )
        # The gate's `completed` count since the step began: enough for the 5% sample floor.
        return rc.GateVerdict(status, reason, self.now, self.now - since, percent, {'completed': 1000})

    def write(self, env, change, **kw):
        assert env == self.env
        assert set(change) == {'percents'} and set(change['percents']) <= set(rc.CONTROLLED_NAMES)
        return write_ramp(env, change, firestore_client=self.db, **kw)

    def effects(self):
        return rc.Effects(
            read_document=self.document,
            read_history=self.history,
            write=self.write,
            gate=self.gate,
            parity=None,
            train_lock_held=lambda: self.train_lock,
            append_state=self.state.append,
            notify=lambda text, page: self.notes.append((text, page)),
            clock=lambda: self.now,
        )

    def tick(self, advance_seconds=600, **kw):
        self.now += advance_seconds
        return rc.tick(self.env, self.effects(), **kw)

    def percent(self):
        return self.document()['envs'][self.env]['percents']['batch-pipeline']


def run_until(rig, target, max_ticks=200, **kw):
    for _ in range(max_ticks):
        if rig.percent() == target:
            return
        rig.tick(**kw)
    raise AssertionError(f'did not reach {target}; at {rig.percent()}')


def test_full_ladder_rehearsal_with_two_injected_rollbacks():
    rig = Rig(script={25.0: ['GATE_FAIL http_5xx_regression'], 50.0: ['GATE_FAIL obligation_over_15m']})
    rig.lead({'percents': {'batch-pipeline': 5.0, 'first-summary': 5.0, 'batch-live-stt-retire': 0.0}}, 'seed')

    run_until(rig, 25.0)
    result = rig.tick()  # injected ordinary FAIL at 25
    # first-summary is a quality floor: it advanced in lockstep but a rollback never lowers it.
    assert [d.action for d in result.decisions] == [rc.Action.ROLLBACK_ONE, rc.Action.HOLD]
    assert result.decisions[1].detail == 'quality_floor_kept' and not result.decisions[1].page
    assert rig.percent() == 10.0
    run_until(rig, 50.0)
    result = rig.tick()  # injected data-loss FAIL at 50
    assert [d.action for d in result.decisions] == [rc.Action.ROLLBACK_ZERO, rc.Action.HOLD]
    assert rig.percent() == 0.0
    assert rig.document()['envs'][rig.env]['percents']['first-summary'] == 50.0

    # Two rollbacks in 24h: stopped, even after the lead re-seeds under a lock.
    rig.lead({'locked_by': 'lead'}, 'locked_by_operator')
    rig.lead({'percents': {'batch-pipeline': 5.0, 'first-summary': 5.0}}, 'reseed')
    rig.lead({'locked_by': 'other'}, 'locked_by_operator')
    rig.lead({'locked_by': None}, 'unlock_without_ack')
    result = rig.tick(advance_seconds=4 * 3600)
    assert result.decisions[0].detail == 'stopped_after_two_rollbacks' and not result.wrote

    # The human acknowledgement (ramp_set --clear-lock) resumes the full ladder to 100 and no further.
    rig.lead({'locked_by': None}, 'lock_cleared')
    run_until(rig, 100.0, max_ticks=400)
    doc = rig.document()['envs'][rig.env]
    assert doc['percents'] == {'batch-pipeline': 100.0, 'first-summary': 100.0, 'batch-live-stt-retire': 0.0}
    assert doc['legacy_sync'] == 'on' and doc['locked_by'] is None
    result = rig.tick(advance_seconds=2 * 3600)
    assert result.decisions[0].reason is rc.RampReason.AT_CEILING and not result.wrote

    # Every controller write was one ladder step, at least 10 minutes apart; every decision was logged.
    rows = rig.history(range(rig.document()['revision'], 0, -1))
    controller = [r for r in rows if r['actor'] == rc.ACTOR]
    for row in controller:
        before, after = row['before']['percents']['batch-pipeline'], row['after']['percents']['batch-pipeline']
        assert after in rc.LADDER
        assert after == rc.next_step(before) or after == rc.previous_step(before) or after == 0.0
    times = sorted(rc.parse_iso(r['at']) for r in controller)
    assert all(b - a >= 600 for a, b in zip(times, times[1:]))
    assert all(line.split()[1] == 'ramp-controller' and ' rev=' in line for line in rig.state)
    advances = [n for n, _ in rig.notes if ' advance ' in n]
    assert advances and any(' rollback_zero ' in n for n, page in rig.notes if page)


def test_controller_never_acts_outside_on_and_pages_on_fail():
    rig = Rig(script={10.0: ['GATE_FAIL projection_error']})
    rig.lead({'percents': {'batch-pipeline': 10.0, 'first-summary': 10.0}}, 'seed')
    rig.lead({'legacy_sync': 'draining'}, 'draining')
    result = rig.tick(advance_seconds=2 * 3600)
    assert not result.wrote and rig.percent() == 10.0
    assert rig.notes and rig.notes[-1][1] is True and 'PAGE lead' in rig.notes[-1][0]


def test_train_lock_and_dry_run_write_nothing():
    rig = Rig()
    rig.lead({'percents': {'batch-pipeline': 10.0, 'first-summary': 10.0}}, 'seed')
    rig.train_lock = True
    assert not rig.tick(advance_seconds=2 * 3600).wrote
    rig.train_lock = False
    result = rig.tick(apply=False)
    assert not result.wrote and result.decisions[0].action is rc.Action.ADVANCE
    assert rig.state[-1].endswith('dry_run=1') and rig.percent() == 10.0


def test_resume_after_gap_holds_then_continues():
    rig = Rig()
    rig.lead({'percents': {'batch-pipeline': 10.0, 'first-summary': 10.0}}, 'seed')
    result = rig.tick(advance_seconds=8 * 3600, resumed_after_gap=True)
    assert not result.wrote and result.decisions[0].detail == 'resume_after_gap'
    assert any('resume_after_gap' in text for text, _ in rig.notes)
    assert rig.tick().wrote and rig.percent() == 25.0


def test_prod_requires_parity_from_25():
    rig = Rig(env='prod')
    rig.lead({'percents': {'batch-pipeline': 25.0, 'first-summary': 25.0}}, 'seed')
    result = rig.tick(advance_seconds=2 * 3600)
    assert not result.wrote and result.verdict.reason == 'parity_not_configured'


def test_heartbeat_round_trip(tmp_path):
    path = tmp_path / 'hb'
    assert rc.read_heartbeat(path) == (None, 0)
    rc.write_heartbeat(path, 123.5)
    assert rc.read_heartbeat(path) == (123.5, 0)
    rc.write_heartbeat(path, 124.0, 2)
    assert rc.read_heartbeat(path) == (124.0, 2)
    path.write_text('123.5\n')  # pre-streak format
    assert rc.read_heartbeat(path) == (123.5, 0)


def test_inject_gate_fires_once(tmp_path, capsys):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps([{'percent': 25, 'line': 'GATE_FAIL http_5xx_regression'}]))
    args = ['--plan', str(plan), '--', 'true', 'since', '1', '15', '25']
    assert inject_gate.main(args) == 1
    assert 'GATE_FAIL http_5xx_regression' in capsys.readouterr().out
    assert json.loads(plan.read_text())[0]['used'] is True
    assert inject_gate.main(args) == 0  # falls through to the real command (`true`)


def test_ramp_set_refuses_percent_writes_during_ladder():
    parse = ramp_set.build_parser().parse_args
    args = parse(['--env', 'prod', '--percent', 'batch-pipeline=50'])
    seeded = {'percents': {'batch-pipeline': 10.0}, 'locked_by': None}
    assert ramp_set.plan_change(args, seeded) == 'percent_write_requires_operator_lock'
    assert ramp_set.plan_change(args, {**seeded, 'locked_by': 'lead'})[0] == {'percents': {'batch-pipeline': 50.0}}
    assert ramp_set.plan_change(args, None)[0] == {'percents': {'batch-pipeline': 50.0}}
    assert ramp_set.plan_change(parse(['--env', 'prod', '--clear-lock']), seeded) == (
        {'locked_by': None},
        'lock_cleared',
    )


def test_ramp_set_cli_refuses_controller_actor_and_wrong_tier(monkeypatch):
    db = StrictFirestore()
    db.rows[('rollout_cohorts', '_ramp')] = {'schema_version': 1, 'revision': 0, 'envs': {}}

    monkeypatch.setattr(
        store, 'read_ramp', lambda **kw: store.normalize_ramp_document(db.rows[('rollout_cohorts', '_ramp')])
    )
    common = ['--env', 'prod', '--legacy-sync', 'draining', '--expected-revision', '0', '--reason', 'draining']
    common += [arg for pid in rc.DRAINING_PRECONDITIONS for arg in ('--precondition-met', pid)]
    assert ramp_set.main(common + ['--actor', 'ramp-controller', '--apply'], client_factory=lambda **kw: db) == 2
    monkeypatch.setenv('GCP_AGENT_TIER', 'ro-prod')
    assert ramp_set.main(common + ['--actor', 'lead', '--apply'], client_factory=lambda **kw: db) == 2
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    assert ramp_set.main(common + ['--actor', 'lead', '--apply'], client_factory=lambda **kw: db) == 0
    assert db.rows[('rollout_cohorts', '_ramp')]['envs']['prod']['legacy_sync'] == 'draining'
    assert math.isfinite(db.rows[('rollout_cohorts', '_ramp')]['revision'])


def test_gate_unavailable_escalates_every_third_consecutive_tick():
    unavailable = verdict('FAIL', 'ro_prod_unavailable')
    streak, escalations = 0, []
    for v in [unavailable] * 7 + [verdict('PASS'), unavailable]:
        streak = rc.next_unavailable_streak(streak, v)
        escalations.append(rc.should_escalate_unavailable(streak))
    assert escalations == [False, False, True, False, False, True, False, False, False]
    assert rc.gate_unavailable(verdict('FAIL', 'timeout_incomplete'))
    assert not rc.gate_unavailable(verdict('FAIL', 'projection_error'))
    assert not rc.gate_unavailable(verdict('FAIL', 'http_5xx_regression'))


def test_leaving_on_requires_every_draining_precondition():
    gates = {'cap_hold_ladder_debit', 'minimal_redrive_finished', 'provider_stt_live', 'legacy_final_pass_rehomed'}
    assert gates <= set(rc.DRAINING_PRECONDITIONS)
    parse = ramp_set.build_parser().parse_args
    on = {'percents': {'batch-pipeline': 100.0}, 'locked_by': None, 'legacy_sync': 'on'}
    refused = ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'draining']), on)
    assert refused == 'draining_precondition_unmet:' + ','.join(sorted(rc.DRAINING_PRECONDITIONS))
    partial = parse(['--env', 'prod', '--legacy-sync', 'draining', '--precondition-met', 'cap_hold_ladder_debit'])
    rest = sorted(set(rc.DRAINING_PRECONDITIONS) - {'cap_hold_ladder_debit'})
    assert ramp_set.plan_change(partial, on) == 'draining_precondition_unmet:' + ','.join(rest)
    assert ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'dark']), None).startswith(
        'draining_precondition'
    )
    ok = parse(
        ['--env', 'prod', '--legacy-sync', 'draining']
        + [arg for pid in sorted(rc.DRAINING_PRECONDITIONS) for arg in ('--precondition-met', pid)]
    )
    assert ramp_set.plan_change(ok, on)[0] == {'legacy_sync': 'draining'}
    # Returning to on, and draining -> dark, are never gated (rollback and progression after the gate passed).
    assert ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'on']), {**on, 'legacy_sync': 'dark'})[0]
    assert ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'dark']), {**on, 'legacy_sync': 'draining'})[0]


class _TimeoutRecordingClient:
    """Records the timeout of each `_ramp` point read; the document is absent."""

    def __init__(self):
        self.timeouts = []

    def collection(self, name):
        return self

    def document(self, doc_id):
        return self

    def get(self, *, timeout, retry):
        self.timeouts.append(timeout)
        return type('Absent', (), {'exists': False})()


def test_operator_tools_read_with_a_cold_client_budget(capsys):
    # A fresh client from an operator host needs >1s for its first read; the serving 1s budget made
    # `ramp_set --show` and the controller's first tick fail with DeadlineExceeded every time.
    client = _TimeoutRecordingClient()
    assert ramp_set.main(['--env', 'staging', '--show'], client_factory=lambda **kw: client) == 0
    assert json.loads(capsys.readouterr().out) == {'entry': None, 'env': 'staging', 'revision': 0}
    assert client.timeouts == [store.OPERATOR_READ_TIMEOUT_SECONDS]

    serving = _TimeoutRecordingClient()
    assert store.read_ramp(firestore_client=serving) is None
    assert serving.timeouts == [store.SERVING_READ_TIMEOUT_SECONDS] == [1.0]


def test_controller_reads_with_the_operator_budget(tmp_path, monkeypatch):
    client = _TimeoutRecordingClient()
    monkeypatch.setattr(rc, 'run_fleet_gate', lambda *a, **kw: pytest.fail('unseeded env must not run the gate'))
    argv = ['--env', 'staging', '--gate-cmd', 'true', '--no-anx', '--state-file', str(tmp_path / 'STATE.md')]
    rc.main(argv, client_factory=lambda **kw: client, runner=lambda argv, timeout: (0, ''))
    assert client.timeouts and set(client.timeouts) == {store.OPERATOR_READ_TIMEOUT_SECONDS}


# ---------------------------------------------------------------------------
# Lessons from the 5% record-lane ramps (lessons/batch-rollout-and-staging-traps.md #2-#5).
# ---------------------------------------------------------------------------

# Every `GATE_FAIL <token>` that fleet_gate.sh's verdict() can print (workspace infra/rollout/fleet_gate.sh,
# pinned at omi-workspace 3172987). The workspace's infra/rollout/test_controller_contract.py pins the same list
# against the gate source, so a new gate verdict fails there until it is classified here.
FLEET_GATE_VERDICT_FAIL_TOKENS = frozenset(
    {
        'pre_existing_debt_growing',
        'projection_error',
        'projection_transient_rate',
        'unrecovered_quarantine',
        'failed_held_duration_unknown',
        'terminal_unrecovered_speech_unit_over_120s',
        'failed_held_over_budget',
        'terminal_unrecovered_speech_over_0_2pct',
        'terminal_unrecovered_speech_unknown',
        'projection_stalled',
        'stuck_job_over_30m',
        'obligation_over_15m',
        'recovery_spend_over_0_005_per_worn_hour',
        'recovery_spend_unknown',
        'quarantine_projection_p95_unknown',
        'quarantine_projection_p95_over_5m',
        'first_summary_dispatch_contract',
        'first_summary_completion_outlier',
        'http_5xx_regression',
        'unsafe_parakeet_language_route',
        'language_route_unknown',
        'timeout_incomplete',
    }
)


def test_every_fleet_gate_verdict_token_acts():
    # A verdict missing from the closed lists would HOLD as "gate unavailable" and leave a failing cohort on.
    unclassified = {
        t for t in FLEET_GATE_VERDICT_FAIL_TOKENS - rc.INCOMPLETE_SAMPLE_TOKENS if rc.classify_fail(t)[0] is None
    }
    assert unclassified == set()
    # An unknown-size failed_held loss is data loss, like an over-budget one.
    assert rc.classify_fail('failed_held_duration_unknown')[0] is rc.Action.ROLLBACK_ZERO


def test_rollback_never_lowers_the_first_summary_floor():
    out = rc.decide_all(snap(25.0), verdict('FAIL', 'http_5xx_regression', percent=25.0), now=0.0)
    assert [(d.name, d.action, d.to_percent) for d in out] == [
        ('batch-pipeline', rc.Action.ROLLBACK_ONE, 10.0),
        ('first-summary', rc.Action.HOLD, 25.0),
    ]
    assert out[1].detail == 'quality_floor_kept' and not out[1].page


def test_first_summary_below_the_lead_pages_on_every_lead_action():
    s = snap(percents={'batch-pipeline': 25.0, 'first-summary': 5.0})
    for v in (verdict(percent=25.0, hold=2 * H), verdict('FAIL', 'http_5xx_regression', percent=25.0)):
        follower = rc.decide_all(s, v, now=0.0)[1]
        assert (follower.action, follower.detail, follower.page) == (rc.Action.HOLD, 'follower_diverged', True)


def test_first_summary_above_the_lead_holds_quietly():
    s = snap(percents={'batch-pipeline': 5.0, 'first-summary': 100.0})
    for v in (five(hold=H), verdict('FAIL', 'projection_error', percent=5.0)):
        lead, follower = rc.decide_all(s, v, now=0.0)
        assert lead.action is not rc.Action.HOLD
        assert (follower.action, follower.to_percent, follower.page) == (rc.Action.HOLD, 100.0, False)


def test_controller_never_writes_an_unseeded_or_floored_first_summary():
    # Seeded the M3 way (first-summary at prod's 100): the ladder and both rollback kinds leave it at 100.
    rig = Rig(script={25.0: ['GATE_FAIL http_5xx_regression'], 50.0: ['GATE_FAIL obligation_over_15m']})
    rig.lead({'percents': {'batch-pipeline': 5.0, 'first-summary': 100.0}}, 'seed')
    run_until(rig, 50.0)
    rig.tick()
    assert rig.percent() == 0.0
    assert rig.document()['envs'][rig.env]['percents']['first-summary'] == 100.0
    assert not any(text.startswith('PAGE') and 'follower' in text for text, _ in rig.notes)

    # Absent from `_ramp`, serving uses the env default; the controller must not write the lead's value.
    rig = Rig()
    rig.lead({'percents': {'batch-pipeline': 5.0}}, 'seed')
    run_until(rig, 10.0)
    assert 'first-summary' not in rig.document()['envs'][rig.env]['percents']


def test_ramp_set_refuses_lowering_a_quality_floor():
    parse = ramp_set.build_parser().parse_args
    seed = ['--env', 'prod', '--percent', 'batch-pipeline=5', '--percent', 'first-summary=5']
    assert ramp_set.plan_change(parse(seed), None) == 'quality_floor:first-summary'
    assert ramp_set.plan_change(parse(seed + ['--allow-quality-decrease']), None)[0] == {
        'percents': {'batch-pipeline': 5.0, 'first-summary': 5.0}
    }
    ok = ['--env', 'prod', '--percent', 'batch-pipeline=5', '--percent', 'first-summary=100']
    assert ramp_set.plan_change(parse(ok), None)[0]['percents']['first-summary'] == 100.0


def test_preflight_blocks_advance_but_never_rollback():
    rig = Rig(script={10.0: ['GATE_PASS', 'GATE_FAIL http_5xx_regression']})
    rig.lead({'percents': {'batch-pipeline': 10.0, 'first-summary': 100.0}}, 'seed')
    calls = []

    def preflight(percent):
        calls.append(percent)
        return False, 'live_env_recovery_all_admitted'

    effects = rig.effects()
    effects.preflight = preflight
    rig.now += 2 * H
    result = rc.tick(rig.env, effects)
    lead = result.decisions[0]
    assert not result.wrote and rig.percent() == 10.0 and calls == [10.0]
    assert (lead.action, lead.detail, lead.page) == (
        rc.Action.HOLD,
        'preflight:live_env_recovery_all_admitted',
        True,
    )
    rig.now += 600
    result = rc.tick(rig.env, effects)  # a FAIL rolls back without consulting the preflight
    assert result.wrote and rig.percent() == 5.0 and calls == [10.0]


def test_preflight_probe_reports_a_token_and_fails_closed():
    seen = []

    def runner(argv, timeout):
        seen.append(argv)
        return (1, 'checking\nPREFLIGHT_FAIL owner_backlog\n') if argv[-1] == '5' else (2, 'Traceback: x y z!')

    probe = rc.preflight_probe(['controller_preflight.sh'], runner)
    assert probe(5.0) == (False, 'owner_backlog')
    assert probe(10.0) == (False, 'preflight_failed')
    assert seen == [['controller_preflight.sh', '5'], ['controller_preflight.sh', '10']]
    assert rc.preflight_probe(['ok'], lambda argv, timeout: (0, ''))(25.0) == (True, 'ok')


class _FailingClient:
    def collection(self, name):
        raise RuntimeError('firestore unavailable')


def _loop_main(tmp_path, monkeypatch, stop, apply=True):
    notes = []

    def runner(argv, timeout):
        if argv[:2] == ['anx', 'note']:
            notes.append(argv[3])
        return 0, ''

    sleeps = {'n': 0}

    def fake_sleep(_seconds):
        sleeps['n'] += 1
        if sleeps['n'] == 4:
            stop()

    monkeypatch.setattr(rc, '_sleep', fake_sleep)
    monkeypatch.setenv('GCP_AGENT_TIER', 'dev-operator')
    argv = ['--env', 'staging', '--gate-cmd', 'true', '--loop', '--interval', '0']
    argv += ['--apply'] if apply else []
    argv += ['--state-file', str(tmp_path / 'STATE.md')]
    code = rc.main(argv, client_factory=lambda **kw: _FailingClient(), runner=runner)
    return code, notes


def test_loop_pages_after_three_failed_ticks_and_when_interrupted(tmp_path, monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    code, notes = _loop_main(tmp_path, monkeypatch, interrupt)
    assert code == 130
    assert [n for n in notes if 'tick failed 3 consecutive times (RuntimeError)' in n]
    assert notes[-1].startswith('PAGE lead: ramp-controller staging stopped (interrupted)')


def test_dry_run_loop_never_pages(tmp_path, monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    code, notes = _loop_main(tmp_path, monkeypatch, interrupt, apply=False)
    assert code == 130 and notes == []


def test_loop_pages_when_terminated_and_restores_the_handler(tmp_path, monkeypatch):
    import os
    import signal

    before = signal.getsignal(signal.SIGTERM)
    code, notes = _loop_main(tmp_path, monkeypatch, lambda: os.kill(os.getpid(), signal.SIGTERM))
    assert code == 128 + signal.SIGTERM
    assert 'stopped (signal_SIGTERM)' in notes[-1]
    assert signal.getsignal(signal.SIGTERM) is before
