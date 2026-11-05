"""Production-shaped dependency faults enter only the capped speaker outbox."""

import errno

from google.api_core import exceptions as api
import httpx
import pytest
import requests

from database.batch_final_pass_retry import MAX_ATTEMPTS
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
from tests.unit.test_batch_final_pass import prod_shaped, UID, run_prod, batch_outcome_counts  # noqa: F401
from tests.unit.test_batch_final_pass_retry import ready, next_wake  # noqa: F401
from tests.unit.test_batch_final_pass_repro import multi_unit, replay  # noqa: F401
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit
from utils.conversations import final_pass_batch as batch, final_pass_pyannote as final, final_pass_retry as retry
from utils.conversations.final_pass_dependencies import transient_cause

TRANSIENTS = [
    api.ServiceUnavailable,
    api.DeadlineExceeded,
    api.Aborted,
    api.InternalServerError,
    api.TooManyRequests,
    api.ResourceExhausted,
    ConnectionResetError,
    requests.exceptions.ReadTimeout,
    httpx.ReadTimeout,
    requests.exceptions.ConnectionError,
    httpx.ReadError,
    TimeoutError,
    lambda _: ArtifactReadLimit('artifact read deadline'),
]


def inject(monkeypatch, lane, factory, phase):
    def fail(*args, **kwargs):
        raise factory('PRIVATE provider message, never log')

    if phase == 'reference':
        monkeypatch.setattr(batch, 'load_reference', fail)
    elif phase == 'result':
        monkeypatch.setattr(lane.artifacts, 'load_result', fail)
    elif phase == 'audio':
        monkeypatch.setattr(lane.artifacts, 'fetch_audio', fail)
    elif phase == 'diarizer':
        monkeypatch.setattr(final, 'diarize_with_speech_compaction', fail)
    elif phase == 'revalidation':
        reference = batch.load_reference
        calls = []

        def revalidate(*args, **kwargs):
            calls.append(True)
            if len(calls) > len(lane.items):
                fail()
            return reference(*args, **kwargs)

        monkeypatch.setattr(batch, 'load_reference', revalidate)


@pytest.mark.parametrize('factory', TRANSIENTS)
@pytest.mark.parametrize('phase', ['reference', 'result', 'audio', 'revalidation', 'diarizer'])
def test_initial_fault_defers_with_durable_custody_without_terminal_count(ready, monkeypatch, caplog, factory, phase):
    original = ready.lane.conversation.model_dump()
    inject(monkeypatch, ready.lane, factory, phase)
    before = batch_outcome_counts()
    result = run_prod(ready.lane)
    assert result['outcome'] == 'deferred_transient', result
    assert len(ready.state.rows) == len(ready.state.wakes) == 1
    assert next(iter(ready.state.rows.values()))['attempts'] == 0
    assert ready.lane.conversation.model_dump() == original
    assert batch_outcome_counts() == before
    assert result['exception_type'] and result['location'] != 'unavailable'
    assert 'PRIVATE' not in repr(result) + caplog.text


@pytest.mark.parametrize('factory', TRANSIENTS)
def test_each_dependency_class_exhausts_four_retry_claims_once(ready, monkeypatch, factory):
    inject(monkeypatch, ready.lane, factory, 'audio')
    before = batch_outcome_counts()
    assert run_prod(ready.lane)['outcome'] == 'deferred_transient'
    for attempt in range(1, MAX_ATTEMPTS + 1):
        key, token = next_wake(ready.state)
        result = retry.consume(key, token)
        assert result['outcome'] == ('skipped_retry_exhausted' if attempt == MAX_ATTEMPTS else 'deferred_transient')
        assert ready.state.rows[key]['attempts'] == attempt
        assert retry.consume(key, token)['outcome'] == 'stale'
    assert not ready.writes
    after = batch_outcome_counts()
    assert sum(after.values()) - sum(before.values()) == 1
    assert (
        sum(
            value - before.get(labels, 0)
            for labels, value in after.items()
            if dict(labels)['outcome'] == 'skipped_retry_exhausted'
        )
        == 1
    )


@pytest.mark.parametrize('factory', TRANSIENTS)
def test_retry_reload_failures_use_same_classification(ready, monkeypatch, factory):
    from database import conversations

    def fail(*args, **kwargs):
        raise factory('PRIVATE')

    monkeypatch.setattr(conversations, 'get_conversation', fail)
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    before = batch_outcome_counts()
    assert retry.consume(key, token)['outcome'] == 'deferred_transient'
    assert batch_outcome_counts() == before


@pytest.mark.parametrize('reason', ['artifact object limit', 'artifact byte limit'])
def test_structural_read_caps_are_terminal_in_initial_and_retry(ready, monkeypatch, reason):
    inject(monkeypatch, ready.lane, lambda _: ArtifactReadLimit(reason), 'audio')
    before = batch_outcome_counts()
    assert run_prod(ready.lane)['outcome'] == 'failed_read_budget'
    assert not ready.state.rows
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'failed_read_budget'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 2


@pytest.mark.parametrize('factory', [api.PermissionDenied, api.NotFound, api.InvalidArgument, ValueError])
def test_permanent_reload_errors_close_without_retry(ready, monkeypatch, factory):
    from database import conversations

    def fail(*args, **kwargs):
        raise factory('PRIVATE')

    monkeypatch.setattr(conversations, 'get_conversation', fail)
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    before = batch_outcome_counts()
    assert retry.consume(key, token)['outcome'] == 'failed_dependency'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 1


def test_wrapped_errors_preserve_transience_and_structural_caps_win():
    cause = api.Aborted('PRIVATE')
    wrapper = ValueError('unit unavailable')
    wrapper.__cause__ = cause
    assert transient_cause(wrapper) is cause
    cap = ArtifactReadLimit('artifact byte limit')
    cap.__cause__ = cause
    assert transient_cause(cap) is None
    assert transient_cause(OSError(errno.ECONNRESET, 'PRIVATE')) is not None
    assert transient_cause(requests.exceptions.SSLError('PRIVATE')) is None
    wrapper.__cause__ = wrapper
    assert transient_cause(wrapper) is None


def test_replay_captures_transient_deferral_without_outbox_writes(multi_unit, monkeypatch):
    def fail(*args, **kwargs):
        raise api.ServiceUnavailable('PRIVATE')

    monkeypatch.setattr(batch, 'load_reference', fail)
    result = replay(multi_unit)
    assert result['outcome'] == 'deferred_transient'
    assert result['requeue_calls'] == 1
    assert multi_unit.client.rows == multi_unit.before


def test_transient_recovers_on_speaker_only_retry(ready, monkeypatch):
    fetch = ready.lane.artifacts.fetch_audio
    inject(monkeypatch, ready.lane, api.Aborted, 'audio')
    assert run_prod(ready.lane)['outcome'] == 'deferred_transient'
    monkeypatch.setattr(ready.lane.artifacts, 'fetch_audio', fetch)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'success'
    assert len(ready.writes) == 1
    assert retry.consume(key, token)['outcome'] == 'stale'


def test_unit_cap_remains_terminal_in_initial_and_retry(ready, monkeypatch):
    conversation = ready.lane.conversation
    template = conversation.transcript_segments[0]
    conversation.transcript_segments = [
        template.model_copy(update={'id': str(i), 'speaker_id_scope': f'final:batch:unit-{i}'})
        for i in range(batch.MAX_UNITS + 1)
    ]
    ready.raw.update(conversation.model_dump())
    ready.raw['status'] = 'completed'
    monkeypatch.setattr(batch, 'load_reference', lambda *a, **kw: pytest.fail('unit cap performed IO'))
    before = batch_outcome_counts()
    assert run_prod(ready.lane)['outcome'] == 'failed_too_long'
    assert not ready.state.rows
    retry.enqueue(UID, conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'failed_too_long'
    assert retry.consume(key, token)['outcome'] == 'stale'
    assert sum(batch_outcome_counts().values()) - sum(before.values()) == 2


@pytest.mark.parametrize('factory', [api.PermissionDenied, api.NotFound, api.InvalidArgument, ValueError])
def test_permanent_artifact_errors_are_not_deferred(ready, monkeypatch, factory):
    inject(monkeypatch, ready.lane, factory, 'audio')
    assert run_prod(ready.lane)['outcome'] == 'failed_incomplete_coverage'
    assert not ready.state.rows
    retry.enqueue(UID, ready.lane.conversation)
    key, token = next_wake(ready.state)
    assert retry.consume(key, token)['outcome'] == 'failed_incomplete_coverage'
    assert retry.consume(key, token)['outcome'] == 'stale'
