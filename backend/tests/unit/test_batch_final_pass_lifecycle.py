"""Literal artifact lifecycle rows and read-only replays; no owner data or IO."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from database import batch_final_pass as references
from database.batch_final_pass_retry import MAX_ATTEMPTS, backoff
from tests.unit.fixtures.speaker_final_pass_retry import retry_state  # noqa: F401
from tests.unit.test_batch_final_pass import prod_shaped, UID, wav, batch_outcome_counts  # noqa: F401
from tests.unit.test_batch_final_pass_repro import multi_unit, replay  # noqa: F401
from tests.unit.test_batch_final_pass_retry import ready, next_wake  # noqa: F401
from testing.owner_lab import final_pass_repro as lab
from utils.batch_pipeline.artifact_reads import ArtifactReadLimit
from utils.conversations import final_pass_batch as batch, final_pass_retry as retry


def artifact_rows(case, unit='unit-a'):
    return [
        row
        for path, row in case.client.rows.items()
        if path[0] == case.store.namespace + '_artifacts' and row['segment_id'] == unit
    ]


@pytest.mark.parametrize('cleaned', [(), ('audio',), ('results',), ('audio', 'results')])
def test_exact_live_and_cleaned_artifact_row_shapes(multi_unit, cleaned):
    now = datetime.now(timezone.utc)
    for row in artifact_rows(multi_unit):
        # These are the two observed field sets, written literally rather than
        # by the registration/cleanup code whose schema we are testing.
        metadata = {
            'capture_at': 1000.0,
            'conversation_ids': ['conversation'],
            'duration_seconds': 8.0,
            'kind': row['kind'],
            'owner_id': UID,
            'owner_key': 'synthetic-owner-key',
            'privacy_generation': 0,
            'segment_id': 'unit-a',
        }
        if row['kind'] in cleaned:
            metadata['expires_at'] = now + timedelta(days=45)
        else:
            metadata.update(uri=row['uri'], cleanup_after=now + timedelta(hours=24))
        row.clear()
        row.update(metadata)
    result = replay(multi_unit)
    assert result['outcome'] == ('skipped_expired' if cleaned else 'success'), result
    if cleaned:
        assert result['message'] == 'artifact_cleaned'
        assert result['failing_unit'] == 'unit-a'
        assert result['read_bytes'] == result['changed_segments'] == 0


@pytest.mark.parametrize(
    'field,value,reason',
    [
        ('owner_id', 'another-owner', 'artifact_owner_mismatch'),
        ('segment_id', 'another-unit', 'artifact_unit_mismatch'),
        ('privacy_generation', 1, 'generation_mismatch'),
        ('erasure_requested', True, 'erasure'),
    ],
)
def test_cleaned_receipt_never_bypasses_owner_generation_or_erasure(multi_unit, field, value, reason):
    row = artifact_rows(multi_unit)[0]
    row.pop('uri')
    row.pop('cleanup_after')
    row['expires_at'] = datetime.now(timezone.utc) + timedelta(days=45)
    row[field] = value
    with pytest.raises(references.ReferenceUnavailable) as caught:
        references.load_reference(multi_unit.store, UID, 'unit-a', 'conversation')
    assert (caught.value.outcome, str(caught.value)) == ('failed_incomplete_coverage', reason)


def test_missing_uri_without_cleanup_ttl_is_still_a_binding_failure(multi_unit):
    artifact_rows(multi_unit)[0].pop('uri')
    result = replay(multi_unit)
    assert result['message'] == 'uri_mismatch'


def test_four_claims_add_at_most_675_seconds_of_scheduled_backoff(monkeypatch):
    monkeypatch.setattr('database.batch_final_pass_retry.random.uniform', lambda lo, hi: hi)
    assert MAX_ATTEMPTS == 4
    assert sum(backoff(attempt) for attempt in range(MAX_ATTEMPTS)) == 675


def test_late_retry_keeps_expiry_and_counts_one_terminal_outcome(ready, multi_unit):
    # Queue delivery is not bounded by jitter. A wake a day late must not
    # extend retention, replay enrichment, or count again on duplicate delivery.
    ready.raw.update(multi_unit.lane.conversation.model_dump())
    for row in artifact_rows(multi_unit):
        if row['kind'] == 'results':
            row['cleanup_after'] = datetime.now(timezone.utc) - timedelta(seconds=1)
    retry.enqueue(UID, multi_unit.lane.conversation)
    key, token = next_wake(ready.state)
    ready.state.clock[0] += 24 * 3600
    before = batch_outcome_counts()
    assert retry.consume(key, token)['outcome'] == 'skipped_expired'
    assert retry.consume(key, token)['outcome'] == 'stale'
    after = batch_outcome_counts()
    assert sum(after.values()) - sum(before.values()) == 1
    assert (
        sum(
            count - before.get(labels, 0)
            for labels, count in after.items()
            if dict(labels)['outcome'] == 'skipped_expired'
        )
        == 1
    )
    assert not ready.lane.gpu and not ready.writes


@pytest.mark.parametrize('shape', ['identical', 'conflicting', 'padded_hole'])
def test_overlapping_capture_clocks_require_identical_pcm(multi_unit, monkeypatch, shape):
    path = (multi_unit.store.namespace + '_jobs', 'unit-b')
    # Stored segment clocks need not equal capture clocks (merge rebasing).
    # These units overlap by four seconds on their authenticated audio clock.
    multi_unit.client.rows[path]['capture_at'] = 1004.0
    before = [s.model_copy(deep=True) for s in multi_unit.lane.conversation.transcript_segments]

    def fetch(item, *, read_budget):
        sample = b'\x02\0' if shape == 'conflicting' and item.segment_id == 'unit-b' else b'\x01\0'
        pcm = sample * round(item.duration_seconds * 16000)
        if shape == 'padded_hole' and item.segment_id == 'unit-a':
            # Materialized retained manifests can contain zeros outside actual
            # reference slices. PCM alone cannot authenticate that geometry.
            pcm = pcm[: 4 * 32000] + bytes(len(pcm) - 4 * 32000)
        return wav(pcm)

    monkeypatch.setattr(
        batch,
        'artifacts_for',
        lambda _: SimpleNamespace(
            load_result=lambda item, *a, **kw: multi_unit.payloads[item.segment_id], fetch_audio=fetch
        ),
    )
    result = replay(multi_unit)
    assert result['outcome'] == ('success' if shape == 'identical' else 'failed_incomplete_coverage'), result
    if shape != 'identical':
        assert result['message'] == 'conflicting capture clocks'
        assert multi_unit.lane.conversation.transcript_segments == before


@pytest.mark.parametrize('failure', [None, 'references', 'audio'])
def test_replay_reports_read_costs_on_success_and_each_deadline_phase(multi_unit, monkeypatch, failure):
    clock = [0.0]
    monkeypatch.setattr(lab.time, 'perf_counter', lambda: clock[0])
    original_reference = batch.load_reference

    def reference(*args, **kwargs):
        clock[0] += 2
        if failure == 'references':
            raise ArtifactReadLimit('artifact read deadline')
        return original_reference(*args, **kwargs)

    def result(item, uri, *, read_budget):
        clock[0] += 3
        read_budget.begin()
        read_budget.reserve(100)
        read_budget.received_bytes += 100
        return multi_unit.payloads[item.segment_id]

    def audio(item, *, read_budget):
        clock[0] += 5
        read_budget.begin()
        read_budget.reserve(1000)
        if failure == 'audio':
            raise ArtifactReadLimit('artifact read deadline')
        read_budget.received_bytes += 1000
        return wav(b'\x01\0' * round(item.duration_seconds * 16000))

    monkeypatch.setattr(batch, 'load_reference', reference)
    monkeypatch.setattr(batch, 'artifacts_for', lambda _: SimpleNamespace(load_result=result, fetch_audio=audio))
    if failure is None:
        diarize = batch.HttpDiarizer  # Lab substitutes the stub inside reproduce.
        # Spend application time outside the measured read phases.
        apply = lambda *a, **kw: clock.__setitem__(0, clock[0] + 100)
        outcome = lab.reproduce(UID, multi_unit.lane.conversation, {}, load_prints=lambda *a, **kw: {}, apply=apply)
        assert batch.HttpDiarizer is diarize
        # Two initial references, two decode/read phases, two revalidation reads.
        assert outcome['read_wall_seconds'] == 2 * 2 + 2 * (3 + 5) + 2 * 2
        assert (outcome['read_bytes'], outcome['read_reserved_bytes'], outcome['read_objects']) == (2200, 2200, 4)
    else:
        outcome = replay(multi_unit)
        expected = (2, 0, 0, 0) if failure == 'references' else (12, 100, 1100, 2)
        assert (
            tuple(outcome[k] for k in ('read_wall_seconds', 'read_bytes', 'read_reserved_bytes', 'read_objects'))
            == expected
        )
    assert outcome['outcome'] == ('success' if failure is None else 'deferred_transient'), outcome
    assert outcome['requeue_calls'] == (0 if failure is None else 1)
