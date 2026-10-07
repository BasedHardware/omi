# (Trecho relevante da modificação no pipeline de sincronização)
# ... (código existente)
def _record_empty_segment_as_silence(segment_id, job_id):
    # Em vez de apenas marcar como silêncio, retornamos um status que o cliente possa interpretar
    db.update_segment_status(segment_id, status='speech_without_text')
    return {'status': 'speech_without_text', 'segment_id': segment_id}

# No processamento do job:
def process_sync_job(job_id):
    # ... lógica de STT ...
    if not stt_result and retry_failed:
        return _record_empty_segment_as_silence(segment_id, job_id)
    # ...
