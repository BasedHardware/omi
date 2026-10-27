"""Transactional replacement of a finalized provisional record, preserving annotations."""

from copy import deepcopy

from utils.conversations.final_pass_remap import remap_final_record
from utils.manual_speaker_assignments import (
    apply_manual_assignments,
    manual_assignment_decision,
    manual_rejected_speakers,
)
from utils.observability.fallback import record_fallback
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator
from utils.sync.assignment_errors import SyncAssignmentConflict
from utils.sync.assignment_errors import SyncAssignmentConflictReason as Reason


def replace_record(current: dict, incoming: dict, span: dict) -> tuple[dict, list[dict]]:
    if current.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
        raise SyncAssignmentConflict('record route owner changed', subtype=Reason.RECORD_ROUTE_OWNER_CHANGED)
    if current.get('deleted'):
        raise SyncAssignmentConflict('record target retired', subtype=Reason.RECORD_TARGET_RETIRED)
    if current.get('discarded'):
        # Recoverable: the user can restore a discarded record without a status change.
        raise SyncAssignmentConflict('record target discarded', subtype=Reason.RECORD_TARGET_DISCARDED)
    if current.get('status') != 'completed':
        raise SyncAssignmentConflict('record finalize still pending', subtype=Reason.RECORD_FINALIZE_PENDING)
    if current.get('uses_custom_stt') or current.get('data_protection_level', 'enhanced') not in {
        'standard',
        'enhanced',
    }:
        raise SyncAssignmentConflict('record privacy changed', subtype=Reason.RECORD_PRIVACY_CHANGED)
    result = deepcopy(current)
    origin = current['started_at'].timestamp()
    start, end = span['start'] - origin, span['end'] - origin
    old = current.get('transcript_segments') or []
    covered = [s for s in old if start <= (s['start'] + s['end']) / 2 < end]
    retained = [s for s in old if s not in covered]
    new = deepcopy(incoming['transcript_segments'])
    shift = incoming['started_at'].timestamp() - origin
    allocator = ConversationSpeakerIdAllocator()
    allocator.hydrate(old)
    for segment in new:
        segment['start'] += shift
        segment['end'] += shift
        if segment['start'] < 0:
            segment['audio_alignment'], segment['audio_capture_run'] = 'unplaced', None
        allocator.assign(segment)
    receipt = current.get('manual_speaker_assignments') or {}
    # IDs can be referenced by summaries, corrections and translation caches.
    # Preserve those anchors and the user's text verbatim; fail closed when a
    # stored sentence straddles incompatible new voices. Unannotated provisional
    # rows are replaced by the record transcript, including new ASR words.
    protected = bool(
        receipt
        or current.get('has_transcript_corrections')
        or current.get('translation_materializations')
        or current.get('apps_results')
        or current.get('note_claims')
        or _has_refs(current.get('structured'))
        or any(s.get('translations') or s.get('speaker_label_source') in {'manual', 'carried'} for s in covered)
    )
    if protected and covered:
        try:
            patch = remap_final_record(
                covered, new, receipt, current.get('structured') or {}, clock_offset=0, protect_legacy_owner=False
            )
        except ValueError:
            record_fallback(
                component='stt_selection', from_mode='none', to_mode='none', reason='other', outcome='degraded'
            )
            # The original text/translation cannot safely be split. Its ID and
            # all annotations survive; do not impute one of several new voices.
            scope = new[0].get('speaker_id_scope') if new else f"final:batch:silence:{incoming['id']}"
            receipt = deepcopy(receipt)
            decisions = receipt.setdefault('segments', {})
            rejected = manual_rejected_speakers(receipt)
            for original in covered:
                decision = manual_assignment_decision(original, receipt, rejected)
                if decision is not None:
                    decisions[original['id']] = decision
            new = deepcopy(covered)
            for segment in new:
                original = dict(segment)
                segment.update(
                    speaker=f"BATCH_UNASSIGNED_{segment['id']}",
                    speaker_id=-1,
                    speaker_id_scope=scope,
                    is_user=False,
                    person_id=None,
                    speaker_identity_status='ambiguous',
                    speaker_match_source='batch_abstention',
                )
                if original.get('speaker_label_source') in {'manual', 'carried'}:
                    segment.update(
                        is_user=original.get('is_user', False),
                        person_id=original.get('person_id'),
                        speaker_label_source=original['speaker_label_source'],
                    )
                allocator.assign(segment)
            new = apply_manual_assignments(new, receipt)
        else:
            new = patch['transcript_segments']
            # Preserve receipts for untouched capture units too.
            updated = deepcopy(receipt)
            updated.setdefault('segments', {}).update(patch['manual_speaker_assignments'].get('segments') or {})
            receipt = updated
    segments = retained + new
    segments.sort(key=lambda s: (s['start'], s['end'], s['id']))
    result.update(
        transcript_segments=apply_manual_assignments(segments, receipt),
        manual_speaker_assignments=receipt,
        sync_content_revision=int(current.get('sync_content_revision') or 0) + 1,
        record_projection_revision=int(current.get('record_projection_revision') or 0) + 1,
        has_content=bool(segments),
        sync_live_target=True,
    )
    finish = incoming.get('finished_at')
    if finish is not None and (result.get('finished_at') is None or finish > result['finished_at']):
        result['finished_at'] = finish
    return result, new


def _has_refs(value):
    if isinstance(value, dict):
        return any((key == 'source_segment_ids' and bool(child)) or _has_refs(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_has_refs(child) for child in value)
    return False
