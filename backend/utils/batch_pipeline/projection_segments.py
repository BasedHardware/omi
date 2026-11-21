"""Reproduce stable batch segment IDs on the unit word clock, before storage rebasing."""

from uuid import NAMESPACE_URL, uuid5

from config.batch_conversation_speakers import vendor_speaker_authority
from config.policy import ProjectionPolicy
from utils.batch_pipeline.projection_parts import bounded_projection_words, align_projection_words, stamp_speaker
from utils.stt.pre_recorded import postprocess_words


def projection_segments(item, binding, payload, *, batch_segment_id=None, policy=None):
    duration = float(payload['audio_seconds'])
    if not 0 < duration <= 7200 or abs(duration - item.duration_seconds) > 0.1 + 1 / 16000 + 1e-9:
        raise ValueError('result audio duration differs from admitted capture')
    # Model clocks may exceed EOF by the validator's 10 ms tolerance. Bound
    # words to real PCM, and keep its precision through the legacy grouper:
    # rounding to centiseconds can otherwise create a decoded coverage hole.
    words = bounded_projection_words(payload['words'], duration)
    # The existing final-pass aligner abstains in diarization gaps; the existing
    # prerecorded grouper supplies the same sentence/segment shapes as sync.
    aligned = align_projection_words(words, payload, item.segment_id)
    # Vendor words already carry the vendor's labels; with its turns they join
    # the same unit scope, centroids and conversation resolver as GPU units.
    vendor_turns = vendor_speaker_authority(payload)
    authoritative = (binding.record_origin or (policy or ProjectionPolicy()).authoritative_labels) and (
        payload.get('recovery_version') != 1 or vendor_turns
    )
    if authoritative:
        # The legacy grouper imputes None from adjacent voices. Keep each gap an
        # explicit anonymous abstention instead of borrowing a speaker/owner.
        gap = 0
        in_gap = False
        prepared = []
        for word in aligned:
            if word['speaker'] is None:
                if not in_gap:
                    gap += 1
                in_gap = True
                word = {**word, 'speaker': f'BATCH_UNASSIGNED_{item.segment_id}_{gap}'}
            else:
                in_gap = False
            prepared.append(word)
        aligned = prepared
    segments = postprocess_words([{**word, 'text': word['word']} for word in aligned], 0, preserve_timestamps=True)
    if not segments:
        raise ValueError('successful batch result produced no transcript')
    # Legacy sync transcribes a VAD-isolated file whose capture timestamp is
    # already shifted. Batch words cover the full capture; undo the grouper's
    # first-word normalization to keep absolute speech/playback clocks intact.
    offset = float(words[0]['timestamp'][0])
    for index, segment in enumerate(segments):
        segment.start += offset
        segment.end += offset
        segment.id = str(uuid5(NAMESPACE_URL, f'batch:{item.segment_id}:{index}'))
        stamp_speaker(segment, item, payload, authoritative, batch_segment_id)
        if authoritative:
            abstained = (segment.speaker or '').startswith('BATCH_UNASSIGNED_')
            segment.is_user, segment.person_id = False, None
            segment.speaker_identity_status = 'ambiguous' if abstained else 'no_match'
            segment.speaker_match_source = (
                'batch_abstention' if abstained else 'batch_vendor' if vendor_turns else 'batch_pyannote'
            )
    return segments
