"""Synchronous leaf operation called in the existing bounded shadow worker."""

import time
import uuid
from models.diarization import OMI_EMBEDDING_SPACE
from utils.stt.speaker_identity import OMI_SPEAKER_ID_SENTINEL
from models.speaker_label_provenance import project_source
from utils.observability.fallback import record_fallback
from utils.stt.diarization import get_diarizer_backend, LegacyAHC
from utils.stt.diarization_eval import score_words
from utils.stt.diarization_turns import exclusive_from_activity
from utils.stt.local_vad import offline_pcm_speech_segments
from utils.stt.vad_compaction import diarize_with_speech_compaction

import httpx
from prometheus_client import Counter, Histogram

from models.transcript_segment import TranscriptSegment
from utils.conversations.final_pass_assignment import assign_words, name_centroids, skip_single_speaker

OUTCOMES = Counter('omi_transcription_final_pass_total', 'Pyannote final-pass outcomes', ['outcome'])
LATENCY = Histogram('omi_transcription_final_pass_latency_seconds', 'Pyannote final-pass latency')
AGREEMENT = Histogram('omi_transcription_final_pass_agreement', 'Word-weighted speaker agreement with legacy')


def run_final_pass(
    pcm, words, resolution, cache, *, deadline, conversation_id, segments=(), vectors=None, owner_reserved=False
):
    began = time.monotonic()
    try:
        skipped = skip_single_speaker(resolution)
        backend = LegacyAHC() if skipped else get_diarizer_backend()
        output = diarize_with_speech_compaction(
            pcm,
            backend,
            offline_pcm_speech_segments,
            deadline=deadline,
            segments=segments,
            vectors=vectors or {},
            resolution=resolution,
        )
        # Legacy labels are scoped per upload until AHC resolves them. Compare
        # the actual segment projection, never reused window-local SPEAKER_00.
        legacy_turns = [
            {'start': s.start, 'end': s.end, 'speaker': f'{s.speaker_id_scope or "legacy"}:{s.speaker_id}'}
            for s in segments
            if s.speaker_id is not None and s.speaker_id >= 0 and s.end > s.start
        ]
        legacy_words = assign_words(words, exclusive_from_activity(legacy_turns)) if legacy_turns else words
        assigned = assign_words(words, output['turns'])
        decisions = (
            name_centroids(
                output['centroids'], {k: v['embedding'] for k, v in cache.items()}, owner_reserved=owner_reserved
            )
            if output['embedding_space'] == OMI_EMBEDDING_SPACE
            else {}
        )
        if output['embedding_space'] != OMI_EMBEDDING_SPACE:
            record_fallback(
                component='stt_selection',
                from_mode='centroid_naming',
                to_mode='anonymous_speakers',
                reason='capability_mismatch',
                outcome='degraded',
            )
        speakers = {s: i for i, s in enumerate(sorted({t['speaker'] for t in output['turns']}))}
        segments = []
        # Keep word clocks, avoiding postprocess_words' first-word rebase.
        for word in assigned:
            speaker = word['speaker']
            decision = decisions.get(speaker)
            identity = decision.person_id if decision else None
            left, right = word['timestamp']
            if segments and speaker is not None and segments[-1].speaker == speaker and left - segments[-1].end < 1:
                segments[-1].text += ' ' + word['text']
                segments[-1].end = right
            else:
                segments.append(
                    TranscriptSegment(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'omi/final-pass/{conversation_id}/{len(segments)}')),
                        text=word['text'],
                        start=left,
                        end=right,
                        speaker=speaker,
                        speaker_id=speakers.get(speaker, OMI_SPEAKER_ID_SENTINEL),
                        speaker_id_scope=f"final:{output['provenance']['backend']}:{conversation_id}",
                        is_user=identity == 'user',
                        person_id=identity if identity not in (None, 'user') else None,
                        speaker_match_source='final_centroid:' + output['version'],
                        speaker_label_source=project_source(
                            {
                                'is_user': identity == 'user',
                                'person_id': identity if identity != 'user' else None,
                                'speaker_match_source': 'final_centroid',
                            }
                        ),
                        speaker_identity_status=(
                            'user' if identity == 'user' else 'not_user' if identity else 'no_match'
                        ),
                    )
                )
        # Compare anonymous voices with a permutation-invariant overlap mapping.
        total = len(words)
        agreement = (
            score_words([{'speaker': w.get('speaker')} for w in legacy_words], [w['speaker'] for w in assigned])[
                'accuracy_1to1'
            ]
            or 0.0
        )
        AGREEMENT.observe(agreement)
        outcome = 'skipped_single' if skipped else 'diarized'
        OUTCOMES.labels(outcome=outcome).inc()
        return segments, {
            'outcome': outcome,
            'agreement': agreement,
            'word_count': total,
            'speaker_count': len(speakers),
            'overlap_seconds': sum(t['end'] - t['start'] for t in output['overlaps']),
            'version': output['version'],
            'provenance': output['provenance'],
            'embedding_space': output['embedding_space'],
            'naming_outcome': (
                'compatible' if output['embedding_space'] == OMI_EMBEDDING_SPACE else 'incompatible_space'
            ),
        }
    except Exception as error:
        reason = 'timeout' if isinstance(error, (TimeoutError, httpx.TimeoutException)) else 'service'
        OUTCOMES.labels(outcome='failed:' + reason).inc()
        record_fallback(
            component='stt_selection',
            from_mode='whole_conversation_diarizer',
            to_mode='legacy_speaker_matching',
            reason='timeout' if reason == 'timeout' else 'other',
            outcome='degraded',
        )
        return None, {'outcome': 'failed:' + reason}
    finally:
        LATENCY.observe(time.monotonic() - began)
