"""Fast per-recording admission proof checks, without product/client imports."""

from copy import deepcopy
from dataclasses import replace
import hashlib

import pytest

from testing.replay_harness.stages.evidence import Recording, EvidenceMismatch, validate_recording


def receipts(record):
    uri = (
        f'gs://replay-staged/batch-pipeline/batch_pipeline_test_replayharness/owners/'
        f'{hashlib.sha256(record.owner_id.encode()).hexdigest()}/audio/{record.segment_id}/synthetic.enc#1'
    )
    binding = dict(
        owner_id=record.owner_id,
        content_id=record.content_id,
        job_id=record.job_id,
        target_conversation_id=record.conversation_id,
        segment_ids=[record.segment_id],
        privacy_generation=0,
        record_origin=True,
        native_record=True,
    )
    job = dict(
        state='ready',
        owner_id=record.owner_id,
        segment_id=record.segment_id,
        conversation_id=record.conversation_id,
        privacy_generation=0,
        capture_at=record.capture_at,
        duration_seconds=record.duration_seconds,
        audio_uri=uri,
        projection_binding=binding,
    )
    intake = dict(
        owner_id=record.owner_id,
        owner_key=record.owner_key,
        content_id=record.content_id,
        conversation_id=record.conversation_id,
        segment_ids=[record.segment_id],
        total_audio_seconds=record.duration_seconds,
    )
    artifact = dict(
        owner_id=record.owner_id,
        owner_key=record.owner_key,
        segment_id=record.segment_id,
        kind='audio',
        privacy_generation=0,
        uri=uri.split('#')[0],
        capture_at=record.capture_at,
        duration_seconds=record.duration_seconds,
        conversation_ids=[record.conversation_id],
    )
    manifest = dict(
        owner_id=record.owner_id,
        conversation_id=record.conversation_id,
        capture_at=record.capture_at,
        context=dict(
            owner_id=record.owner_id,
            conversation_id=record.conversation_id,
            job_id=record.job_id,
            content_id=record.content_id,
            segment_id=record.segment_id,
            capture_at=record.capture_at,
        ),
        references=[{'path': f'chunks/{record.owner_id}/{record.conversation_id}/1.bin'}],
    )
    return [job, intake, artifact, manifest]


def verify(record, data):
    validate_recording(record, *data, namespace='batch_pipeline_test_replayharness', bucket='replay-staged')


@pytest.fixture
def record():
    return Recording(
        'synthetic-owner', 'synthetic-owner-key', 'synthetic-cid', 'synthetic-content', 'synthetic-segment', 1000, 1
    )


@pytest.mark.parametrize(
    'index,path,value',
    [
        (0, ('state',), 'committed'),
        (0, ('state',), 'dead'),
        (0, ('projection_binding', 'content_id'), 'other-content'),
        (0, ('projection_binding', 'segment_ids'), ['other-segment']),
        (0, ('projection_binding', 'job_id'), 'other-job'),
        (1, ('content_id',), 'other-content'),
        (1, ('segment_ids',), ['other-segment']),
        (2, ('uri',), 'gs://replay-staged/other'),
        (2, ('segment_id',), 'other-segment'),
        (2, ('write_pending_until',), 1),
        (2, ('cleanup_after',), 1),
        (3, ('context', 'content_id'), 'other-content'),
        (3, ('context', 'segment_id'), 'other-segment'),
        (3, ('context', 'job_id'), 'other-job'),
        (3, ('conversation_id',), 'other-conversation'),
        (3, ('references',), [{'path': 'chunks/other-owner/other-cid/1.bin'}]),
    ],
)
def test_every_recording_must_have_its_own_linked_receipts(record, index, path, value):
    data = receipts(record)
    verify(record, data)
    target = data[index]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(EvidenceMismatch):
        verify(record, data)


def test_one_staged_recording_cannot_cover_a_second_unstaged_recording(record):
    first = receipts(record)
    verify(record, first)
    second_record = replace(
        record, content_id='second-content', segment_id='second-segment', conversation_id='second-cid'
    )
    second = receipts(second_record)
    second[2] = deepcopy(first[2])
    with pytest.raises(EvidenceMismatch, match='artifact_identity'):
        verify(second_record, second)
