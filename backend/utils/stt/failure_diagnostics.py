"""Closed, content-free categories for handled transcription failures."""

_STAGES = {
    '_save_wav': 'upload_save',
    '_prepare_voice_message_url': 'storage_prepare',
    'get_syncing_file_temporal_signed_url': 'storage_prepare',
    '_get_signed_url': 'storage_sign',
    'iam_signing_kwargs': 'storage_sign',
    '_validated_wav_is_silent': 'audio_decode',
    '_run_file_vad': 'audio_decode',
    '_segments_from_16khz_samples': 'vad_inference',
    '_get_ort_session': 'vad_inference',
    'get_prerecorded_provider': 'provider_selection',
    'parakeet_prerecorded': 'provider_download',
    '_normalize_parakeet_download': 'provider_decode',
    'parakeet_prerecorded_from_bytes': 'provider_request',
    'postprocess_words': 'transcript_processing',
}
_ERROR_KINDS = {
    'FileNotFoundError': 'file_missing',
    'PermissionError': 'permission',
    'CouldntDecodeError': 'audio_decode',
    'VADAudioDecodeError': 'audio_decode',
    'ParakeetAudioDecodeError': 'audio_decode',
    'VADProcessingError': 'vad_processing',
    'TypeError': 'type',
    'ValueError': 'value',
    'AttributeError': 'attribute',
    'TimeoutError': 'timeout',
    'ReadTimeout': 'timeout',
    'ConnectTimeout': 'timeout',
    'HTTPStatusError': 'upstream_http',
    'Forbidden': 'permission',
    'RefreshError': 'credential_refresh',
    'TransportError': 'transport',
}


def transcription_failure_categories(error: BaseException) -> tuple[str, str]:
    """Inspect bounded traceback/cause shapes, never messages or frame values."""
    stage, kind = 'unknown', 'other'
    seen: set[int] = set()
    current: BaseException | None = error
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        kind = _ERROR_KINDS.get(type(current).__name__, 'other')
        trace = current.__traceback__
        for _ in range(32):
            if trace is None:
                break
            stage = _STAGES.get(trace.tb_frame.f_code.co_name, stage)
            trace = trace.tb_next
        current = current.__cause__ or current.__context__
    return stage, kind
