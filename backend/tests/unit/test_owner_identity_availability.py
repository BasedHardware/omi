"""Durable current-revision denominators and bounded attempt outcomes."""

from copy import deepcopy
from pathlib import Path

import pytest

from database import owner_identity_availability as storage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.observability import owner_recognition as metrics, owner_recognition_diagnostics as diagnostics
from utils.conversations import speaker_resolution as stage
from utils.conversations.speaker_resolution_inputs import transcript_membership


@pytest.fixture
def durable(monkeypatch):
    client = StrictFirestore()
    path = ('users', 'synthetic-owner', 'conversations', 'synthetic-row')
    client.rows[path] = dict(
        status='completed',
        transcript_segments=[
            dict(id='one', text='Synthetic owner.', start=0, end=6, is_user=True, speaker_word_seconds=5),
            dict(id='two', text='Synthetic unknown.', start=6, end=10, is_user=False),
            dict(
                id='three',
                text='Synthetic person.',
                start=10,
                end=16,
                is_user=False,
                person_id='synthetic-person',
                speaker_word_seconds=4,
            ),
        ],
    )
    monkeypatch.setattr(storage, 'current_stage', lambda: 'test')
    monkeypatch.setattr(
        storage.conversations, 'decode_transcript_segments_verified', lambda uid, values, compressed: values
    )
    return client, path


def observe(client):
    return storage.observe('synthetic-owner', 'synthetic-row', client=client)


def counts(client):
    return {str(i): client.rows.get(('owner_identity_availability_test', str(i)), {}) for i in range(storage.SHARDS)}


def samples(collector):
    return {
        (sample.name, tuple(sample.labels.values())): sample.value
        for family in collector.collect()
        for sample in family.samples
    }


def test_duplicate_delivery_summary_reenrichment_and_restart_do_not_recount(durable):
    client, path = durable
    assert observe(client)
    before = deepcopy(counts(client))
    assert not observe(client)
    client.rows[path]['structured'] = {'title': 'Synthetic title changed'}
    assert not observe(client)
    # Dedupe is durable, independent of every process-local metric collector.
    restarted = metrics.IdentityAvailability()
    assert not list(restarted.collect())
    restarted.publish(counts(client), observed_at=100)
    assert not observe(client) and counts(client) == before
    values = samples(restarted)
    assert values['omi_owner_recognition_identity_segments_total', ('owner',)] == 1
    assert values['omi_owner_recognition_identity_segment_seconds_total', ('unknown',)] == 4
    assert values['omi_owner_recognition_identity_word_seconds_total', ('known_person',)] == 4
    assert values['omi_owner_recognition_identity_word_time_segments_total', ('unknown',)] == 0


def test_late_growth_and_repaired_identity_are_new_revision_observations(durable):
    client, path = durable
    assert observe(client)
    client.rows[path]['transcript_segments'].append(
        dict(id='four', text='Later speech.', start=16, end=22, is_user=False)
    )
    assert observe(client)
    client.rows[path]['transcript_segments'][1]['is_user'] = True
    assert observe(client)
    assert not observe(client)
    collector = metrics.IdentityAvailability()
    collector.publish(counts(client), observed_at=200)
    values = samples(collector)
    assert values['omi_owner_recognition_identity_segments_total', ('owner',)] == 4  # 1 + 1 + 2
    assert values['omi_owner_recognition_identity_segments_total', ('unknown',)] == 4  # 1 + 2 + 1


@pytest.mark.parametrize('fence', ['deleted', 'discarded', 'is_locked', 'sync_merged_into', 'account_deleting'])
def test_erasure_and_retired_rows_emit_nothing(durable, fence):
    client, path = durable
    if fence == 'account_deleting':
        client.rows[('account_deletions', 'synthetic-owner')] = dict(wipe_status='pending')
    else:
        client.rows[path][fence] = True
    assert not observe(client)
    assert not any(counts(client).values()) and storage.FIELD not in client.rows[path]


def test_incomplete_refresh_is_unavailable_and_stale_refresh_cannot_lower_counters(durable):
    client, path = durable
    assert observe(client)
    collector = metrics.IdentityAvailability()
    with pytest.raises(ValueError):
        collector.publish({'0': {}}, observed_at=1)
    assert not list(collector.collect())
    collector.publish(counts(client), observed_at=100)
    before = samples(collector)
    collector.publish({str(i): {} for i in range(storage.SHARDS)}, observed_at=90)
    assert samples(collector) == before


def test_processing_membership_fence_rejects_late_append_and_rebased_merge(monkeypatch):
    from database import conversations

    segments = [dict(id='one', text='Synthetic speech.', start=0, end=6)]
    incoming = dict(speaker_resolution={'input_membership_sha256': transcript_membership(segments)})
    monkeypatch.setattr(conversations, '_decode_transcript_segments_strict', lambda uid, raw, compressed, **kw: raw)
    assert conversations._batch_identity_membership_current('synthetic', incoming, dict(transcript_segments=segments))
    assert not conversations._batch_identity_membership_current(
        'synthetic',
        incoming,
        dict(transcript_segments=[*segments, dict(id='two', text='Late speech.', start=6, end=10)]),
    )
    assert not conversations._batch_identity_membership_current(
        'synthetic', incoming, dict(transcript_segments=[{**segments[0], 'start': 8, 'end': 14}])
    )


def test_labels_are_closed_and_all_exporters_keep_the_denominators():
    for value in ('synthetic-user-id', 'gs://synthetic/private', 'PRIVATE words'):
        before = list(diagnostics.PROOF_REFUSALS.collect())[0].samples
        diagnostics.resolver_reason(value)
        diagnostics.final_pass_availability(value)
        assert list(diagnostics.PROOF_REFUSALS.collect())[0].samples == before
    root = Path(__file__).resolve().parents[2]
    exporters = list(
        (root / 'charts/monitoring/prometheus-stackdriver-exporter').glob('*omi_cloud_run_metrics_exporter.yaml')
    )
    assert len(exporters) == 4
    for exporter in exporters:
        text = exporter.read_text()
        for measure in metrics.AVAILABILITY_MEASURES:
            assert f'omi_owner_recognition_identity_{measure}_total/' in text
        assert 'omi_owner_recognition_identity_observed_at_seconds/' in text
        assert 'omi_owner_recognition_proof_refusals_total/' in text
        assert 'omi_owner_recognition_final_pass_availability_total/' in text


def test_explicit_final_pass_disabled_and_dependency_unavailable(original_lane, monkeypatch):
    # The admission call must expose integration's disabled outcome without
    # enabling a dependency, taking a slot or changing its return contract.
    from utils.conversations import final_pass_batch as batch

    lane = original_lane
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'false')
    counter = diagnostics.FINAL_PASS_AVAILABILITY.labels(outcome='disabled')
    before = counter._value.get()
    result = batch.run_batch_final_pass(
        'synthetic', lane.conversation, {}, load_prints=lambda *a: {}, apply=lambda *a, **kw: None, requeue=None
    )
    assert result['outcome'] == 'skipped_ineligible' and counter._value.get() == before + 1
    monkeypatch.setenv('BATCH_FINAL_PASS_ENABLED', 'true')

    def unavailable(*a, **kw):
        raise RuntimeError('diarizer_unconfigured')

    monkeypatch.setattr(batch, '_run', unavailable)
    counter = diagnostics.FINAL_PASS_AVAILABILITY.labels(outcome='dependency_unavailable')
    before = counter._value.get()
    result = batch.run_batch_final_pass(
        'synthetic', lane.conversation, {}, load_prints=lambda *a: {}, apply=lambda *a, **kw: None, requeue=None
    )
    assert result['outcome'] == 'failed_batch_audio' and counter._value.get() == before + 1


@pytest.fixture
def original_lane(lane):
    return lane


from tests.unit.test_batch_final_pass import lane


def test_returned_final_pass_dependency_failure_is_observed(original_lane, monkeypatch):
    from utils.conversations import final_pass_batch as batch

    lane = original_lane
    monkeypatch.setattr(batch, 'recurring_enabled_for', lambda *a: False)
    monkeypatch.setattr(
        batch,
        'run_final_pass',
        lambda *a, **kw: (
            None,
            {
                'outcome': 'failed:service',
                'reason': 'diarizer_unconfigured',
            },
        ),
    )
    counter = diagnostics.FINAL_PASS_AVAILABILITY.labels(outcome='dependency_unavailable')
    before = counter._value.get()
    result = batch.run_batch_final_pass(
        'synthetic', lane.conversation, {}, load_prints=lambda *a, **kw: {}, apply=lambda *a, **kw: None, requeue=None
    )
    assert result['outcome'] == 'failed_batch_audio'
    assert counter._value.get() == before + 1
