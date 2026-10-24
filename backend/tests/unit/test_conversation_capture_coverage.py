"""Public coverage projection never exposes the internal source-position receipt."""

from datetime import datetime, timezone
import uuid
import pytest
from models.conversation import Conversation
from utils.committed_capture import CommittedCaptureMap


@pytest.mark.parametrize('coverage', ['incomplete', 'mapped', 'unknown', None])
def test_capture_coverage_projects_existing_receipt_only(coverage):
    row = dict(id='c', created_at=datetime.now(timezone.utc), started_at=None, finished_at=None, structured={})
    if coverage is not None:
        row['capture_evidence'] = dict(
            capability='source_position', coverage=coverage, capture_root='private', runs=[{'start': 1}]
        )
    conversation = Conversation(**row)
    assert conversation.model_dump(mode='json')['capture_coverage'] == coverage
    assert 'capture_evidence' not in conversation.model_dump(mode='json')
    assert 'capture_evidence' not in conversation.model_dump()


def test_legacy_and_public_projection_roundtrip():
    row = dict(id='c', created_at=datetime.now(timezone.utc), started_at=None, finished_at=None, structured={})
    assert Conversation(**row).capture_coverage is None
    public = Conversation(**row, capture_coverage='incomplete').model_dump(mode='json')
    assert Conversation(**public).capture_coverage == 'incomplete'


def _live_committed_envelope(snapshot_coverage: str = 'incomplete', **overrides) -> dict:
    envelope = dict(
        version=1,
        capability='source_position',
        coverage=snapshot_coverage,
        origin='live',
        proof='committed_transcript_v1',
        conflicts=0,
        runs=[
            {
                'capture_root': str(uuid.uuid4()),
                'clock_epoch': 1,
                'source_frame_start': 9000,
                'source_frame_end': 9200,
                'decoded_sample_start': 144_000_000,
                'decoded_sample_end': 147_200_000,
                'samples_per_frame': 1600,
                'rate_hz': 16000,
                'channel': 'mono',
            }
        ],
        lifetime=dict(version=1, complete=True, conflicts=0, history=[]),
    )
    envelope.update(overrides)
    return envelope


def _conversation_with(evidence: dict) -> Conversation:
    return Conversation(
        id='c',
        created_at=datetime.now(timezone.utc),
        started_at=None,
        finished_at=None,
        structured={},
        capture_evidence=evidence,
    )


def test_live_ledger_bound_incomplete_projects_mapped():
    # The run ledger keeps 32 runs of at most 30 seconds each, so a continuous
    # capture past ~16 minutes latches coverage='incomplete' with a complete,
    # conflict-free lifetime. That bound is not observed audio loss.
    conversation = _conversation_with(_live_committed_envelope())
    assert conversation.capture_coverage == 'mapped'


def test_live_committed_envelope_with_conflicts_stays_incomplete():
    envelope = _live_committed_envelope(conflicts=2)
    envelope['lifetime']['conflicts'] = 2
    assert _conversation_with(envelope).capture_coverage == 'incomplete'


def test_live_committed_envelope_with_incomplete_lifetime_stays_incomplete():
    envelope = _live_committed_envelope()
    envelope['lifetime']['complete'] = False
    assert _conversation_with(envelope).capture_coverage == 'incomplete'


def test_receipt_overflow_stub_stays_incomplete():
    # bounded_envelope can replace an oversize sync receipt that is short of
    # frames with this stub; projecting it away would hide real loss.
    envelope = dict(version=1, capability='unknown', coverage='incomplete', reason='overflow')
    assert _conversation_with(envelope).capture_coverage == 'incomplete'


def test_sync_frame_loss_receipt_stays_incomplete():
    envelope = dict(
        version=1,
        capability='source_position',
        coverage='incomplete',
        origin='sync_vad',
        receipts=[{'segment_id': 's1', 'capture_root': str(uuid.uuid4()), 'clock_epoch': 1}],
    )
    assert _conversation_with(envelope).capture_coverage == 'incomplete'


def test_continuous_capture_past_run_bound_projects_mapped_end_to_end():
    # Reproduce the production false positive: 20 minutes of continuous
    # pendant audio with a valid claim on every frame, then assert both the
    # produced receipt and its public projection.
    root = str(uuid.uuid4())
    capture_map = CommittedCaptureMap()
    wall, sample, ordinal = 1000.0, 0, 0
    for i in range(20 * 60 * 10):
        capture_map.accept(
            {'capture_root': root, 'clock_epoch': 1, 'source_frame': ordinal},
            sample_start=sample,
            sample_count=1600,
            rate_hz=16000,
            receipt_wall_time=wall + i * 0.1,
        )
        ordinal += 1
        sample += 1600
    assert capture_map.incomplete is True

    tail = capture_map.runs[-1]
    mid = (tail['decoded_sample_start'] + tail['decoded_sample_end']) // 2
    capture_map.remember_transcripts([{'id': 'seg-1', '_capture_word_ranges': [(mid - 8000, mid + 8000)]}])

    class Segment:
        id = 'seg-1'
        text = 'hello'
        start = 1.0
        end = 2.0
        audio_alignment = 'placed'

    snapshot = capture_map.committed_snapshot('c', [Segment()])
    assert snapshot['coverage'] == 'incomplete'
    assert snapshot['lifetime']['complete'] is True
    conversation = _conversation_with(snapshot)
    assert conversation.capture_coverage == 'mapped'
