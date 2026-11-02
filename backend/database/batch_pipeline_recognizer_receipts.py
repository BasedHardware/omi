"""Content-free, token/privacy-fenced provider attempts for held recovery."""

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.contracts import validate_measured_vad, held_vad_census


def record_recognizer(store, segment_id, token, intent, provider, outcome, words, speech_seconds, *, claim=False):
    if intent not in {'recovery', 'speech_redrive'} or provider not in {'modulate', 'soniox'}:
        raise ValueError('closed recognizer receipt required')
    if outcome not in {'started', 'words', 'empty', 'error', 'refused'}:
        raise ValueError('closed recognizer outcome required')
    if words is not None and (isinstance(words, bool) or not isinstance(words, int) or words < 0):
        raise ValueError('word count required')
    if (outcome == 'words' and not words) or (outcome == 'empty' and words != 0):
        raise ValueError('word count disagrees with outcome')

    def commit(tx):
        job, _ = RecoveryStore(store).checked(tx, segment_id, allow_completed_speech_redrive=True)
        existing = tx.get('results', segment_id)
        marker = job.get(intent) or {}
        state = job.get('recovery_state') if intent == 'recovery' else marker.get('state')
        if (
            state != 'running'
            or marker.get('token') != token
            or job.get('result')
            or existing
            or job.get('state') != 'quarantined'
        ):
            raise ProjectionBlocked('recognizer intent lost')
        receipts = marker.setdefault('recognizers', {})
        if claim and provider in receipts:
            return False
        if provider in receipts and receipts[provider]['outcome'] != 'started':
            raise ProjectionBlocked('recognizer already settled')
        measured = validate_measured_vad(speech_seconds, job['duration_seconds'])
        receipts[provider] = {
            'provider': provider,
            'outcome': outcome,
            'word_count': words,
            'vad_speech_seconds': measured,
        }
        job['measured_held_vad_speech_seconds'] = held_vad_census(job, measured)
        tx.put('jobs', segment_id, job)
        return True

    return store.run(commit)
