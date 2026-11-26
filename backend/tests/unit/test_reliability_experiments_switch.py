"""The reliability experiments switch: per account from the Omi flag store, or a local override list.

``config.reliability_experiments.enabled(name, uid)`` is what every experiment call site asks.
``utils.reliability_flags`` is the store read bound behind it: direct on a thread, and from what was
last learned on an event loop, which never reads the store inline.
"""

import asyncio
import re
import threading
from pathlib import Path

import pytest

from config import reliability_experiments as experiments
from utils import omi_flags, reliability_flags, rollout_cohorts

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv(experiments.ENV, raising=False)
    monkeypatch.setattr(experiments, '_resolver', None)
    monkeypatch.setattr(experiments, '_warmer', None)
    reliability_flags.reset()
    yield
    reliability_flags.reset()


def rules(monkeypatch, admitted):
    """A flag store whose rule ``key`` admits the uids in ``admitted[key]``; counts its reads."""
    reads = []

    def resolve(key, uid):
        reads.append((key, uid, threading.current_thread().name))
        if key not in admitted:
            return None
        return omi_flags.Resolved(uid in admitted[key])

    monkeypatch.setattr(omi_flags, 'resolve', resolve)
    return reads


def test_every_name_is_its_own_flag_key_and_is_registered_as_a_rollout():
    keys = {value for name, value in vars(experiments).items() if name.endswith('_FLAG_KEY')}
    assert keys == set(experiments.EXPERIMENTS)
    registry = (ROOT / 'config/feature-flags.yaml').read_text()
    for key in keys:
        row = next((line for line in registry.splitlines() if re.search(rf'"key":\s*"{key}"', line)), None)
        assert row is not None, key
        assert '"kind":"posthog"' in row.replace(' ', '') and '"lifecycle":"rollout"' in row.replace(' ', ''), key
        assert '"backend"' in row, key


def test_off_without_a_resolver_an_account_or_a_rule(monkeypatch):
    assert experiments.enabled('commit_wake', 'u') is False
    experiments.configure_resolver(lambda name, uid: True)
    assert experiments.enabled('commit_wake', None) is False
    assert experiments.enabled('commit_wake', '') is False
    assert experiments.enabled('commit_wake', 'u') is True
    with pytest.raises(KeyError):
        experiments.enabled('no_such_experiment', 'u')


def test_a_rule_admits_its_accounts_only(monkeypatch):
    experiments.configure_resolver(lambda name, uid: name == 'fast_end_feedback' and uid == 'in')
    assert experiments.enabled('fast_end_feedback', 'in') is True
    assert experiments.enabled('fast_end_feedback', 'out') is False
    assert experiments.enabled('end_open_conversation', 'in') is False
    assert experiments.any_enabled('in', 'end_open_conversation', 'fast_end_feedback') is True
    assert experiments.any_enabled('out', 'end_open_conversation', 'fast_end_feedback') is False


def test_a_failing_or_odd_resolver_reads_as_off():
    experiments.configure_resolver(lambda name, uid: 1 / 0)
    assert experiments.enabled('commit_wake', 'u') is False
    experiments.configure_resolver(lambda name, uid: 'yes')
    assert experiments.enabled('commit_wake', 'u') is False


def test_the_local_override_turns_a_name_on_for_every_account(monkeypatch):
    experiments.configure_resolver(lambda name, uid: pytest.fail('the override answers first'))
    monkeypatch.setenv(experiments.ENV, 'commit_wake, receipt_long_poll')
    assert experiments.enabled('commit_wake') is True
    assert experiments.enabled('receipt_long_poll', 'anyone') is True
    monkeypatch.setenv(experiments.ENV, 'all')
    assert all(experiments.enabled(name) for name in experiments.EXPERIMENTS)
    monkeypatch.setenv(experiments.ENV, 'comit_wake')
    assert experiments.unknown() == {'comit_wake'}


def test_no_deployed_environment_sets_the_local_override():
    for path in (ROOT / 'backend/deploy').rglob('*.yaml'):
        assert experiments.ENV not in path.read_text(), path
    for path in (ROOT / 'backend/charts').rglob('*.yaml'):
        assert experiments.ENV not in path.read_text(), path


def test_the_rollout_runtime_binds_the_flag_store_read(monkeypatch):
    rollout_cohorts.configure_rollout_runtime()
    assert experiments._resolver is reliability_flags.admits
    assert experiments._warmer is reliability_flags.warm
    # No store configured in a test process: every rule reads as absent, so everything is off.
    assert experiments.enabled('commit_wake', 'u') is False


def test_a_thread_reads_the_store_directly(monkeypatch):
    reads = rules(monkeypatch, {'commit_wake': {'in'}})
    assert reliability_flags.admits('commit_wake', 'in') is True
    assert reliability_flags.admits('commit_wake', 'out') is False
    assert reliability_flags.admits('fast_end_feedback', 'in') is False  # no rule
    assert [(key, uid) for key, uid, _ in reads] == [
        ('commit_wake', 'in'),
        ('commit_wake', 'out'),
        ('fast_end_feedback', 'in'),
    ]


def test_a_store_fault_reads_as_off(monkeypatch):
    monkeypatch.setattr(omi_flags, 'resolve', lambda key, uid: 1 / 0)
    assert reliability_flags.admits('commit_wake', 'in') is False


@pytest.mark.asyncio
async def test_an_event_loop_never_reads_the_store_inline(monkeypatch):
    reads = rules(monkeypatch, {'commit_wake': {'in'}})
    loop_thread = threading.current_thread().name
    # First check for the account in this process: off, and a worker thread goes to learn it.
    assert reliability_flags.admits('commit_wake', 'in') is False
    for _ in range(200):
        if reliability_flags.admits('commit_wake', 'in'):
            break
        await asyncio.sleep(0.01)
    assert reliability_flags.admits('commit_wake', 'in') is True
    assert reads and all(thread != loop_thread for _, _, thread in reads)
    # One task learned every rule of the account, whichever key was asked for.
    assert {key for key, uid, _ in reads if uid == 'in'} == set(experiments.EXPERIMENTS)


@pytest.mark.asyncio
async def test_warm_learns_the_account_before_the_first_check(monkeypatch):
    reads = rules(monkeypatch, {'fast_end_feedback': {'in'}})
    loop_thread = threading.current_thread().name
    await reliability_flags.warm('in')
    assert reliability_flags.admits('fast_end_feedback', 'in') is True
    assert all(thread != loop_thread for _, _, thread in reads)
    count = len(reads)
    await reliability_flags.warm('in')  # Learned a moment ago: no second read.
    assert len(reads) == count


@pytest.mark.asyncio
async def test_a_stale_answer_is_served_while_it_is_learned_again(monkeypatch):
    admitted = {'commit_wake': {'in'}}
    rules(monkeypatch, admitted)
    clock = [1000.0]
    monkeypatch.setattr(reliability_flags, '_now', lambda: clock[0])
    await reliability_flags.warm('in')
    assert reliability_flags.admits('commit_wake', 'in') is True
    admitted['commit_wake'] = set()  # The rule changes.
    clock[0] += reliability_flags.REFRESH_SECONDS + 1
    assert reliability_flags.admits('commit_wake', 'in') is True  # Served as held, refreshed behind.
    for _ in range(200):
        if not reliability_flags.admits('commit_wake', 'in'):
            break
        await asyncio.sleep(0.01)
    assert reliability_flags.admits('commit_wake', 'in') is False


@pytest.mark.asyncio
async def test_the_switch_warm_is_a_no_op_without_a_warmer_or_an_account():
    await experiments.warm('u')
    await experiments.warm(None)
    seen = []

    async def warmer(uid):
        seen.append(uid)
        raise RuntimeError('pool closed')

    experiments.configure_resolver(lambda name, uid: False, warmer)
    await experiments.warm('u')  # A failed warm never fails the caller.
    assert seen == ['u']


def test_held_answers_are_bounded(monkeypatch):
    rules(monkeypatch, {})
    monkeypatch.setattr(reliability_flags, 'MAX_ANSWERS', 4)
    for index in range(10):
        reliability_flags.admits('commit_wake', f'u{index}')
    assert len(reliability_flags._answers) == 4
