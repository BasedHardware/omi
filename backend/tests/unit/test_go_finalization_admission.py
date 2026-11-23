"""SCA-3883 item 3: Go finalization admission is runtime config that fails closed."""

from pathlib import Path

import pytest

from config import rollout_cohorts as policy
from database import rollout_cohorts as store
from scripts.rollout import go_finalization_cohort as cli
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.rollout import go_finalization_admission as admission

UID = 'synthetic-owner-1'


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Reader:
    """Scripted switch reads; each call pops the next outcome (env dict, None, or Exception)."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        value = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(value, Exception):
            raise value
        return value


def env(percent):
    return {'percents': {} if percent is None else {'go-finalization': percent}}


@pytest.fixture
def member(monkeypatch):
    members = {UID}
    monkeypatch.setattr(policy, 'in_rollout_cohort', lambda uid, name: name == 'go-finalization' and uid in members)
    return members


def configure(*outcomes):
    clock = Clock()
    reader = Reader(*outcomes)
    admission.configure_switch_reader(reader, clock)
    return reader, clock


@pytest.mark.parametrize(
    'outcome',
    [None, env(None), env(99.9), env(0), env('100'), env(True), {'percents': 'x'}, RuntimeError('unavailable')],
)
def test_switch_fails_closed_unless_exactly_100(member, outcome):
    configure(outcome)
    assert admission.go_finalization_decision(UID) == ('python', 'closed')


def test_open_switch_admits_members_only(member):
    configure(env(100))
    assert admission.go_finalization_decision(UID) == ('go', 'admitted')
    assert admission.go_finalization_decision('synthetic-other') == ('python', 'not_member')


def test_membership_error_is_a_negative_grant(monkeypatch):
    configure(env(100.0))

    def boom(uid, name):
        raise policy.RolloutCohortUnavailable('unknown')

    monkeypatch.setattr(policy, 'in_rollout_cohort', boom)
    assert admission.go_finalization_decision(UID) == ('python', 'not_member')


def test_cached_value_bounds_how_long_open_survives_a_close(member):
    reader, clock = configure(env(100), env(0))
    assert admission.go_finalization_decision(UID)[0] == 'go'
    clock.now += admission.TTL_SECONDS - 1
    assert admission.go_finalization_decision(UID)[0] == 'go'  # within TTL: no second read
    assert reader.calls == 1
    clock.now += 1
    assert admission.go_finalization_decision(UID) == ('python', 'closed')
    assert reader.calls == 2


def test_read_error_closes_and_never_serves_last_known_good(member):
    reader, clock = configure(env(100), RuntimeError('down'), env(100))
    assert admission.go_finalization_decision(UID)[0] == 'go'
    clock.now += admission.TTL_SECONDS
    assert admission.go_finalization_decision(UID) == ('python', 'closed')
    # A failed read does not count as fresh: the next call retries instead of caching closed.
    assert admission.go_finalization_decision(UID)[0] == 'go'
    assert reader.calls == 3


def test_closed_and_non_member_paths_add_no_firestore_operations(monkeypatch):
    """The only Firestore access is the switch refresh; membership uses the shared cache."""
    reader, _clock = configure(env(None))
    seen = []
    monkeypatch.setattr(policy, 'in_rollout_cohort', lambda uid, name: seen.append(uid) or False)
    for _ in range(50):
        admission.go_finalization_decision(UID)
    assert reader.calls == 1 and seen == []  # closed never consults membership
    configure(env(100))
    for _ in range(50):
        assert admission.go_finalization_decision('synthetic-other') == ('python', 'not_member')


def test_admission_counter_is_labelled_by_engine_and_reason_only():
    before = admission.ADMISSIONS.labels('go', 'admitted')._value.get()
    admission.record_admission('go', 'admitted')
    assert admission.ADMISSIONS.labels('go', 'admitted')._value.get() == before + 1
    assert admission.ADMISSIONS._labelnames == ('engine', 'reason')


def test_cohort_has_no_env_fallback_and_ramp_name_is_known():
    assert policy.COHORT_ENVS['go-finalization']() == ''
    assert 'go-finalization' in store.RAMP_NAMES


def test_membership_write_is_atomic_with_its_audit_row():
    db = StrictFirestore()
    db.rows[('rollout_cohorts', UID)] = {'cohorts': {'prod': {'dream-agent': True}}}
    before, after = store.write_go_finalization_membership(
        UID,
        'prod',
        True,
        actor='release-lead',
        reason='release_go_test',
        at='2026-11-23T09:00:00+00:00',
        firestore_client=db,
    )
    assert (before, after) == (None, True)
    assert db.rows[('rollout_cohorts', UID)]['cohorts']['prod'] == {'dream-agent': True, 'go-finalization': True}
    entries = [
        row for path, row in db.rows.items() if path[:3] == ('rollout_cohorts', '_audit-go-finalization', 'entries')
    ]
    assert len(entries) == 1
    assert entries[0] | {} == {
        'cohort': 'go-finalization',
        'env': 'prod',
        'uid': UID,
        'before': None,
        'after': True,
        'actor': 'release-lead',
        'reason': 'release_go_test',
        'at': '2026-11-23T09:00:00+00:00',
    }
    store.write_go_finalization_membership(
        UID, 'prod', False, actor='release-lead', reason='close', at='2026-11-23T09:01:00+00:00', firestore_client=db
    )
    entries = [
        row for path, row in db.rows.items() if path[:3] == ('rollout_cohorts', '_audit-go-finalization', 'entries')
    ]
    assert sorted((str(row['before']), row['after']) for row in entries) == [('None', True), ('True', False)]


@pytest.mark.parametrize(
    'kwargs',
    [
        {'uid': '_ramp'},
        {'env': 'staging'},
        {'member': 1},
        {'actor': ''},
        {'reason': 'Has Spaces'},
    ],
)
def test_membership_write_refuses_invalid_input_and_writes_nothing(kwargs):
    db = StrictFirestore()
    args = {'uid': UID, 'env': 'prod', 'member': True, 'actor': 'lead', 'reason': 'ok'} | kwargs
    with pytest.raises(ValueError):
        store.write_go_finalization_membership(
            args['uid'],
            args['env'],
            args['member'],
            actor=args['actor'],
            reason=args['reason'],
            at='t',
            firestore_client=db,
        )
    assert db.rows == {}


def test_cli_reads_uid_from_file_and_never_prints_it(tmp_path, capsys):
    db = StrictFirestore()
    uid_file = tmp_path / 'uid'
    uid_file.write_text(UID + '\n')
    code = cli.main(
        ['--env', 'dev', '--uid-file', str(uid_file), '--add', '--actor', 'lead', '--reason', 'smoke'],
        client_factory=lambda: db,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert UID not in out and '"after": true' in out
    assert db.rows[('rollout_cohorts', UID)]['cohorts']['dev']['go-finalization'] is True


def test_switch_reads_stay_outside_transaction_callbacks():
    """The decision is made before the creating transaction; the module never opens one."""
    text = (Path(__file__).parents[2] / 'utils/rollout/go_finalization_admission.py').read_text()
    assert 'transactional' not in text and 'run_transactional' not in text
