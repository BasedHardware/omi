"""Contract (g): ramp-controller decisions, authority limits, and a hermetic full-ladder rehearsal."""

import json
import math

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


def test_five_percent_holds_three_hours():
    assert decide(snap(5.0), verdict(percent=5.0, hold=3 * H - 1)).action is rc.Action.HOLD
    assert decide(snap(5.0), verdict(percent=5.0, hold=3 * H)).to_percent == 10.0


@pytest.mark.parametrize('status', ['PENDING', 'NO_WORK'])
def test_pending_and_no_work_hold(status):
    d = decide(snap(), verdict(status))
    assert d.action is rc.Action.HOLD and d.reason is rc.RampReason.GATE_PENDING


def test_never_past_one_hundred():
    d = decide(snap(100.0), verdict(percent=100.0))
    assert d.action is rc.Action.HOLD and d.reason is rc.RampReason.AT_CEILING


def test_off_ladder_value_moves_to_next_step_without_skipping():
    assert decide(snap(7.0), verdict(percent=7.0, hold=4 * H)).to_percent == 10.0
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
        'parity_fail',
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
    ],
)
def test_gate_execution_failures_hold(reason):
    d = decide(snap(25.0), verdict('FAIL', reason, percent=25.0))
    assert d.action is rc.Action.HOLD


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
    assert decide(snap(), verdict(), seconds_since_last_controller_write=599).action is rc.Action.HOLD
    assert (
        decide(snap(), verdict('FAIL', 'projection_error'), seconds_since_last_controller_write=10).action
        is rc.Action.HOLD
    )
    assert decide(snap(10.0), verdict(percent=5.0)).action is rc.Action.HOLD


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
    full = base + ['--apply', '--train-lock-cmd', 'x', '--parity-cmd', 'y']
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
        return rc.GateVerdict(status, reason, self.now, self.now - since, percent, {})

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
    assert [d.action for d in result.decisions] == [rc.Action.ROLLBACK_ONE] * 2
    assert rig.percent() == 10.0
    run_until(rig, 50.0)
    result = rig.tick()  # injected data-loss FAIL at 50
    assert [d.action for d in result.decisions] == [rc.Action.ROLLBACK_ZERO] * 2
    assert rig.percent() == 0.0

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
    assert 'cap_hold_ladder_debit' in rc.DRAINING_PRECONDITIONS
    parse = ramp_set.build_parser().parse_args
    on = {'percents': {'batch-pipeline': 100.0}, 'locked_by': None, 'legacy_sync': 'on'}
    refused = ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'draining']), on)
    assert refused == 'draining_precondition_unmet:cap_hold_ladder_debit'
    assert ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'dark']), None).startswith(
        'draining_precondition'
    )
    ok = parse(['--env', 'prod', '--legacy-sync', 'draining', '--precondition-met', 'cap_hold_ladder_debit'])
    assert ramp_set.plan_change(ok, on)[0] == {'legacy_sync': 'draining'}
    # Returning to on, and draining -> dark, are never gated (rollback and progression after the gate passed).
    assert ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'on']), {**on, 'legacy_sync': 'dark'})[0]
    assert ramp_set.plan_change(parse(['--env', 'prod', '--legacy-sync', 'dark']), {**on, 'legacy_sync': 'draining'})[0]
