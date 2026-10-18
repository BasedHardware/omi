"""Closed, content-free categories for handled transcription failures."""

from typing import NamedTuple

_TRANSPORT_EXCEPTION_CLASSES = frozenset(
    {
        'ConnectionClosed',
        'ConnectionClosedError',
        'ConnectionClosedOK',
        'ConnectionResetError',
        'ConnectionAbortedError',
        'BrokenPipeError',
        'TimeoutError',
        'OSError',
        'SSLError',
        'gaierror',
        'RuntimeError',
        'TypeError',
        'ValueError',
    }
)


class TransportFailureFields(NamedTuple):
    exception_class: str
    received_close_code: int
    sent_close_code: int
    close_cause: str
    session_age_bucket: str


def transport_failure_fields(error: BaseException, age_seconds: float) -> TransportFailureFields:
    """Never serialize exception text, close reasons, or arbitrary class names.

    Separate received/sent codes distinguish a remote close from our own 1011
    keepalive timeout. -1 means no close frame was observed in that direction.
    """

    def close_code(frame: object) -> int:
        code = getattr(frame, 'code', None)
        if not isinstance(code, int) or isinstance(code, bool):
            return -1
        normalized_code = int(code)
        return normalized_code if 1000 <= normalized_code <= 4999 else -1

    received = getattr(error, 'rcvd', None)
    sent = getattr(error, 'sent', None)
    name = type(error).__name__
    age = 'ge_300m'
    for limit, bucket in ((30, 'lt_30s'), (300, 'lt_5m'), (1800, 'lt_30m'), (3600, 'lt_60m'), (18000, 'lt_300m')):
        if age_seconds < limit:
            age = bucket
            break
    return TransportFailureFields(
        name if name in _TRANSPORT_EXCEPTION_CLASSES else 'other',
        close_code(received),
        close_code(sent),
        'keepalive_ping_timeout' if getattr(sent, 'reason', None) == 'keepalive ping timeout' else 'other',
        age,
    )


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
