"""What a database lock costs the live v3 builder's commit (database/conversations_v3_commit_cost.py).

The commit and its retries are the fresh-transaction retry of SCA-2918; the meter changes neither a result
nor an error. It times every commit and counts how it ended, the extra attempts and the documents they read
again. Which document held the lock, and every pass thrown away by its own guards, is the collision
record's to report (test_conversations_v3_pass_collisions.py).
"""

import logging
import re
from pathlib import Path

import pytest
import yaml
from google.api_core.exceptions import Aborted

from database import conversations_v3 as store, conversations_v3_commit_cost as commit_cost
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.conversations.v3 import Conflict


def exhausted():
    # What the fresh-transaction retry raises when every attempt was aborted.
    error = FirestoreContentionExhausted('Firestore transaction contention exhausted for commit')
    error.__cause__ = Aborted('Transaction lock timeout.')
    return error


def sdk_exhausted():
    # What the SDK itself raises when all of its in-chain tries were aborted at commit.
    error = ValueError('Failed to commit transaction in 5 attempts.')
    error.__cause__ = Aborted('Transaction lock timeout.')
    return error


def commit(runs=1, error=None):
    """A commit whose body ran ``runs`` times under its own retries, then returned or raised."""
    tries = [0]

    def operation():
        tries[0] = runs
        if error is not None:
            raise error
        return 'observed'

    return operation, (lambda: tries[0])


def count(outcome):
    return commit_cost.COMMITS.labels(outcome)._value.get()


def extra():
    return commit_cost.EXTRA_ATTEMPTS._value.get(), commit_cost.EXTRA_READS._value.get()


def timed(outcome):
    samples = commit_cost.SECONDS.labels(outcome)._child_samples()
    return next(sample.value for sample in samples if sample.name == '_count')


def every_count():
    return {outcome: count(outcome) for outcome in commit_cost.OUTCOMES}


def test_a_clean_commit_is_counted_once(caplog):
    operation, attempts = commit()
    before = count('first_try')
    # The meter starts no transaction of its own: the commit and its retries are the caller's.
    assert commit_cost.run(operation, attempts=attempts) == 'observed'
    assert count('first_try') == before + 1
    assert 'v3_commit_contention' not in caplog.text


def test_a_commit_that_had_to_retry_is_counted_with_its_cost(caplog):
    caplog.set_level(logging.INFO, logger=commit_cost.logger.name)
    operation, attempts = commit(runs=3)
    recovered, seconds, (tries, reads) = count('recovered'), timed('recovered'), extra()
    assert commit_cost.run(operation, reads_per_attempt=10, attempts=attempts) == 'observed'
    assert count('recovered') == recovered + 1
    assert timed('recovered') == seconds + 1
    assert extra() == (tries + 2, reads + 20)
    assert 'event=v3_commit_contention outcome=recovered attempts=3' in caplog.text
    assert 'extra_reads=20' in caplog.text
    # A handled case: info, like the collision record's line for each lost attempt.
    assert [record.levelno for record in caplog.records if 'v3_commit_contention' in record.message] == [logging.INFO]


@pytest.mark.parametrize('failure, kind', [(exhausted, FirestoreContentionExhausted), (sdk_exhausted, ValueError)])
def test_a_commit_that_gave_up_on_a_lock_fails_unchanged_and_is_counted(failure, kind, caplog):
    caplog.set_level(logging.INFO, logger=commit_cost.logger.name)
    error = failure()
    operation, attempts = commit(runs=3, error=error)
    before, (tries, reads) = count('exhausted'), extra()
    # The error leaves unchanged, so the task route still answers it as before.
    with pytest.raises(kind) as raised:
        commit_cost.run(operation, reads_per_attempt=10, attempts=attempts)
    assert raised.value is error
    assert count('exhausted') == before + 1
    assert extra() == (tries + 2, reads + 20)
    # The collision record writes the line for a commit that gave up (lock_failed); none is added here.
    assert 'v3_commit_contention' not in caplog.text


def test_another_failure_passes_through_unchanged_and_is_counted():
    error = RuntimeError('synthetic')
    operation, attempts = commit(error=error)
    before = count('error')
    with pytest.raises(RuntimeError) as raised:
        commit_cost.run(operation, attempts=attempts)
    assert raised.value is error
    assert count('error') == before + 1


def test_a_pass_thrown_away_by_its_own_guards_is_left_to_the_collision_record(caplog):
    caplog.set_level(logging.INFO, logger=commit_cost.logger.name)
    assert 'conflict' not in commit_cost.OUTCOMES
    error = Conflict('source_changed')
    # Two attempts lost to a lock, then the third found a changed document.
    operation, attempts = commit(runs=3, error=error)
    counts, (tries, reads) = every_count(), extra()
    with pytest.raises(Conflict) as raised:
        commit_cost.run(operation, reads_per_attempt=10, attempts=attempts)
    assert raised.value is error
    # No outcome and no line of its own; only what the lock retries before it cost.
    assert every_count() == counts
    assert extra() == (tries + 2, reads + 20)
    assert 'v3_commit_contention' not in caplog.text


def test_a_missing_or_broken_attempt_counter_never_fails_a_commit():
    operation, _ = commit()
    assert commit_cost.run(operation) == 'observed'
    assert commit_cost.run(operation, attempts=lambda: 1 / 0) == 'observed'


def test_only_the_live_builder_goes_through_the_meter():
    source_text = open(store.__file__).read()
    wrapped = source_text.index("if key == 'builder':")
    call = source_text.index('commit_cost.run(', wrapped)
    assert call < source_text.index('else:', wrapped)
    # One count of attempts for both records: the collision record's.
    assert 'attempts=lambda: watch.attempt' in source_text[call : source_text.index('else:', call)]


def test_the_counters_leave_backend_sync_where_the_builder_runs():
    config = yaml.safe_load((Path(__file__).resolve().parents[2] / 'deploy/cloud_run_gmp_sync.yaml').read_text())
    keep = next(rule for rule in config['spec']['endpoints'][0]['metricRelabeling'] if rule['action'] == 'keep')
    for name in (
        'omi_conversations_v3_builder_commit_total',
        'omi_conversations_v3_builder_commit_extra_attempts_total',
        'omi_conversations_v3_builder_commit_extra_reads_total',
    ):
        assert re.fullmatch(keep['regex'], name), name
    # The duration histogram stays local: its buckets would cost the scrape budget.
    assert not re.fullmatch(keep['regex'], 'omi_conversations_v3_builder_commit_seconds_bucket')
