"""Proof that optional enforced-hit audits stay bounded and outside the decision."""

from concurrent.futures import Future
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import ServiceUnavailable
import pytest

from database import batch_privacy_tokenless_audit as audit
from database import batch_pipeline_projection as projection
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_privacy_tokenless import EnforcedHit
from database.firestore_read_origin import current_read_origin
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.executors import ExecutorSaturatedError

HIT = EnforcedHit(frozenset({'source'}), 7, 1_000, 1_300)
OWNER = 'example'
NOW = 1_100


def count(counter, outcome):
    return counter.labels(audit.ROUTE, outcome)._value.get()


@pytest.mark.parametrize(
    ('allowed', 'revision', 'stamp', 'outcome'),
    [
        (True, 950, NOW, 'agree'),
        (False, 1_050, NOW, 'disagree_within_window'),
        (False, 950, NOW, 'disagree_beyond_window'),
        (False, None, NOW, 'failed'),
        (False, 1_101, NOW, 'failed'),
        (True, 950, 1_080, 'failed'),
        (True, 950, 1_301, 'failed'),
    ],
)
def test_audit_evaluates_only_comparable_live_walks(monkeypatch, allowed, revision, stamp, outcome):
    monkeypatch.setattr(audit.time, 'time', lambda: NOW)
    snapshot = SimpleNamespace(
        read_time=datetime.fromtimestamp(stamp, timezone.utc),
        update_time=datetime.fromtimestamp(revision, timezone.utc) if revision is not None else None,
    )
    transaction = object()
    store = SimpleNamespace(client=Mock())
    monkeypatch.setattr(audit.metrics, 'read_snapshot', Mock(return_value=snapshot))

    def read(target, read_body, budget):
        assert target is store and current_read_origin() == 'job:projection_tokenless_audit'
        return read_body(SimpleNamespace(client=store.client, transaction=transaction))

    walk = Mock()
    if not allowed:
        walk.side_effect = BatchPrivacyBlocked('account_deleted')
    monkeypatch.setattr(audit, 'read_snapshot', read)
    monkeypatch.setattr(audit, '_assert_batch_write_allowed_live', walk)
    outcomes = ('agree', 'disagree_within_window', 'disagree_beyond_window')
    before = [count(audit.AUDIT, label) for label in outcomes]
    incomplete = count(audit.INCOMPLETE, 'failed')
    audit._audit(store, OWNER, HIT, ArtifactReadBudget(audit.time.monotonic() + 2, 0, 0))
    assert [count(audit.AUDIT, label) for label in outcomes] == [
        value + (label == outcome) for value, label in zip(before, outcomes)
    ]
    assert count(audit.INCOMPLETE, 'failed') == incomplete + (outcome == 'failed')
    assert walk.call_args.args == (store.client, transaction, OWNER)
    assert walk.call_args.kwargs['conversation_ids'] == HIT.ids
    assert walk.call_args.kwargs['expected_generation'] == HIT.generation


def test_audit_submission_is_capped_nonblocking_and_records_dropped(monkeypatch):
    monkeypatch.setattr(audit.time, 'time', lambda: NOW)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_tokenless_owner_audit":100}')
    future = Future()
    submit = Mock(return_value=future)
    monkeypatch.setattr(audit.read_cache_shadow_executor, 'submit', submit)
    monkeypatch.setattr(audit.random, 'randrange', lambda _: 100)
    audit.submit_projection_precheck_audit(object(), OWNER, HIT)
    submit.assert_not_called()

    monkeypatch.setattr(audit.random, 'randrange', lambda _: 99)
    dropped = count(audit.INCOMPLETE, 'dropped')
    agreements = count(audit.AUDIT, 'agree')
    audit.submit_projection_precheck_audit(object(), OWNER, HIT)
    submit.assert_called_once()
    assert not future.done()  # No result/join on the submission path.
    assert future.cancel()
    submit.side_effect = ExecutorSaturatedError()
    audit.submit_projection_precheck_audit(object(), OWNER, HIT)
    assert count(audit.INCOMPLETE, 'dropped') == dropped + 2
    assert count(audit.AUDIT, 'agree') == agreements

    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    audit.submit_projection_precheck_audit(object(), OWNER, HIT)
    assert submit.call_count == 2


def test_rpc_failure_and_point_read_limit_are_not_agreements(monkeypatch):
    monkeypatch.setattr(audit, 'read_snapshot', Mock(side_effect=ServiceUnavailable('synthetic Firestore error')))
    failures = count(audit.INCOMPLETE, 'failed')
    agreements = count(audit.AUDIT, 'agree')
    deadline = audit.time.monotonic() + 2
    audit._audit(object(), OWNER, HIT, ArtifactReadBudget(deadline, 0, 0))
    assert count(audit.INCOMPLETE, 'failed') == failures + 1
    assert count(audit.AUDIT, 'agree') == agreements

    budget = audit._PointReadBudget(ArtifactReadBudget(deadline, 0, 0))
    for _ in range(audit.MAX_POINT_READS):
        assert budget.timeout(10) <= 2
    with pytest.raises(ArtifactReadLimit, match='audit read limit'):
        budget.timeout(10)


def test_projection_only_submits_after_the_successful_attempt(monkeypatch):
    submit = Mock()
    monkeypatch.setattr(projection, 'submit_projection_precheck_audit', submit)
    session = SimpleNamespace(policy=None, binding=SimpleNamespace(owner_id=OWNER), tokenless_precheck_hits=[])

    def prepare(transaction, *, speculative):
        assert speculative
        session.tokenless_precheck_hits[:] = [HIT] if transaction == 'hit' else []

    session.prepare = prepare
    store = projection.ProjectionStore(SimpleNamespace(client=None))

    def run(operation, *, policy):
        assert operation.to_wrap('hit') is HIT
        submit.assert_not_called()
        return operation.to_wrap('miss')

    monkeypatch.setattr(store, 'run', run)
    store.check(session, speculative=True)
    submit.assert_not_called()

    def success(operation, *, policy):
        result = operation.to_wrap('hit')
        submit.assert_not_called()
        return result

    monkeypatch.setattr(store, 'run', success)
    store.check(session, speculative=True)
    submit.assert_called_once_with(store.store, OWNER, HIT)
